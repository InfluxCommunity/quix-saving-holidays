import quixstreams as qx
import os
import pandas as pd
from influxdb_client_3 import InfluxDBClient3, Point, WritePrecision
import ast
import json
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
#from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
# ... other imports ...

# Define a resource with your service name
resource = Resource.create({
    ResourceAttributes.SERVICE_NAME: "RawData_InfluxDB_Exporter"
})

# Configure the OTLP HTTP exporter
otlp_http_exporter = OTLPSpanExporter(
    endpoint="http://ec2-18-153-62-79.eu-central-1.compute.amazonaws.com:4320/v1/traces"  # Replace with your Otel Collector HTTP endpoint
)
# Set the tracer provider with the defined resource
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)

# Use the OTLP HTTP exporter in the BatchSpanProcessor
span_processor = BatchSpanProcessor(otlp_http_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)


client = qx.QuixStreamingClient()

# get the topic consumer for a specific consumer group
topic_consumer = client.get_topic_consumer(topic_id_or_name = os.environ["input"],
                                           consumer_group = "empty-destination")

# Read the environment variable and convert it to a list
tag_columns = ast.literal_eval(os.environ.get('INFLUXDB_TAG_COLUMNS', "[]"))

# Read the enviroment variable for measurement name and convert it to a list
measurement_name = os.environ.get('INFLUXDB_MEASUREMENT_NAME', os.environ["input"])
                                           
client = InfluxDBClient3(token=os.environ["INFLUXDB_TOKEN"],
                         host=os.environ["INFLUXDB_HOST"],
                         org=os.environ["INFLUXDB_ORG"],
                         database=os.environ["INFLUXDB_DATABASE"])


def on_dataframe_received_handler(stream_consumer: qx.StreamConsumer, df: pd.DataFrame):
    try:
        # Reformat the dataframe to match the InfluxDB format
        df = df.rename(columns={'timestamp': 'time'})
        df = df.set_index('time')

        client.write(df, data_frame_measurement_name=measurement_name, data_frame_tag_columns=tag_columns) 
        print("Write successful")
    except Exception as e:
        print(e)
        print("Write failed")


def on_event_data_received_handler(stream_consumer: qx.StreamConsumer,data: qx.EventData):
    with data:
        jsondata = json.loads(data.value)
        metadata = jsondata['metadata']
        data_points = jsondata['data']
        fields = {k: v for d in data_points for k, v in d.items()}
        timestamp = str(data.timestamp)



        
        point = {"measurement": measurement_name, "tags" : metadata, "fields": fields, "time": timestamp}

        print(point)
        client.write(record=point)
        
        


        


def on_stream_received_handler(stream_consumer: qx.StreamConsumer):
    # subscribe to new DataFrames being received
    # if you aren't familiar with DataFrames there are other callbacks available
    # refer to the docs here: https://docs.quix.io/sdk/subscribe.html
    stream_consumer.timeseries.on_dataframe_received = on_dataframe_received_handler

    stream_consumer.events.on_data_received = on_event_data_received_handler


# subscribe to new streams being received
topic_consumer.on_stream_received = on_stream_received_handler

print("Listening to streams. Press CTRL-C to exit.")

# Handle termination signals and provide a graceful exit
qx.App.run()