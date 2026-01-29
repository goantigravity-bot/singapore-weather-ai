import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
import torch
import pandas as pd
from typing import Optional
from datetime import datetime, timedelta
import os

# Import from predict.py
from predict import (
    load_system, 
    get_station_mapping, 
    find_sensor_id, 
    get_input_data, 
    find_nearest_n_sensors,
    reverse_geocode,
    geocode_location,
    fetch_osm_path,
    process_and_sample_path,
    DEVICE
)
import numpy as np

import sqlite3
from collections import Counter
import logging
from monitor_api import router as monitor_router

# Logger Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Singapore Weather AI API")

# 创建 API 路由器
# 所有路由都会注册在根路径和 /api 前缀下，以支持：
# - 本地开发：直接访问 http://localhost:8000/predict
# - CloudFront 生产环境：通过 /api/predict 访问
api_router = APIRouter()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database Setup
def init_db():
    conn = sqlite3.connect('weather.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            ip_address TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

class SearchLog(BaseModel):
    query: str

# --- S3 Config for Training status ---
S3_BUCKET = os.environ.get("S3_BUCKET", None)
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", None)

@api_router.get("/training/status")
def get_training_status():
    """Fetch current training state from S3"""
    if not S3_BUCKET:
        return {"status": "unknown", "message": "S3_BUCKET not configured"}
    
    try:
        import boto3
        import json
        s3 = boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)
        obj = s3.get_object(Bucket=S3_BUCKET, Key="state/training_state.json")
        data = json.loads(obj['Body'].read().decode('utf-8'))
        return data
    except Exception as e:
        # If file not found or other error, return idle/unknown
        logger.warning(f"Failed to fetch training status: {e}")
        return {"status": "idle", "message": str(e)}

@api_router.get("/training/history")
def get_training_history():
    """Fetch training history from S3"""
    if not S3_BUCKET:
        return []
        
    try:
        import boto3
        import json
        s3 = boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)
        obj = s3.get_object(Bucket=S3_BUCKET, Key="history/training_history.json")
        data = json.loads(obj['Body'].read().decode('utf-8'))
        return data
    except Exception as e:
        logger.warning(f"Failed to fetch history: {e}")
        return []


# Global variables to hold model and data
model = None
df = None
stations_meta = []
MAX_RADIUS_KM = 10.0  # limit for spatial correlation

@app.on_event("startup")
def startup_event():
    global model, df, stations_meta
    logger.info("API Startup: Loading Model and Data...")
    try:
        model, df = load_system()
        model.eval()
        stations_meta = get_station_mapping()
        logger.info("API Startup: Success.")
    except Exception as e:
        logger.error(f"API Startup Failed: {e}")

@api_router.get("/health")
def health_check():
    if model is None:
        return {"status": "error", "message": "Model not loaded"}
    return {"status": "ok"}

@api_router.get("/stations")
def get_stations():
    global stations_meta
    return stations_meta

@api_router.post("/log-search")
def log_search(log: SearchLog, request: Request):
    try:
        # 获取客户端IP地址
        # 优先使用X-Forwarded-For（如果经过代理）
        client_ip = request.headers.get("X-Forwarded-For")
        if client_ip:
            # X-Forwarded-For可能包含多个IP，取第一个
            client_ip = client_ip.split(",")[0].strip()
        else:
            # 否则使用直接连接的IP
            client_ip = request.client.host if request.client else None
        
        conn = sqlite3.connect('weather.db')
        c = conn.cursor()
        c.execute(
            "INSERT INTO search_history (query, ip_address) VALUES (?, ?)",
            (log.query, client_ip)
        )
        conn.commit()
        conn.close()
        logger.info(f"Search logged: '{log.query}' from IP: {client_ip}")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error logging search: {e}")
        return {"status": "error", "message": str(e)}

@api_router.get("/popular-searches")
def get_popular_searches():
    try:
        conn = sqlite3.connect('weather.db')
        c = conn.cursor()
        # Get all queries
        c.execute("SELECT query FROM search_history")
        rows = c.fetchall()
        conn.close()
        
        # Count frequencies
        queries = [r[0] for r in rows if r[0].strip()]
        counts = Counter(queries)
        
        # Return top 6 most common
        popular = [{"name": q, "count": c} for q, c in counts.most_common(6)]
        
        # If DB is empty, return defaults
        if not popular:
            return []
            
        return popular
    except Exception as e:
        logger.error(f"Error fetching popular searches: {e}")
        return []

@api_router.get("/predict/path")
def predict_weather_path(
    query: str = Query(..., description="Name of the landmark or path (e.g. 'Rail Corridor')")
):
    global model, df, stations_meta
    
    if model is None:
        raise HTTPException(status_code=503, detail="System not ready")

    logger.info(f"Path Prediction Request for: {query}")
    
    # 1. Fetch Path Logic
    path_data = fetch_osm_path(query)
    if not path_data:
        raise HTTPException(status_code=404, detail=f"Could not fetch path data for '{query}' from OpenStreetMap (Overpass)")
        
    # 2. Sample Points
    samples = process_and_sample_path(path_data, sample_dist_km=2.0)
    logger.info(f"Sampled {len(samples)} points along path.")
    
    if not samples:
        raise HTTPException(status_code=404, detail=f"Path found but geometry extraction failed or path is too short.")
        
    results = []
    
    # 3. Predict for each point (Reuse predict logic by calling internal helper if separated, 
    # or just replicate simplified flow here). 
    # We'll use a simplified flow to avoid overhead of full 'predict_weather' call which does extra arg parsing.
    
    # Common Time Setup
    now = datetime.now()
    minute_floored = (now.minute // 10) * 10
    now = now.replace(minute=minute_floored, second=0, microsecond=0)
    max_ts = df['timestamp'].max()
    ref_date = max_ts.date() - timedelta(days=1)
    target_query_time = datetime.combine(ref_date, now.time())
    if df['timestamp'].dt.tz is not None:
        target_query_time = pd.Timestamp(target_query_time).tz_localize(df['timestamp'].dt.tz)
    last_ts = target_query_time
    
    # Reuse the IDW helper inside this scope or move it to global scope. 
    # For now, duplicate or move. Let's move it to global scope later, but for speed, duplicate small helper.
    def calculate_idw(values, distances, power=2):
        if not values or not distances: return None
        if len(values) == 1: return values[0]
        for v, d in zip(values, distances):
            if d < 0.1: return v
        weights = [1.0 / (d**power) for d in distances]
        weighted_sum = sum(v * w for v, w in zip(values, weights))
        return weighted_sum / sum(weights)
        
    for i, pt in enumerate(samples):
        lat, lon = pt[0], pt[1]
        
        # Determine Target Sensors (3 nearest)
        target_sensors = find_nearest_n_sensors(lat, lon, stations_meta, n=3)
        # Filter out sensors that are too far to be reliable
        target_sensors = [s for s in target_sensors if s[1] <= MAX_RADIUS_KM]
        
        if not target_sensors: continue
        
        # Predict Rain
        rain_preds = []
        temp_values = []
        hum_values = []
        valid_distances = []
        
        primary_id = target_sensors[0][0]
        
        for sid, dist in target_sensors:
            sat_in, sensor_in = get_input_data(df, sid, last_ts)
            
            # Fallback
            if sat_in is None:
                 try:
                     nearest_valid = df[df['sensor_id'] == sid]['timestamp']
                     deltas = abs(nearest_valid - last_ts)
                     closest_ts = nearest_valid.iloc[deltas.argmin()]
                     sat_in, sensor_in = get_input_data(df, sid, closest_ts)
                 except: pass
            
            if sat_in is not None and sensor_in is not None:
                with torch.no_grad():
                    pred = model(sat_in.to(DEVICE), sensor_in.to(DEVICE)).item()
                    rain_preds.append(pred)
                    
            # Current Readings
            try:
                sensor_data = df[df['sensor_id'] == sid]
                relevant = sensor_data[sensor_data['timestamp'] <= last_ts].sort_values('timestamp')
                if not relevant.empty:
                    rec = relevant.iloc[-1]
                    temp_values.append(float(rec['temperature']))
                    hum_values.append(float(rec['humidity']))
                    if sat_in is not None:
                        valid_distances.append(dist)
            except: pass
            
        # Aggregate
        min_len = min(len(rain_preds), len(temp_values), len(hum_values), len(valid_distances))
        
        final_rain = 0.0
        desc = "No Data"
        
        if min_len > 0:
            v_dists = valid_distances[:min_len]
            final_rain = calculate_idw(rain_preds[:min_len], v_dists)
            final_temp = calculate_idw(temp_values[:min_len], v_dists)
            final_hum = calculate_idw(hum_values[:min_len], v_dists)
            
            if final_rain >= 2.0: desc = "Heavy Rain"
            elif final_rain >= 0.1: desc = "Light Rain"
            else: desc = "Clear"
            
            results.append({
                "lat": lat,
                "lon": lon,
                "forecast": {
                    "rainfall": round(final_rain, 4),
                    "description": desc,
                    "temperature": round(final_temp, 1) if final_temp else None
                }
            })
            
    return {
        "query": query,
        "points": results
    }

@api_router.get("/predict")
def predict_weather(
    location: Optional[str] = Query(None, description="Location name or address"),
    lat: Optional[float] = Query(None, description="Latitude"),
    lon: Optional[float] = Query(None, description="Longitude")
):
    global model, df, stations_meta
    
    if model is None:
        raise HTTPException(status_code=503, detail="System not ready")

    # Determine Target time (Simulate Real-Time)
    # 1. Get current real time
    now = datetime.now()
    
    # 1.5 Floor to nearest 10 minutes (Logic requested by user)
    # e.g. 15:37 -> 15:30
    minute_floored = (now.minute // 10) * 10
    now = now.replace(minute=minute_floored, second=0, microsecond=0)
    
    # 2. Find a reference day in DB (e.g. the last available day)
    # We want to map "Now" -> "Reference Day @ Same Time"
    max_ts = df['timestamp'].max()
    ref_date = max_ts.date()
    
    # If the dataset ends at midnight, using that exact date might result in future times missing.
    # Safe bet: Go back 1 day from the absolute max to ensure full 24h coverage.
    ref_date = ref_date - timedelta(days=1)
    
    # 3. Construct Query Time
    target_query_time = datetime.combine(ref_date, now.time())
    
    # 4. Ensure timezone awareness if DF is aware (it usually is UTC+8 from predict.py loading)
    if df['timestamp'].dt.tz is not None:
        target_query_time = pd.Timestamp(target_query_time).tz_localize(df['timestamp'].dt.tz)
    
    logger.info(f"Simulating Live Data: Real Time {now} -> Mapped to History {target_query_time}")

    last_ts = target_query_time
    
    target_sensor_id = None
    dist_km = None
    station_name = "Unknown"
    
    # NEW: List to hold multiple sensors for interpolation
    target_sensors = [] # List of (id, distance_km)

    # Logic to find sensor(s)
    if lat is not None and lon is not None:
        # Coords provided -> Find 3 nearest
        target_sensors = find_nearest_n_sensors(lat, lon, stations_meta, n=3)
        
        # REVERSE GEOCODE: Get the actual name of the clicked point
        real_name = reverse_geocode(lat, lon)
        if real_name:
            station_name = real_name # Overwrite "Unknown"
            
    elif location:
        # Location Name provided -> Resolve to 1 sensor (old logic) or geocode then find 3
        # For simplicity, if location is a name, we map to single nearest for now, OR geocode.
        # Let's try to Geocode first to get coords for IDW
        glat, glon = geocode_location(location)
        if glat and glon:
             target_sensors = find_nearest_n_sensors(glat, glon, stations_meta, n=3)
        else:
             # Fallback to single sensor lookup
             sid = find_sensor_id(location, df, stations_meta)
             if sid:
                 target_sensors = [(sid, 0.0)] # 0 distance implies exact match
             else:
                 raise HTTPException(status_code=404, detail=f"Location '{location}' not found")
    else:
        raise HTTPException(status_code=400, detail="Must provide 'location' OR 'lat' and 'lon'")
    
    # Detailed Log for Sensor Selection
    logger.info(f"Initial Nearest Sensors for query: {[f'{s[0]} ({s[1]:.2f}km)' for s in target_sensors]}")

    # Filter out sensors that are too far
    filtered_sensors = [s for s in target_sensors if s[1] <= MAX_RADIUS_KM]
    
    if len(filtered_sensors) < len(target_sensors):
        logger.warning(f"Filtered out {len(target_sensors) - len(filtered_sensors)} sensors > {MAX_RADIUS_KM}km")
        
    target_sensors = filtered_sensors
    
    if not target_sensors:
        logger.warning(f"No sensors found within {MAX_RADIUS_KM}km range.")
        raise HTTPException(status_code=404, detail=f"No sensors found within {MAX_RADIUS_KM}km. Data may be unreliable.")

    # --- IDW CALCULATION HELPER ---
    def calculate_idw(values, distances, power=2):
        """
        values: list of float values
        distances: list of float distances
        """
        if not values or not distances: return None
        if len(values) == 1: return values[0]
        
        # Check for exact match (dist ~= 0)
        for v, d in zip(values, distances):
            if d < 0.1: # Within 100m
                return v
        
        # Calculate weights
        weights = [1.0 / (d**power) for d in distances]
        sum_weights = sum(weights)
        
        weighted_sum = sum(v * w for v, w in zip(values, weights))
        return weighted_sum / sum_weights

    # --- COLLECT DATA FROM SENTORS ---
    temp_values = []
    hum_values = []
    pm25_values = []
    rain_preds = []
    valid_distances = []
    
    primary_station_name = ""
    
    logger.info(f"Interpolating using {len(target_sensors)} stations.")
    
    for i, (sid, dist) in enumerate(target_sensors):
        # Get metadata name for the closest one
        if i == 0:
            for s in stations_meta:
                 if s['id'] == sid:
                     primary_station_name = s.get('name', sid)
                     break
        
        # 1. Fetch History & Prediction Inputs
        sat_in, sensor_in = get_input_data(df, sid, last_ts)
        
        # Fallback logic if exact time missing
        if sat_in is None or sensor_in is None:
             try:
                 nearest_valid = df[df['sensor_id'] == sid]['timestamp']
                 deltas = abs(nearest_valid - last_ts)
                 closest_ts = nearest_valid.iloc[deltas.argmin()]
                 sat_in, sensor_in = get_input_data(df, sid, closest_ts)
             except:
                 pass
        
        if sat_in is not None and sensor_in is not None:
            # Predict Rain
            with torch.no_grad():
                pred = model(sat_in.to(DEVICE), sensor_in.to(DEVICE)).item()
                rain_preds.append(pred)
        
        # 2. Fetch Current Readings (Temp/Hum)
        try:
            sensor_data = df[df['sensor_id'] == sid]
            if not sensor_data.empty:
                relevant = sensor_data[sensor_data['timestamp'] <= last_ts].sort_values('timestamp')
                if not relevant.empty:
                    rec = relevant.iloc[-1]
                    t = float(rec['temperature'])
                    h = float(rec['humidity'])
                    p = float(rec.get('pm25', 0.0))
                    temp_values.append(t)
                    hum_values.append(h)
                    pm25_values.append(p)
                    
                    # Only add distance if we successfully got data
                    # (Assuming rain pred success usually implies data exists, but need to align lists)
                    # Ideally we align lists perfectly. For prototype, we sync 'valid_distances' to 'temp_values'
                    # But rain_preds might differ.
                    # Let's clean this up: Only add to lists if ALL data available
                    if sat_in is not None and sensor_in is not None:
                        valid_distances.append(dist)
                    else:
                        # Convert partial failures? 
                        # If rain failed, we skip this station entirely for simplicity
                        if len(rain_preds) > len(valid_distances): 
                             rain_preds.pop()
                        if len(temp_values) > len(valid_distances):
                             temp_values.pop()
                             hum_values.pop()
                             pm25_values.pop()
        except Exception:
            pass

    # --- AGGREGATE RESULTS ---
    
    # Use valid_distances for weighting
    # If list lengths mismatch (rare), truncate to min length
    min_len = min(len(rain_preds), len(temp_values), len(hum_values), len(pm25_values), len(valid_distances))
    
    final_rain = 0.0
    final_temp = None
    final_hum = None
    final_pm25 = None
    
    if min_len > 0:
        # Slice to sync
        v_dists = valid_distances[:min_len]
        v_rain = rain_preds[:min_len]
        v_temp = temp_values[:min_len]
        v_hum = hum_values[:min_len]
        v_pm25 = pm25_values[:min_len]
        
        final_rain = calculate_idw(v_rain, v_dists)
        final_temp = calculate_idw(v_temp, v_dists)
        final_hum = calculate_idw(v_hum, v_dists)
        final_pm25 = calculate_idw(v_pm25, v_dists)
        
        final_temp = round(final_temp, 1)
        final_hum = round(final_hum, 1)
        final_pm25 = round(final_pm25, 0)
        
        logger.info(f"Prediction Result -- Rain: {final_rain:.4f} | Temp: {final_temp} | Hum: {final_hum} | PM2.5: {final_pm25}")
    else:
        # Fallback to single closest if everything failed (shouldn't happen with valid fallback logic)
        raise HTTPException(status_code=500, detail="Failed to aggregate data from any station")
        
    # Interpretation
    desc = "Clear / No Rain"
    if final_rain >= 2.0: desc = "Heavy Rain / Storm"
    elif final_rain >= 0.1: desc = "Light Rain"

    # Display Name
    display_name = primary_station_name
    
    # If we have a specific geocoded name (from lat/lon logic), use it
    if station_name != "Unknown":
        display_name = station_name
    elif len(target_sensors) > 1 and valid_distances[0] > 0.5:
        # If we interpolated and aren't super close to the primary, and didn't have a specific name
        display_name = f"{primary_station_name} (Area)"

    return {
        "timestamp": now, # Return CURRENT REAL TIME to User
        "location_query": location if location else f"{lat},{lon}",
        "nearest_station": {
            "id": target_sensors[0][0], # Closest ID
            "name": display_name
        },
        "contributing_stations": [s[0] for s in target_sensors], # List of IDs used for IDW
        "forecast": {
            "rainfall_mm_next_10min": round(final_rain, 4),
            "description": desc
        },
        "current_weather": {
            "temperature": final_temp,
            "humidity": final_hum,
            "pm25": final_pm25
        }
    }

# 注册路由器：同时支持根路径和 /api 前缀
# - 根路径：本地开发使用 http://localhost:8000/predict
# - /api 前缀：CloudFront 代理使用 https://xxx.cloudfront.net/api/predict
app.include_router(api_router)  # 根路径
app.include_router(api_router, prefix="/api")  # /api 前缀

# 注册监控仪表盘路由 /monitor/*
app.include_router(monitor_router)

# --- 静态文件服务（前端）---
# 自动检测前端构建目录，支持开发环境和生产环境
FRONTEND_DIR = Path(__file__).parent / "frontend" / "dist"

if FRONTEND_DIR.exists():
    # 挂载静态资源目录（JS/CSS/图片等）
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
    
    # SPA fallback：所有未匹配的路由返回 index.html
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Handle SPA routing by serving index.html for all unmatched routes"""
        # 如果是 API 路径，让 FastAPI 处理
        if full_path.startswith(("api/", "docs", "openapi.json", "health", "stations", "predict", "log-search", "popular-searches", "training", "monitor")):
            raise HTTPException(status_code=404, detail="Not found")
        
        # 检查是否是静态文件请求
        static_file = FRONTEND_DIR / full_path
        if static_file.exists() and static_file.is_file():
            return FileResponse(static_file)
        
        # 返回 index.html 支持 SPA 路由
        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        
        raise HTTPException(status_code=404, detail="Not found")
    
    logger.info(f"Frontend static files mounted from: {FRONTEND_DIR}")
else:
    logger.warning(f"Frontend directory not found: {FRONTEND_DIR} - Static file serving disabled")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
