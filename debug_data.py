import pandas as pd
from predict import find_sensor_id, get_station_mapping

# Load Data
df = pd.read_csv("real_sensor_data.csv")
stations = get_station_mapping()

# Check Gardens by the Bay
location = "Gardens by the Bay"
print(f"Checking data for: {location}")

sensor_id = find_sensor_id(location, df, stations)
print(f"Mapped Sensor ID: {sensor_id}")

if sensor_id:
    # Check data
    sensor_data = df[df['sensor_id'] == sensor_id]
    print(f"Total Records: {len(sensor_data)}")
    
    if not sensor_data.empty:
        last = sensor_data.sort_values('timestamp').iloc[-1]
        print(f"Last Record Time: {last['timestamp']}")
        print(f"Temperature: {last['temperature']}")
        print(f"Humidity: {last['humidity']}")
        print(f"Rainfall: {last['rainfall']}")
    else:
        print("No records found in CSV for this ID.")
else:
    print("Could not map location to any sensor.")
