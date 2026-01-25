import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import torch
import pandas as pd
from typing import Optional
from datetime import datetime, timedelta

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

# Logger Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Singapore Weather AI API")

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
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

class SearchLog(BaseModel):
    query: str


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

@app.get("/health")
def health_check():
    if model is None:
        return {"status": "error", "message": "Model not loaded"}
    return {"status": "ok"}

@app.get("/stations")
def get_stations():
    global stations_meta
    return stations_meta

@app.post("/log-search")
def log_search(log: SearchLog):
    try:
        conn = sqlite3.connect('weather.db')
        c = conn.cursor()
        c.execute("INSERT INTO search_history (query) VALUES (?)", (log.query,))
        conn.commit()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error logging search: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/popular-searches")
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

@app.get("/predict/path")
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

@app.get("/predict")
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
                    temp_values.append(t)
                    hum_values.append(h)
                    
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
        except Exception:
            pass

    # --- AGGREGATE RESULTS ---
    
    # Use valid_distances for weighting
    # If list lengths mismatch (rare), truncate to min length
    min_len = min(len(rain_preds), len(temp_values), len(hum_values), len(valid_distances))
    
    final_rain = 0.0
    final_temp = None
    final_hum = None
    
    if min_len > 0:
        # Slice to sync
        v_dists = valid_distances[:min_len]
        v_rain = rain_preds[:min_len]
        v_temp = temp_values[:min_len]
        v_hum = hum_values[:min_len]
        
        final_rain = calculate_idw(v_rain, v_dists)
        final_temp = calculate_idw(v_temp, v_dists)
        final_hum = calculate_idw(v_hum, v_dists)
        
        final_temp = round(final_temp, 1)
        final_hum = round(final_hum, 1)
        
        logger.info(f"Prediction Result -- Rain: {final_rain:.4f} | Temp: {final_temp} | Hum: {final_hum}")
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
            "humidity": final_hum
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
