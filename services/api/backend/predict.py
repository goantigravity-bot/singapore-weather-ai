import torch
import pandas as pd
import xarray as xr
import os
import glob
import numpy as np

from scipy.spatial import Delaunay
from datetime import datetime, timedelta
from weather_fusion_model import WeatherFusionNet

# --- Himawari EQR L3 投影参数 ---
# 原始数据来自 weather_dataset.py，内联以消除对该模块的依赖
# 投影: Equirectangular, 覆盖 60N→60S / 70E→150W, 分辨率 0.02°
LAT_MAX = 60.0
LON_MIN = 70.0
RES = 0.02

def latlon2xy(lat, lon):
    """将经纬度转为 Himawari EQR L3 像素坐标 (col, row)"""
    y = (LAT_MAX - lat) / RES
    x = (lon - LON_MIN) / RES
    return int(round(x)), int(round(y))

# --- Config ---
MODEL_PATH = "weather_fusion_model.pth"
CSV_PATH = "real_sensor_data.csv"
SAT_DIR = "satellite_data"
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
        # 不足 seq_len 步时，用最早一行向前填充（pad），而非直接失败
        # 这样在实时数据初始拉取阶段也能出预测结果
        if len(recent_data) == 0:
            print(f"Warning: No resampled data for {sensor_id}")
            return None, None
        deficit = seq_len - len(recent_data)
        pad_row = recent_data.iloc[[0]]
        padding = pd.concat([pad_row] * deficit, ignore_index=False)
        recent_data = pd.concat([padding, recent_data])

    features = recent_data[['temperature', 'rainfall', 'humidity', 'pm25']].values.astype(np.float32)
    
    # NORMALIZATION (Must match weather_dataset.py)
    features[:, 0] = (features[:, 0] - 28.0) / 5.0   # Temp
    features[:, 1] = features[:, 1] / 10.0            # Rain
    features[:, 2] = (features[:, 2] - 80.0) / 20.0   # Humidity
    features[:, 3] = (features[:, 3] - 20.0) / 20.0   # PM2.5
    
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
    
    # 兼容 Himawari-8 (H08) 和 Himawari-9 (H09) 两种卫星命名
    npy_files = []
    nc_files = []
    for sat_prefix in ["NC_H08_", "NC_H09_"]:
        npy_pattern = f"{sat_prefix}{utc_str}_*.npy"
        npy_files.extend(glob.glob(os.path.join(processed_dir, npy_pattern)))
    
    files = []
    use_npy = False
    
    if npy_files:
        files = npy_files
        use_npy = True
    else:
        # 2. Try Raw (.nc)
        for sat_prefix in ["NC_H08_", "NC_H09_"]:
            pattern = f"{sat_prefix}{utc_str}_*.nc"
            nc_files.extend(glob.glob(os.path.join(SAT_DIR, pattern)))
        files = nc_files
    
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

def predict_ensemble(lat, lon, time_obj, model, df, stations_meta, ensemble_size=3):
    """
    Advanced prediction using Spatial Smoothing (Ensemble) and Cloud Analysis.
    Returns: {
        'rainfall': float (mm),
        'status': str,
        'confidence': float (0-1),
        'cloud_cover': bool,
        'details': dict
    }
    """
    # 1. Spatial Smoothing: Find N nearest sensors
    nearest_sensors = find_nearest_n_sensors(lat, lon, stations_meta, n=ensemble_size)
    
    if not nearest_sensors:
        print(f"No sensors found near {lat}, {lon}")
        return None

    predictions = []
    weights = []
    contributing_sensor_ids = []  # 记录实际参与插值的传感器 ID（前端 triangle 需要）
    
    debug_info = []

    # Get Satellite Image ONCE (optimization) - though get_input_data does it per sensor.
    # We'll rely on cache or just let it run (images are small).
    # But for cloud analysis, we need the raw TBB from the *target* location.
    # Since we don't have a direct "get_lat_lon_pixel" function easily exposed,
    # we will use the TBB from the satellite input of the closest sensor as a proxy.
    
    tbb_val = None
    
    for i, (sensor_id, dist_km) in enumerate(nearest_sensors):
        # Weight inverse to distance (plus epsilon)
        w = 1.0 / (dist_km + 1.0)
        
        sat_in, sensor_in = get_input_data(df, sensor_id, time_obj)
        
        if sat_in is None or sensor_in is None:
            continue
            
        # Capture TBB from the first (closest) valid sensor for cloud analysis
        if tbb_val is None and sat_in is not None:
             # sat_in is (1, 1, 64, 64) normalized (val - 200)/100
             # We want the center pixel approx.
             # In a real system, we'd map lat/lon to pixel. 
             # Here, we take the mean of the center 16x16 crop as "local cloudiness"
             center_crop = sat_in[0, 0, 24:40, 24:40] 
             mean_norm = center_crop.mean().item()
             tbb_val = mean_norm * 100.0 + 200.0 # De-normalize
        
        with torch.no_grad():
            pred = model(sat_in.to(DEVICE), sensor_in.to(DEVICE)).item()
            
        predictions.append(pred)
        weights.append(w)
        contributing_sensor_ids.append(sensor_id)
        debug_info.append(f"{sensor_id}({dist_km:.1f}km): {pred:.2f}mm")

    if not predictions:
        return None
        
    # Weighted Average
    weights = np.array(weights)
    predictions = np.array(predictions)
    
    # Normalize weights
    weights = weights / weights.sum()
    
    final_pred = np.sum(predictions * weights)
    
    # 2. Confidence Score
    # Based on standard deviation of predictions
    # If std is high -> low confidence
    if len(predictions) > 1:
        std_dev = np.std(predictions)
        # Map std: 0.0 -> 1.0 conf, >1.0 -> 0.0 conf
        confidence = max(0.0, 1.0 - std_dev)
    else:
        confidence = 0.5 # Single sensor default
        
    # 3. Cloud Cover Analysis
    is_cloudy = False
    cloud_msg = ""
    # TBB threshold: < 15°C (288K). 
    # Usually < 273K is definitely cloud. < 240K is deep convection.
    if tbb_val:
        if tbb_val < 288.0:
            is_cloudy = True
            cloud_msg = f"(Clouds Detected: {tbb_val:.1f}K)"
        else:
            cloud_msg = f"(Clear Sky: {tbb_val:.1f}K)"

    # Status Determination
    status = "Unknown"
    if final_pred < 0.1:
        status = "Cloudy" if is_cloudy else "Clear"
    elif final_pred < 2.0:
        status = "Light Rain"
    else:
        status = "Heavy Rain"
        
    return {
        'rainfall': final_pred,
        'status': status,
        'confidence': confidence,
        'cloud_cover': is_cloudy,
        'contributing_sensors': contributing_sensor_ids,
        'debug': f"Ens: {', '.join(debug_info)} {cloud_msg}"
    }

def predict(sensor_id=None, time_str=None):
    # wrapper for backward compatibility or simple testing
    model, df = load_system()
    stations_meta = get_station_mapping()
    
    if not time_str:
        last_ts = df['timestamp'].max()
    else:
         last_ts = pd.to_datetime(time_str)
         
    if not sensor_id:
        sensor_id = df['sensor_id'].unique()[0]
        
    # We need lat/lon for ensemble
    # Try to find it in meta
    lat, lon = None, None
    for s in stations_meta:
        if s['id'] == sensor_id:
            lat = s['location']['latitude']
            lon = s['location']['longitude']
            break
            
    if lat:
        res = predict_ensemble(lat, lon, last_ts, model, df, stations_meta)
        if res:
            print(f">>> PREDICTED: {res['rainfall']:.4f} mm ({res['status']})")
            print(f"    Conf: {res['confidence']:.2f} | {res['debug']}")
            return
            
    # Fallback to single
    print("Fallback to single sensor prediction...")
    # ... (rest of old logic if needed, but we essentially replaced it)

import argparse
import requests
import difflib
import numpy as np
import pandas as pd

# --- Helper: Geocoding ---
# L1: 进程内字典（避免每次查库），L2: SQLite 表（跨 worker 共享 + 重启持久化）
_geocode_cache: dict[str, tuple[float, float]] = {}

def geocode_location(address):
    """
    Convert address string to (lat, lon).
    Two-tier cache: L1 in-memory dict → L2 SQLite table → Provider API.
    Provider 由 geocoding 模块管理（运行时可切换 Nominatim / OneMap）。
    Only successful results are cached; failures trigger retry on next call.
    """
    # L1: 进程内命中
    if address in _geocode_cache:
        return _geocode_cache[address]

    # L2: SQLite 共享缓存（另一个 worker 可能已写入）
    try:
        from db import get_geocode_cache, set_geocode_cache
        cached = get_geocode_cache(address)
        if cached:
            _geocode_cache[address] = cached
            return cached
    except Exception:
        pass

    # L3: 调用 Provider API（Nominatim 或 OneMap）
    import geocoding
    lat, lon = geocoding.geocode(address)

    if lat is not None and lon is not None:
        _geocode_cache[address] = (lat, lon)
        # 写入 L2 供其他 worker 和重启后使用
        try:
            set_geocode_cache(address, lat, lon)
        except Exception:
            pass
        return lat, lon

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

# Overpass API 缓存：L1 进程内字典 + L2 SQLite 持久化
_osm_cache: dict[str, dict] = {}

def fetch_osm_path(query):
    # L1: 进程内命中
    if query in _osm_cache:
        print(f"Overpass API L1 cache hit for: {query}")
        return _osm_cache[query]

    # L2: SQLite 共享缓存
    try:
        from db import get_overpass_cache, set_overpass_cache
        cached = get_overpass_cache(query)
        if cached:
            print(f"Overpass API L2 cache hit for: {query}")
            _osm_cache[query] = cached
            return cached
    except Exception:
        pass

    # L3: 调用 Overpass API
    print(f"Querying Overpass API for: {query} (cache miss)")
    overpass_url = "http://overpass-api.de/api/interpreter"
    
    bbox = "1.15,103.55,1.48,104.1"
    
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
        valid_path_elements = []
        
        path_keywords = ["corridor", "trail", "connector", "pcn", "track", "walk", "greenway"]
        force_path = any(k in query.lower() for k in path_keywords)
        
        print(f"Path Logic: Force={force_path}")

        for el in data['elements']:
            tags = el.get('tags', {})
            highway = tags.get('highway', '')
            leisure = tags.get('leisure', '')
            route = tags.get('route', '')
            
            is_cycleway = highway in ['cycleway', 'path', 'footway', 'pedestrian', 'track', 'steps']
            is_route = route in ['hiking', 'foot', 'bicycle']
            is_leisure_track = leisure == 'track'
            is_vehicle = highway in ['motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'residential', 'service', 'unclassified']
            
            if force_path:
                 valid_path_elements.append(el)
            else:
                if (is_cycleway or is_route or is_leisure_track) and not is_vehicle:
                    valid_path_elements.append(el)
                    
        if not valid_path_elements:
            print("Path Filtering: No elements matched 'Recreational Path' criteria.")
            return None
            
        print(f"Path Filtering: Found {len(valid_path_elements)} valid path segments.")
        result = {'elements': valid_path_elements}
        _osm_cache[query] = result
        # 写入 L2 供其他 worker 和重启后使用
        try:
            set_overpass_cache(query, result)
        except Exception:
            pass
        return result
        
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
        # Fallback for offline/dev
        return [
            {'id': 'S50', 'name': 'Clementi', 'location': {'latitude': 1.3337, 'longitude': 103.7768}},
            {'id': 'S109', 'name': 'Ang Mo Kio', 'location': {'latitude': 1.3764, 'longitude': 103.8492}},
            {'id': 'S24', 'name': 'Changi', 'location': {'latitude': 1.3678, 'longitude': 103.9826}},
             {'id': 'S104', 'name': 'Woodlands', 'location': {'latitude': 1.44387, 'longitude': 103.78538}},
            {'id': 'S100', 'name': 'Woodlands', 'location': {'latitude': 1.4172, 'longitude': 103.74855}}, # S100 is intermediate?
            {'id': 'S107', 'name': 'East Coast Parkway', 'location': {'latitude': 1.3135, 'longitude': 103.9625}},
            {'id': 'S115', 'name': 'Tuas South', 'location': {'latitude': 1.2937, 'longitude': 103.6182}},
            {'id': 'S111', 'name': 'Newton', 'location': {'latitude': 1.31055, 'longitude': 103.8365}},
             {'id': 'S116', 'name': 'West Coast', 'location': {'latitude': 1.281, 'longitude': 103.754}},
             {'id': 'S121', 'name': 'Choa Chu Kang', 'location': {'latitude': 1.37288, 'longitude': 103.72244}},
             {'id': 'S60', 'name': 'Sentosa', 'location': {'latitude': 1.25, 'longitude': 103.8279}}
        ]

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


