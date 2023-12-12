import quixstreams as qx
import pandas as pd
import numpy as np
import os
from sklearn.preprocessing import StandardScaler
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
    ResourceAttributes.SERVICE_NAME: "Anomaly_Detection"
})

# Configure the OTLP HTTP exporter
otlp_http_exporter = OTLPSpanExporter(
    endpoint="http://ec2-18-153-62-79.eu-central-1.compute.amazonaws.com:4320/v1/traces"  # Replace with your Otel Collector HTTP endpoint
)

# Configure the OTLP gRPC exporter
#otlp_http_exporter = OTLPSpanExporter(
 #   endpoint="ec2-18-153-62-79.eu-central-1.compute.amazonaws.com:4321"  # Replace with your Otel Collector HTTP endpoint
#)

# Set the tracer provider with the defined resource
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)

# Use the OTLP HTTP exporter in the BatchSpanProcessor
span_processor = BatchSpanProcessor(otlp_http_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)


class QuixFunction:
    def __init__(self, consumer_stream: qx.StreamConsumer, producer_stream: qx.StreamProducer, model):
        self.consumer_stream = consumer_stream
        self.producer_stream = producer_stream
        # Load the autoencoder model from the file
        self.model = model
        self.threshold = float(os.environ["threshold"])  # Define a threshold value (in percentage)
    # Callback triggered for each new event
    def on_event_data_handler(self, stream_consumer: qx.StreamConsumer, data: qx.EventData):
        print(data.value)
        # Transform your data here.
        self.producer_stream.events.publish(data)

    # Callback triggered for each new parameter data.
    def on_dataframe_handler(self, stream_consumer: qx.StreamConsumer, df: pd.DataFrame):
        # Normalize the anomalous data
        print(df)
        with self.tracer.start_as_current_span("dataframe_clean") as span:
        
            df = df.set_index('timestamp')
            anom_data = df.drop(columns=['machineID'])

            timesteps = 40

        with self.tracer.start_as_current_span("predict") as span:
        # Use the Autoencoder to predict on the anomalous data
            scaler = StandardScaler()
            scaled_anom_data= scaler.fit_transform(anom_data)
            predictions = self.model.predict(scaled_anom_data)

            # Assuming the last prediction of each sequence corresponds to the next timestamp
            relevant_predictions = predictions[:, -1, :].squeeze()

            # Adjust the length of normal_scaled to match relevant_predictions
            # This skips the first (timesteps - 1) entries, as they don't have corresponding predictions
            scaled_anom_adjusted = scaled_anom_data[timesteps - 1:]

            # Calculate MSE for each timestamp
            mse = np.power(scaled_anom_adjusted - relevant_predictions, 2).mean(axis=1)

        with self.tracer.start_as_current_span("MSE_Calculation") as span:
            # Scale the MSE to a percentage
            min_mse = np.min(mse)
            max_mse = np.max(mse)
            mse_percentage = ((mse - min_mse) / (max_mse - min_mse)) * 100

            # Add 'is_anomalous' column to the DataFrame
            df = df.iloc[timesteps - 1:].copy()
            df['is_anomalous'] = mse_percentage > self.threshold
            df['mse_percentage'] = mse_percentage
            df['threshold'] = self.threshold


        with self.tracer.start_as_current_span("Publish_Prediction") as span:
            df = df.reset_index().rename(columns={'timestamp': 'time'})
            print(df)


            self.producer_stream.timeseries.buffer.publish(df)  # Send filtered data to output topic›