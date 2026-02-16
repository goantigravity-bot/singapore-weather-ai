
import pandas as pd
from datetime import datetime, timedelta, timezone
import os

def update_sensor_data():
    file_path = "dummy_data/sensor_readings.csv"
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    df = pd.read_csv(file_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Calculate shift
    # We want the last data point to be roughly "now"
    max_ts = df['timestamp'].max()
    now_ts = datetime.now()
    
    # Shift so that the range covers roughly the last few days
    # Let's align the start of the data to (now - 3 days) to match satellite generation roughly
    # Or just shift everything so the latest matches now.
    
    shift = now_ts - max_ts
    
    # We might want to align to 10-minute intervals
    df['timestamp'] = df['timestamp'] + shift
    
    # Round to nearest 10 mins
    df['timestamp'] = df['timestamp'].dt.round('10min')
    
    # Format back to string
    df['timestamp'] = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"Updating {len(df)} records. New range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    df.to_csv(file_path, index=False)
    print("Done.")

if __name__ == "__main__":
    update_sensor_data()
