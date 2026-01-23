import torch
import pandas as pd
import xarray as xr
import os
import glob
import numpy as np
from datetime import datetime, timedelta
from weather_fusion_model import WeatherFusionNet
from weather_dataset import latlon2xy # We reuse the projection tool

# --- Config ---
MODEL_PATH = "weather_fusion_model.pth"
CSV_PATH = "real_sensor_data.csv" # Or dummy_data/sensor_readings.csv
SAT_DIR = "satellite_data"       # Or dummy_data/satellite
DEVICE = torch.device("cpu")

# Singapore Crop Box (Same as in dataset)
SG_LAT_MAX, SG_LON_MIN = 1.50, 103.6
C1, L1 = latlon2xy(SG_LAT_MAX, SG_LON_MIN) 
SG_LAT_MIN, SG_LON_MAX = 1.15, 104.1
C2, L2 = latlon2xy(SG_LAT_MIN, SG_LON_MAX)

def load_system():
    print("Loading Model...")
    model = WeatherFusionNet(sat_channels=1, sensor_features=3, prediction_dim=1)
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model file {MODEL_PATH} not found. Train first!")
        
    model.load_state_dict(torch.load(MODEL_PATH, map_location=DEVICE))
    model.to(DEVICE)
    model.eval()
    
    print("Loading Sensor Database...")
    df = pd.read_csv(CSV_PATH)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return model, df

def get_input_data(df, sensor_id, target_time, seq_len=6):
    """
    Prepare inputs for the model for a specific sensor at a specific time.
    We need:
    1. Past sensor sequence (target_time - seq_len*10min to target_time)
    2. Satellite image at target_time
    """
    
    # 1. Fetch Sensor Sequence
    # Currently dummy data is 10 min interval, real gov data is 1 min.
    # We should resample if needed, but for prototype let's extract last `seq_len` points.
    
    sensor_group = df[df['sensor_id'] == sensor_id].sort_values('timestamp')
    
    # --- RESAMPLING LOGIC (Match Training) ---
    # We need 6 steps of 10-minutes = 60 minutes history
    required_minutes = seq_len * 10
    
    # Extract slightly more to be safe (e.g. 70 mins)
    window_start = target_time - timedelta(minutes=required_minutes + 10)
    window_end = target_time
    
    mask = (sensor_group['timestamp'] >= window_start) & (sensor_group['timestamp'] <= window_end)
    recent_raw = sensor_group[mask].copy()
    
    if recent_raw.empty:
         print(f"Warning: No recent data for {sensor_id}")
         return None, None
         
    # Resample to 10min
    recent_resampled = recent_raw.set_index('timestamp').resample('10min').agg({
        'temperature': 'mean',
        'humidity': 'mean',
        'rainfall': 'sum'
    }).dropna()
    
    # We need exactly the last `seq_len` steps
    recent_data = recent_resampled.tail(seq_len)
    
    if len(recent_data) < seq_len:
        print(f"Warning: Not enough history (after resampling) for {sensor_id}. Found {len(recent_data)} steps (Need {seq_len}).")
        return None, None

    features = recent_data[['temperature', 'rainfall', 'humidity']].values.astype(np.float32)
    
    # NORMALIZATION (Must match weather_dataset.py)
    features[:, 0] = (features[:, 0] - 28.0) / 5.0  
    features[:, 1] = features[:, 1] / 10.0          
    features[:, 2] = (features[:, 2] - 80.0) / 20.0 
    
    sensor_tensor = torch.tensor(features, dtype=torch.float32).unsqueeze(0) # Batch dim
    
    # 2. Fetch Satellite Image
    # Match minute to nearest 10
    minute = (target_time.minute // 10) * 10
    sat_ts = target_time.replace(minute=minute, second=0)
    
    # Try finding file
    # Try finding file
    processed_dir = "processed_data"
    
    # Timezone fix: Timestamp usually local, files UTC.
    # Simple heuristic: If raw file missing, try constructing UTC name
    # But files search usually works with wildcards.
    
    # 1. Try Processed (.npy)
    # Convert sat_ts to UTC string if needed 
    # (Assuming sat_ts is Local Time from CSV, which is usually UTC+8)
    utc_str = (sat_ts - timedelta(hours=8)).strftime('%Y%m%d_%H%M')
    
    npy_pattern = f"NC_H09_{utc_str}_*.npy"
    npy_files = glob.glob(os.path.join(processed_dir, npy_pattern))
    
    files = []
    use_npy = False
    
    if npy_files:
        files = npy_files
        use_npy = True
    else:
        # 2. Try Raw (.nc)
        # Use UTC string pattern
        pattern = f"NC_H09_{utc_str}_*.nc"
        files = glob.glob(os.path.join(SAT_DIR, pattern))
    
    if not files:
        # Fallback to dummy name
        dummy = f"himawari_{sat_ts.strftime('%Y%m%d_%H%M')}.nc"
        dpath = os.path.join(SAT_DIR, dummy)
        if os.path.exists(dpath):
            files = [dpath]
            use_npy = False
            
    sat_tensor = torch.zeros(1, 1, 64, 64)
    
    if files:
        try:
            if use_npy:
                # FAST PATH
                data = np.load(files[0])
                sat_tensor = torch.tensor(data, dtype=torch.float32)
                if sat_tensor.ndim == 2:
                    sat_tensor = sat_tensor.unsqueeze(0).unsqueeze(0)
                elif sat_tensor.ndim == 3:
                     sat_tensor = sat_tensor.unsqueeze(0)
                
                # Normalize (200-300K -> 0-1)
                sat_tensor = (sat_tensor - 200) / 100.0
                print(f"Loaded Cached Image: {os.path.basename(files[0])}")
                
            else:
                # SLOW PATH (Raw NC)
                ds = xr.open_dataset(files[0], decode_timedelta=False)
                
                var_name = 'tbb'
                if 'tbb_13' in ds:
                     var_name = 'tbb_13'
                     
                if ds[var_name].shape[0] > 1000:
                    # Full Disk -> Crop
                    r_min, r_max = min(L1, L2), max(L1, L2)
                    c_min, c_max = min(C1, C2), max(C1, C2)
                    data = ds[var_name][r_min:r_max, c_min:c_max].values
                    temp_tensor = torch.tensor(data, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
                    sat_tensor = torch.nn.functional.interpolate(temp_tensor, size=(64, 64), mode='bilinear', align_corners=False)
                else:
                    data = ds[var_name].values
                    sat_tensor = torch.tensor(data, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
                
                # Normalize
                sat_tensor = (sat_tensor - 200) / 100.0
                ds.close()
                print(f"Loaded Raw Image: {os.path.basename(files[0])}")
        except Exception as e:
            print(f"Error loading sat image: {e}")
    else:
        print(f"Satellite image missing for {sat_ts}")

    return sat_tensor, sensor_tensor

def predict(sensor_id=None, time_str=None):
    model, df = load_system()
    
    # Default: Pick random sensor and latest time if not specified
    if not sensor_id:
        sensor_id = df['sensor_id'].unique()[0]
        print(f"Auto-selected Sensor ID: {sensor_id}")
    
    if not time_str:
        # Latest time in DB
        last_ts = df['timestamp'].max()
        print(f"Auto-selected Time: {last_ts}")
    else:
        last_ts = pd.to_datetime(time_str)

    print(f"\n--- Forecasting for Location: {sensor_id} @ {last_ts} ---")
    
    sat_in, sensor_in = get_input_data(df, sensor_id, last_ts)
    
    if sat_in is None or sensor_in is None:
        print("Failed to prepare input data.")
        return

    with torch.no_grad():
        prediction = model(sat_in.to(DEVICE), sensor_in.to(DEVICE))
        pred_val = prediction.item()
        
    print(f"\n>>> PREDICTED RAINFALL (Next 10 mins): {pred_val:.4f} mm")
    
    # Interpretation
    if pred_val < 0.1:
        print("Weather Outlook: Clear / No Rain")
    elif pred_val < 2.0:
        print("Weather Outlook: Light Rain")
    else:
        print("Weather Outlook: Heavy Rain / Storm")

import argparse
import requests
import difflib
import numpy as np
import pandas as pd

# --- Helper: Geocoding ---
def geocode_location(address):
    """
    Convert address string to (lat, lon) using OpenStreetMap Nominatim API.
    """
    # Nominatim requires a User-Agent
    headers = {'User-Agent': 'SingaporeWeatherAI/1.0'}
    url = "https://nominatim.openstreetmap.org/search"
    
    # Append ", Singapore" to ensure we search locally
    if "singapore" not in address.lower():
        address += ", Singapore"
        
    params = {
        'q': address,
        'format': 'json',
        'limit': 1
    }
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        data = resp.json()
        
        if data:
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            print(f"Geocoded '{address}': ({lat:.4f}, {lon:.4f})")
            return lat, lon
        else:
            print(f"Geocoding failed: No results for '{address}'")
            return None, None
            
    except Exception as e:
        print(f"Geocoding error: {e}")
        return None, None

# --- Helper: Get Station Metadata ---
def get_station_mapping():
    """Fetch real-time station metadata from NEA API to map Names and Locations -> IDs."""
    # Use Rainfall API because it has significantly more stations (60+) compared to Temperature (2-14)
    # This ensures better coverage for finding the nearest sensor.
    url = "https://api.data.gov.sg/v1/environment/rainfall"
    try:
        # verify=False to avoid SSL issues in some envs
        resp = requests.get(url, timeout=5, verify=False) 
        data = resp.json()
        stations = data.get("metadata", {}).get("stations", [])
        
        # Return list of dicts for more info
        # [{'id': 'S50', 'device_id': 'S50', 'name': 'Clementi', 'location': {'latitude': 1.3337, 'longitude': 103.7768}}]
        print(f"[Info] Fetched metadata for {len(stations)} rainfall stations.")
        return stations
    except Exception as e:
        print(f"Warning: Could not fetch station metadata: {e}")
        return []

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate Euclidean distance (sufficient for small area like Singapore).
    Returns degrees (approx).
    """
    return np.sqrt((lat1 - lat2)**2 + (lon1 - lon2)**2)

def find_nearest_sensor(target_lat, target_lon, stations):
    """Find the nearest sensor ID to the given coordinates."""
    if not stations:
        return None

    best_id = None
    min_dist = float('inf')
    best_name = "Unknown"

    for s in stations:
        try:
            slat = s['location']['latitude']
            slon = s['location']['longitude']
            sid = s['id']
            sname = s.get('name', 'Unknown')
            
            dist = calculate_distance(target_lat, target_lon, slat, slon)
            if dist < min_dist:
                min_dist = dist
                best_id = sid
                best_name = sname
        except KeyError:
            continue
            
    if best_id:
        # Approx conversion: 0.01 deg ~= 1.1km
        dist_km = min_dist * 111.0 
        print(f"Nearest Station: {best_name} (ID: {best_id}) - Distance: {dist_km:.2f} km")
        return best_id
    return None

def find_sensor_id(query, df, stations_metadata):
    """
    Find sensor ID by logic chain:
    1. Exact ID Match in CSV
    2. Fuzzy Name Match in Metadata
    3. Geocoding -> Nearest Sensor
    """
    # 1. Check if query is an ID existing in our CSV
    unique_ids = df['sensor_id'].unique()
    if query in unique_ids:
        return query
        
    # 2. Check name mapping (Fuzzy)
    name_map = {s['name']: s['id'] for s in stations_metadata if 'name' in s}
    names = list(name_map.keys())
    matches = difflib.get_close_matches(query, names, n=1, cutoff=0.6) # Stricter cutoff to prefer Geocoding if not sure
    
    if matches:
        best_name = matches[0]
        mapped_id = name_map[best_name]
        print(f"Location '{query}' matched to Station Name '{best_name}' (ID: {mapped_id})")
        return mapped_id
        
    # 3. Geocoding Fallback
    print(f"Searching map for '{query}'...")
    lat, lon = geocode_location(query)
    if lat is not None and lon is not None:
        return find_nearest_sensor(lat, lon, stations_metadata)

    print(f"Could not find any location matching '{query}'.")
    return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Weather Forecast for Singapore")
    parser.add_argument("locations", nargs="*", help="List of Location names or Addresses (e.g. 'Marina Bay Sands')")
    parser.add_argument("--time", type=str, help="Target time (YYYY-MM-DD HH:MM:SS), defaults to latest")
    # New geospatial args
    parser.add_argument("--lat", type=float, help="Target Latitude")
    parser.add_argument("--lon", type=float, help="Target Longitude")
    
    args = parser.parse_args()
    
    # Validation
    if (args.lat is not None) != (args.lon is not None):
        print("Error: Must provide BOTH --lat and --lon.")
        exit(1)
    
    try:
        # Load system first
        model, df = load_system()
        
        # Load Metadata for Mapping
        stations_meta = get_station_mapping()
        
        # Determine Timestr
        last_ts = None
        if not args.time:
             last_ts = df['timestamp'].max()
             print(f"Auto-selected Time: {last_ts}")
        else:
             # Fix Timezone: Input string is Naive, but DataFrame is usually UTC+8
             # We assume user input is SG local time.
             last_ts = pd.to_datetime(args.time)
             if last_ts.tz is None and df['timestamp'].dt.tz is not None:
                 last_ts = last_ts.tz_localize(df['timestamp'].dt.tz)
        
        # Determine Target Sensors
        target_sensors = []
        
        # Case A: Lat/Lon provided
        if args.lat is not None and args.lon is not None:
            print(f"Finding nearest sensor for coordinates: ({args.lat}, {args.lon})")
            nearest = find_nearest_sensor(args.lat, args.lon, stations_meta)
            if nearest:
                target_sensors.append(nearest)
            else:
                print("Could not determine nearest sensor (Metadata fetch failed?).")
                
        # Case B: Location Names provided
        elif args.locations:
            for query in args.locations:
                found = find_sensor_id(query, df, stations_meta)
                if found:
                    target_sensors.append(found)

        # Case C: Default (Random/First)
        else:
             # Only if no lat/lon was provided
             target_sensors.append(df['sensor_id'].unique()[0])
             print(f"Auto-selected Sensor ID: {target_sensors[0]}")
            
        
        # Run Prediction for all targets
        for target_sensor in target_sensors:
            print(f"\n--- Forecasting for Location: {target_sensor} @ {last_ts} ---")
            sat_in, sensor_in = get_input_data(df, target_sensor, last_ts)
            
            if sat_in is None or sensor_in is None:
                 print("Failed to prepare input data (History too short or missing Sat image).")
            else:
                 with torch.no_grad():
                     prediction = model(sat_in.to(DEVICE), sensor_in.to(DEVICE))
                     pred_val = prediction.item()
                     
                 print(f">>> PREDICTED RAINFALL (Next 10 mins): {pred_val:.4f} mm")
                 if pred_val < 0.1: print("Weather Outlook: Clear / No Rain")
                 elif pred_val < 2.0: print("Weather Outlook: Light Rain")
                 else: print("Weather Outlook: Heavy Rain / Storm")
             
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


