import quixstreams as qx
import pandas as pd
import numpy as np
import os
from sklearn.preprocessing import StandardScaler


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
        df = df.set_index('timestamp')
        anom_data = df.drop(columns=['machineID'])

        timesteps = 40


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

        # Scale the MSE to a percentage
        min_mse = np.min(mse)
        max_mse = np.max(mse)
        mse_percentage = ((mse - min_mse) / (max_mse - min_mse)) * 100

        # Add 'is_anomalous' column to the DataFrame
        anom_data = anom_data.iloc[timesteps - 1:].copy()
        anom_data['is_anomalous'] = mse_percentage > self.threshold
        anom_data['mse_percentage'] = mse_percentage
        anom_data['threshold'] = self.threshold


        df = df.reset_index().rename(columns={'timestamp': 'time'})
        print(df)


        self.producer_stream.timeseries.buffer.publish(df)  # Send filtered data to output topic›