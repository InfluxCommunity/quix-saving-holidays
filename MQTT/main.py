import quixstreams as qx
from mqtt_function import MQTTFunction
import paho.mqtt.client as paho
from paho import mqtt
import os

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
#from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
# ... other imports ...

# Define a resource with your service name
resource = Resource.create({
    ResourceAttributes.SERVICE_NAME: "MQTT"
})

# Configure the OTLP HTTP exporter
otlp_http_exporter = OTLPSpanExporter(
    endpoint="https://ec2-18-153-62-79.eu-central-1.compute.amazonaws.com:4320/v1/traces",  # Replace with your Otel Collector HTTP endpoint
    # You can add additional configuration as needed
)

# Set the tracer provider with the defined resource
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)

# Use the OTLP HTTP exporter in the BatchSpanProcessor
span_processor = BatchSpanProcessor(otlp_http_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)

def mqtt_protocol_version():
    if os.environ["mqtt_version"] == "3.1":
        return paho.MQTTv31
    if os.environ["mqtt_version"] == "3.1.1":
        return paho.MQTTv311
    if os.environ["mqtt_version"] == "5":
        return paho.MQTTv5
    raise ValueError('mqtt_version is invalid')

mqtt_port = os.environ["mqtt_port"]
if not mqtt_port.isnumeric():
    raise ValueError('mqtt_port must be a numeric value')

with tracer.start_as_current_span("main_execution"):
    # Logic to write data to a Quix stream
    # ...
    mqtt_client = paho.Client(client_id = os.environ["Quix__Deployment__Name"], userdata = None, protocol = mqtt_protocol_version())
    # we'll be using tls
    mqtt_client.tls_set(tls_version = mqtt.client.ssl.PROTOCOL_TLS)
    mqtt_client.username_pw_set(os.environ["mqtt_username"], os.environ["mqtt_password"])

# Quix injects credentials automatically to the client.
# Alternatively, you can always pass an SDK token manually as an argument.
quix_client = qx.QuixStreamingClient()

print("Opening output topic")
producer_topic = quix_client.get_topic_producer(os.environ["output"])

# A stream is a collection of data that belong to a single session of a single source.
stream_producer = producer_topic.create_stream()

stream_producer.properties.name = "MQTT Data"  # Give the stream a human-readable name (for the data catalogue).
stream_producer.properties.location = "/mqtt data"  # Save stream in specific folder to organize your workspace.

mqtt_functions = MQTTFunction(os.environ["mqtt_topic"], mqtt_client, producer_topic, tracer)

# setting callbacks for different events to see if it works, print the message etc.
def on_connect(client, userdata, flags, rc, properties = None):
    if rc == 0:
        mqtt_functions.handle_mqtt_connected()
        print("CONNECTED!") # required for Quix to know this has connected
    else:
        print("ERROR: Connection refused ({})".format(rc))

# print message, useful for checking if it was successful
def on_message(client, userdata, msg):
    with tracer.start_as_current_span("on_message") as span:

        #print(msg.topic + " " + str(msg.qos) + " " + str(msg.payload))

        span.add_event(
            "message_recived",
            {
                "topic": str(msg.topic),
                "QOS": str(msg.qos),
                "payload": str(msg.payload)
            }
        )

        # handle the message in the relevant function
        mqtt_functions.handle_mqtt_message(msg.topic, msg.payload, msg.qos)


# print which topic was subscribed to
def on_subscribe(client, userdata, mid, granted_qos, properties = None):
    print("Subscribed: " + str(mid) + " " + str(granted_qos))


mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.on_subscribe = on_subscribe

# connect to MQTT Cloud on port 8883 (default for MQTT)
mqtt_client.connect(os.environ["mqtt_server"], int(mqtt_port))

# start the background process to handle MQTT messages
mqtt_client.loop_start()

def before_shutdown():
    # stop handling MQTT messages
    mqtt_client.loop_stop()

# Handle graceful exit of the model.
qx.App.run(before_shutdown = before_shutdown)