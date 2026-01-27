import torch
import pandas as pd
import xarray as xr
import os
import glob
import numpy as np
from scipy.spatial import Delaunay
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
    model = WeatherFusionNet(sat_channels=1, sensor_features=4, prediction_dim=1)
    if not os.path.exists(MODEL_PATH):
        print(f"Warning: Model file {MODEL_PATH} not found. Starting with initialized model (random weights).")
    else:
        try:
            state_dict = torch.load(MODEL_PATH, map_location=DEVICE, weights_only=True)
            model.load_state_dict(state_dict)
            print("Model loaded successfully.")
        except Exception as e:
            print(f"⚠️ Error loading model weights: {e}")
            print("⚠️ Starting with initialized model (random weights) for testing/verification.")
    
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
        'rainfall': 'sum',
        'pm25': 'mean'
    }).dropna()
    
    # We need exactly the last `seq_len` steps
    recent_data = recent_resampled.tail(seq_len)
    
    if len(recent_data) < seq_len:
        print(f"Warning: Not enough history (after resampling) for {sensor_id}. Found {len(recent_data)} steps (Need {seq_len}).")
        return None, None

    features = recent_data[['temperature', 'rainfall', 'humidity', 'pm25']].values.astype(np.float32)
    
    # NORMALIZATION (Must match weather_dataset.py)
    features[:, 0] = (features[:, 0] - 28.0) / 5.0  
    features[:, 1] = features[:, 1] / 10.0          
    features[:, 2] = (features[:, 2] - 80.0) / 20.0 
    features[:, 3] = (features[:, 3] - 20.0) / 20.0 
    
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
    headers = {'User-Agent': 'SingaporeWeatherAI/0.3'}
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

def reverse_geocode(lat, lon):
    """
    Convert (lat, lon) to address string using OpenStreetMap Nominatim API.
    """
    headers = {'User-Agent': 'SingaporeWeatherAI/0.3'}
    url = "https://nominatim.openstreetmap.org/reverse"
    
    params = {
        'lat': lat,
        'lon': lon,
        'format': 'json',
        'zoom': 18,
        'addressdetails': 1
    }
    
    try:
        # verify=False to prevent SSL errors in some envs
        resp = requests.get(url, params=params, headers=headers, timeout=5, verify=False) 
        data = resp.json()
        
        # DEBUG PRINT
        # print(f"DEBUG: Nominatim Resp: {data}")
        
        if 'display_name' in data:
            # Simplify the name: Pick formatted address or specific parts
            addr = data.get('address', {})
            # Priorities: Road, Landmark, Suburb, etc.
            parts = []
            
            # Expanded list of useful address parts
            for key in ['tourism', 'historic', 'amenity', 'building', 'leisure', 'road', 'residential', 'village', 'suburb', 'town', 'city_district', 'district']:
                if key in addr:
                    val = addr[key]
                    # Filter out generic terms if possible
                    parts.append(val)
                    break 
            
            if not parts:
                return data['display_name'].split(',')[0]
            
            return parts[0]
            
        else:
            print(f"DEBUG: No display_name in reverse geocode resp for {lat},{lon}")
            return f"{lat:.3f}, {lon:.3f}"
            
        return None
        
    except Exception as e:
        print(f"Reverse Geocoding error: {e}")
        return None

# --- Helper: OSM Path Fetching ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat/2)**2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    return R * c

def fetch_osm_path(query):
    print(f"Querying Overpass API for: {query}")
    overpass_url = "http://overpass-api.de/api/interpreter"
    
    # Singapore Bounding Box
    bbox = "1.15,103.55,1.48,104.1"
    
    # Ask for tags so we can filter
    overpass_query = f"""
    [out:json][timeout:45];
    (
      way["name"~"{query}",i]({bbox});
      relation["name"~"{query}",i]({bbox});
    );
    out geom tags;
    """
    
    try:
        response = requests.get(overpass_url, params={'data': overpass_query}, timeout=50)
        data = response.json()
        
        if not data or 'elements' not in data:
            return None

        # --- INTELLIGENT FILTERING ---
        # Only accept if it looks like a hiking/cycling path
        valid_path_elements = []
        
        # Keywords that FORCE path mode (override tag checks)
        path_keywords = ["corridor", "trail", "connector", "pcn", "track", "walk", "greenway"]
        force_path = any(k in query.lower() for k in path_keywords)
        
        print(f"Path Logic: Force={force_path}")

        for el in data['elements']:
            tags = el.get('tags', {})
            highway = tags.get('highway', '')
            leisure = tags.get('leisure', '')
            route = tags.get('route', '')
            
            # Acceptance Criteria
            is_cycleway = highway in ['cycleway', 'path', 'footway', 'pedestrian', 'track', 'steps']
            is_route = route in ['hiking', 'foot', 'bicycle']
            is_leisure_track = leisure == 'track'
            
            # Rejection Criteria (Vehicle Roads)
            # e.g. Commonwealth Ave is primary/residential
            is_vehicle = highway in ['motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'residential', 'service', 'unclassified']
            
            if force_path:
                # If user typed "Rail Corridor", accept it even if some segments are weird, 
                # but assume Overpass returned mostly correct things.
                # Just avoid obvious huge roads if possible, or accept if it's the only match.
                 valid_path_elements.append(el)
            else:
                # Strict Mode for generic queries like "Sentosa"
                if (is_cycleway or is_route or is_leisure_track) and not is_vehicle:
                    valid_path_elements.append(el)
                    
        if not valid_path_elements:
            print("Path Filtering: No elements matched 'Recreational Path' criteria.")
            return None
            
        print(f"Path Filtering: Found {len(valid_path_elements)} valid path segments.")
        # Return filtered data structure
        return {'elements': valid_path_elements}
        
    except Exception as e:
        print(f"Overpass Error: {e}")
        return None

def process_and_sample_path(data, sample_dist_km=2.0):
    if not data or 'elements' not in data:
        return []
        
    all_points = []
    
    for el in data['elements']:
        if 'geometry' in el:
            for pt in el['geometry']:
                all_points.append([pt['lat'], pt['lon']])
        elif 'members' in el:
            for member in el['members']:
                if 'geometry' in member:
                    for pt in member['geometry']:
                        all_points.append([pt['lat'], pt['lon']])

    if not all_points:
        return []
        
    points = np.array(all_points)
    
    # 1. Remove duplicates
    _, unique_idx = np.unique(points.round(decimals=4), axis=0, return_index=True)
    points = points[unique_idx]
    
    # 2. Sort by Latitude (Heuristic for simple linear features like Rail Corridor)
    # This is not perfect for complex shapes but works for the specific user request.
    sorted_points = points[np.argsort(points[:, 0])[::-1]] # North to South
    
    if len(sorted_points) == 0:
        return []
        
    final_samples = [sorted_points[0]]
    
    for i in range(1, len(sorted_points)):
        curr = sorted_points[i]
        last = final_samples[-1]
        
        # Dist in km
        dist = haversine(last[0], last[1], curr[0], curr[1])
        
        if dist >= sample_dist_km:
            final_samples.append(curr)
            
    return final_samples

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

# Global cache for Delaunay mesh to avoid rebuilding on every click
_delaunay_mesh = None
_delaunay_stations = []

def get_delaunay_mesh(stations):
    global _delaunay_mesh, _delaunay_stations
    
    # Check if we need to rebuild (if stations changed or first run)
    # Simple check: count
    if _delaunay_mesh is not None and len(stations) == len(_delaunay_stations):
        return _delaunay_mesh, _delaunay_stations
        
    coords = []
    valid_stations = []
    for s in stations:
        try:
            lat = s['location']['latitude']
            lon = s['location']['longitude']
            coords.append([lat, lon])
            valid_stations.append(s)
        except KeyError:
            continue
            
    if len(coords) < 3:
        return None, []
        
    _delaunay_mesh = Delaunay(np.array(coords))
    _delaunay_stations = valid_stations
    print(f"Built Delaunay Mesh with {len(coords)} points.")
    return _delaunay_mesh, _delaunay_stations

def find_nearest_n_sensors(target_lat, target_lon, stations, n=3):
    """
    Find sensors using Delaunay Triangulation (Geometric Enclosure).
    1. If point is inside a triangle, return its 3 vertices.
    2. If outside (simplex=-1), fallback to 3 nearest by distance.
    """
    if not stations:
        return []

    # 1. Try Delaunay
    mesh, valid_stations = get_delaunay_mesh(stations)
    
    simplex_idx = -1
    triangle_sensors = []
    
    if mesh:
        # find_simplex returns the index of the triangle containing the point
        # It handles arrays, so we pass [[lat, lon]]
        simplex_idx = mesh.find_simplex([[target_lat, target_lon]])[0]
        
        if simplex_idx != -1:
            # Found a containing triangle!
            # Get indices of the 3 vertices
            vertex_indices = mesh.simplices[simplex_idx]
            
            triangle_sensors = []
            for idx in vertex_indices:
                s = valid_stations[idx]
                sid = s['id']
                slat = s['location']['latitude']
                slon = s['location']['longitude']
                dist_deg = calculate_distance(target_lat, target_lon, slat, slon)
                dist_km = dist_deg * 111.0
                triangle_sensors.append((sid, dist_km))
            
            # Sort by distance just for consistency
            triangle_sensors.sort(key=lambda x: x[1])
            print(f"Geometric Selection: Inside Triangle {[s[0] for s in triangle_sensors]}")
            # Do NOT return here. Fall through to filter logic.
            # return triangle_sensors

    # --- 2. Fallback to Distance-based K-Nearest (If Delaunay Failed) ---
    candidates = []
    
    # If we are here, we are OUTSIDE triangle (since we return inside the if block above).
    
    print("Geometric Selection: Fallback to K-Nearest Candidates.")
    for s in stations:
        try:
            slat = s['location']['latitude']
            slon = s['location']['longitude']
            sid = s['id']
            dist_deg = calculate_distance(target_lat, target_lon, slat, slon)
            dist_km = dist_deg * 111.0
            candidates.append((sid, dist_km))
        except KeyError:
            continue
            
    candidates.sort(key=lambda x: x[1])
    candidates = candidates[:n] # Pre-slice to N, but filter might reduce further
    
    # --- 3. Filter / Prune ---
    # We now have a list of 'candidates' (either from Triangle or K-Nearest).
    # Logic:
    #   - Sort by distance
    #   - Always keep the closest one.
    #   - For the others, check:
    #       1. Absolute max distance (e.g. 15km)
    #       2. Relative max distance (e.g. > 3x the closest distance)
    
    if not candidates and not triangle_sensors:
         return []
         
    # Unite potential lists (simplifies flow if we had mixed logic, but here it's one or other)
    # Just use 'final_list'
    final_list = triangle_sensors if triangle_sensors else candidates
    
    # Sort just in case
    final_list.sort(key=lambda x: x[1])
    
    if not final_list:
        return []
        
    closest_dist = final_list[0][1]
    filtered_list = [final_list[0]] # Always keep best
    
    for i in range(1, len(final_list)):
        sid, dist = final_list[i]
        
        # 1. Absolute Cutoff (Singapore is small, >15km is irrelevant)
        if dist > 15.0:
            continue
            
        # 2. Relative Cutoff
        # If it's 3x further than the nearest, AND strictly > 3km away.
        # (The >3km check prevents pruning when everything is super close like 0.5km vs 1.6km)
        if dist > (closest_dist * 3.0) and dist > 3.0:
            continue
            
        filtered_list.append((sid, dist))
        
    print(f"Sensor Pruning: {len(final_list)} -> {len(filtered_list)} (Nearest: {closest_dist:.2f}km)")
    
    return filtered_list[:n]

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


