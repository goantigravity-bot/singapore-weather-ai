import torch
import pandas as pd
import time
from datetime import datetime

# Import from our existing prediction logic
# Note: Ensure predict.py is in the same directory
from predict import load_system, get_station_mapping, find_sensor_id, get_input_data, DEVICE

# --- CONFIGURATION ---
LOCATIONS = [
    "East Coast Park", 
    "Rail Corridor", 
    "Fort Canning Park"
]

def run_batch_forecast():
    print(f"--- Starting Batch Forecast Report @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    
    # 1. Load System (Model + Data)
    try:
        model, df = load_system()
        # Ensure model is in eval mode (load_system does this but good to be explicit if reusing)
        model.eval()
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to load system. {e}")
        return

    # 2. Load Metadata (for geocoding/mapping)
    stations_meta = get_station_mapping()
    if not stations_meta:
        print("Warning: Could not fetch station metadata. Geocoding might fail.")

    # 3. Determine Time (Using latest available in DB for simulation, or Real-time if live)
    # Since this is a retrospective/offline demo, we use the latest timestamp in CSV.
    # In a real live system, this would be `datetime.now()` (and we'd fetch live API data).
    last_ts = df['timestamp'].max()
    print(f"Reference Data Time: {last_ts}\n")

    print(f"{'LOCATION':<25} | {'NEAREST STATION':<25} | {'DIST (km)':<10} | {'PREDICTION (Next 10m)':<25}")
    print("-" * 95)

    for loc_name in LOCATIONS:
        # Find Sensor
        # find_sensor_id handles: csv_match -> fuzzy_name_match -> geocode -> nearest_sensor
        # It prints logs, so we might see some output from it.
        # to suppress logs we could redirect stdout, but for now let's keep it simple.
        
        # We need to capture the sensor ID to run prediction
        # `find_sensor_id` in predict.py returns the ID.
        # But `find_sensor_id` prints stuff. Let's just run it.
        
        try:
            # Note: find_sensor_id prints to stdout. 
            # We might want to wrap it or modify predict.py to be silent, 
            # but for this MVP script, we accept the noise or try to parse results.
            
            # Use a slightly different approach: Resolve ID and Distance first
            # We reuse the logic but maybe we want to calculate distance explicitly for the report?
            # actually `find_sensor_id` calls `find_nearest_sensor` which prints distance.
            
            # Let's just get the ID.
            sensor_id = find_sensor_id(loc_name, df, stations_meta)
            
            if not sensor_id:
                print(f"{loc_name:<25} | {'NOT FOUND':<25} | {'-':<10} | {'N/A'}")
                continue
                
            # Run Prediction
            sat_in, sensor_in = get_input_data(df, sensor_id, last_ts)
            
            weather_desc = "N/A"
            if sat_in is not None and sensor_in is not None:
                with torch.no_grad():
                     pred = model(sat_in.to(DEVICE), sensor_in.to(DEVICE)).item()
                
                if pred < 0.1: weather_desc = "Clear / No Rain"
                elif pred < 2.0: weather_desc = "Light Rain"
                else: weather_desc = "Heavy Rain / Storm"
                
                # Format Prediction String
                pred_str = f"{pred:.4f} mm ({weather_desc})"
            else:
                pred_str = "Data Missing"

            # Check if we can get station name for the table
            # Try to find name in metadata
            station_name = sensor_id
            for s in stations_meta:
                if s['id'] == sensor_id:
                    station_name = s.get('name', sensor_id)
                    break
            
            print(f"{loc_name:<25} | {station_name[:25]:<25} | {'?':<10} | {pred_str}")

        except Exception as e:
            print(f"{loc_name:<25} | {'ERROR':<25} | {'-':<10} | {str(e)}")

    print("-" * 95)
    print("Batch Run Complete.")

if __name__ == "__main__":
    run_batch_forecast()
