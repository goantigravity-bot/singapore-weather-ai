import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import torch
import pandas as pd
from typing import Optional
from datetime import datetime

# Import from predict.py
from predict import (
    load_system, 
    get_station_mapping, 
    find_sensor_id, 
    get_input_data, 
    find_nearest_sensor,
    geocode_location,
    DEVICE
)

import sqlite3
from collections import Counter

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

@app.on_event("startup")
def startup_event():
    global model, df, stations_meta
    print("API Startup: Loading Model and Data...")
    try:
        model, df = load_system()
        model.eval()
        stations_meta = get_station_mapping()
        print("API Startup: Success.")
    except Exception as e:
        print(f"API Startup Failed: {e}")

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
        print(f"Error logging search: {e}")
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
        print(f"Error fetching popular searches: {e}")
        return []

@app.get("/predict")
def predict_weather(
    location: Optional[str] = Query(None, description="Location name or address"),
    lat: Optional[float] = Query(None, description="Latitude"),
    lon: Optional[float] = Query(None, description="Longitude")
):
    global model, df, stations_meta
    
    if model is None:
        raise HTTPException(status_code=503, detail="System not ready")

    # Determine Target time (Latest in DB for demo, Real-time in prod)
    last_ts = df['timestamp'].max()
    
    target_sensor_id = None
    dist_km = None
    station_name = "Unknown"

    # Logic to find sensor
    if lat is not None and lon is not None:
        # Coords provided
        target_sensor_id = find_nearest_sensor(lat, lon, stations_meta)
        if not target_sensor_id:
            raise HTTPException(status_code=404, detail="No suitable sensor found near coordinates")
            
    elif location:
        # Location Name provided
        # We need to replicate find_sensor_id logic but extract more info
        # Reuse find_sensor_id for simplicity, but it prints logs.
        target_sensor_id = find_sensor_id(location, df, stations_meta)
        
        if not target_sensor_id:
             raise HTTPException(status_code=404, detail=f"Location '{location}' not found")
    else:
        raise HTTPException(status_code=400, detail="Must provide 'location' OR 'lat' and 'lon'")

    # Get Station Metadata for response
    # Recalculate distance if possible or lookup
    for s in stations_meta:
        if s['id'] == target_sensor_id:
            station_name = s.get('name', target_sensor_id)
            # If lat/lon provided, we could calc actual distance, but reusing logic ok.
            break

    # Run Prediction
    sat_in, sensor_in = get_input_data(df, target_sensor_id, last_ts)
    
    if sat_in is None or sensor_in is None:
         raise HTTPException(status_code=500, detail="Data missing for prediction (history or satellite)")
         
    with torch.no_grad():
        pred_val = model(sat_in.to(DEVICE), sensor_in.to(DEVICE)).item()

    # Retrieve current readings (Temperature/Humidity) from the input data or DF
    # We want the latest reading available for this sensor AT or BEFORE last_ts
    cur_temp = None
    cur_hum = None

    try:
        sensor_data = df[df['sensor_id'] == target_sensor_id]
        if not sensor_data.empty:
            # Sort by time
            relevant = sensor_data[sensor_data['timestamp'] <= last_ts].sort_values('timestamp')
            if not relevant.empty:
                latest_record = relevant.iloc[-1]
                cur_temp = float(latest_record['temperature'])
                cur_hum = float(latest_record['humidity'])
    except Exception as e:
        print(f"Error fetching current readings: {e}")

    # Interpretation
    desc = "Clear / No Rain"
    if pred_val >= 2.0: desc = "Heavy Rain / Storm"
    elif pred_val >= 0.1: desc = "Light Rain"

    return {
        "timestamp": last_ts,
        "location_query": location if location else f"{lat},{lon}",
        "nearest_station": {
            "id": target_sensor_id,
            "name": station_name
        },
        "forecast": {
            "rainfall_mm_next_10min": round(pred_val, 4),
            "description": desc
        },
        "current_weather": {
            "temperature": cur_temp,
            "humidity": cur_hum
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
