import uvicorn
from fastapi import FastAPI, HTTPException, Query
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

app = FastAPI(title="Singapore Weather AI API")

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
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
