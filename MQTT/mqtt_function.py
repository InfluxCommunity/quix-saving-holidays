import quixstreams as qx
import paho.mqtt.client as paho
from datetime import datetime


class MQTTFunction:

    def __init__(self, topic, mqtt_client: paho.Client, producer_topic: qx.TopicProducer, tracer):
        self.mqtt_client = mqtt_client
        self.topic = topic
        self.producer_topic = producer_topic
        self.tracer = tracer

    def handle_mqtt_connected(self):
        # once connection is confirmed, subscribe to the topic
        with self.tracer.start_as_current_span("mqtt_connect"):
            self.mqtt_client.subscribe(self.topic, qos = 1)

    def handle_mqtt_message(self, topic, payload, qos):
        # publish message data to a new event
        # if you want to handle the message in a different way
        # implement your own logic here.
        with self.tracer.start_as_current_span("mqtt_publish") as span:
            span.set_attribute("stream_name", str(topic).replace("/", "-"))
            span_context = span.get_span_context()

            # Custom payload with trace context
            otel = {
                "trace_id": str(span_context.trace_id),
                "span_id": str(span_context.span_id),
            }
            
        
            self.producer_topic.get_or_create_stream(str(topic).replace("/", "-")).events \
                .add_timestamp(datetime.utcnow()) \
                .add_value("data", payload.decode("utf-8")) \
                .add_value("otel", otel) \
                .add_tag("qos", str(qos)) \
                .publish()
            
