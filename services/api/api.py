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
    find_nearest_sensor,
    reverse_geocode,
    geocode_location,
    fetch_osm_path,
    process_and_sample_path,
    DEVICE,
    predict_ensemble
)
from smart_query import parse_query, analyze_path_weather, convert_numpy
import numpy as np

import sqlite3
import json
from collections import Counter
import db as weather_db
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
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            response_time_ms REAL,
            response_result TEXT
        )
    ''')
    conn.commit()
    conn.close()
    # 创建新的结构化表
    weather_db.create_tables()

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



# Background Sync
import threading
import time
import shutil
import glob
from datetime import datetime, timedelta

# --- S3 Config ---
S3_BUCKET = os.environ.get("S3_BUCKET", "weather-ai-models-de08370c") # Default fallback
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", None)
MODEL_KEY = "models/latest.pth"
DATA_KEY = "govdata/real_sensor_data.csv"
SYNC_INTERVAL = 300 # 5 minutes

def sync_satellite_data(s3, bucket):
    """Sync recent satellite data (Last 3 hours)"""
    # Logic: List and Download
    now_utc = datetime.utcnow()
    # Check current day and previous day (if near boundary)
    dates_to_check = [now_utc.date()]
    if now_utc.hour < 3:
        dates_to_check.append(now_utc.date() - timedelta(days=1))
    
    local_dir = "satellite_data"
    os.makedirs(local_dir, exist_ok=True)
    
    for d in dates_to_check:
        date_str = d.strftime("%Y%m%d") # S3 uses YYYYMMDD
        prefix = f"satellite/{date_str}/"
        try:
             # Limit to recent files? 
             # For simplicity, we sync the whole day's folder if feasible (~144 files/day * 5MB = 700MB)
             # Storage might fill up. Implement cleanup.
             objs = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
             if 'Contents' in objs:
                 for obj in objs['Contents']:
                     key = obj['Key']
                     filename = os.path.basename(key)
                     local_path = os.path.join(local_dir, filename)
                     
                     if not os.path.exists(local_path):
                          logger.info(f"⬇️ [API] Downloading satellite: {filename}")
                          s3.download_file(bucket, key, local_path)
                          
        except Exception as e:
            logger.warning(f"Error listing/downloading satellite: {e}")
            
    # Cleanup old files (> 6 hours)
    # TODO: Implement strict cleanup to avoid disk fill

def sync_assets_thread():
    """Background thread to sync model and data from S3"""
    import boto3
    from botocore.exceptions import ClientError
    
    logger.info("🔄 Sync thread started")
    
    while True:
        try:
            s3 = boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)
            
            # 0. Sync Satellite Data
            sync_satellite_data(s3, S3_BUCKET)
            
            # 1. Download Model
            local_model = "weather_fusion_model.pth"
            try:
                # Check ETag or LastModified to avoid redundant download?
                # For simplicity, we just download to temp and swap if successful
                s3.download_file(S3_BUCKET, MODEL_KEY, local_model + ".tmp")
                os.replace(local_model + ".tmp", local_model)
                logger.info("✅ Model synced from S3")
            except ClientError as e:
                logger.warning(f"Failed to sync model: {e}")
            except Exception as e:
                 logger.warning(f"Error syncing model: {e}")

            # 2. Download CSV
            local_csv = "real_sensor_data.csv"
            try:
                s3.download_file(S3_BUCKET, DATA_KEY, local_csv + ".tmp")
                os.replace(local_csv + ".tmp", local_csv)
                logger.info("✅ CSV Data synced from S3")
            except ClientError as e:
                 # Check 'govdata/real_sensor_data.csv' fallback?
                 try:
                     s3.download_file(S3_BUCKET, "govdata/real_sensor_data.csv", local_csv + ".tmp")
                     os.replace(local_csv + ".tmp", local_csv)
                     logger.info("✅ CSV Data synced from S3 (fallback path)")
                 except:
                     logger.warning(f"Failed to sync CSV data: {e}")

            # 3. Reload System
            # We reload simply by calling load_system again.
            # This might cause a brief spike in memory but is safe.
            global model, df, stations_meta
            logger.info("🔄 Reloading system components...")
            new_model, new_df = load_system()
            if new_model and new_df is not None:
                model = new_model
                df = new_df
                # Reload metadata mostly for station mapping logic
                stations_meta = get_station_mapping()
                logger.info("✅ System reloaded successfully.")
            else:
                 logger.warning("Reload returned empty model/df. Keeping old state.")

        except Exception as e:
             logger.error(f"Sync thread fatal error: {e}")
        
        time.sleep(SYNC_INTERVAL)

@app.on_event("startup")
def startup_event():
    global model, df, stations_meta
    logger.info("API Startup: Loading Model and Data...")
    
    # Start Sync Thread
    if S3_BUCKET:
        t = threading.Thread(target=sync_assets_thread, daemon=True)
        t.start()
    else:
        logger.warning("S3_BUCKET not set. Sync disabled.")

    try:
        model, df = load_system()
        if model: model.eval()
        stations_meta = get_station_mapping()
        logger.info("API Startup: Success.")
    except Exception as e:
        logger.error(f"API Startup Failed: {e}")

# --- Endpoints ---

@api_router.get("/health")
def health():
    return {"status": "ok", "version": "0.7.0", "service": "api"}

@api_router.get("/stations")
def get_stations():
    """Get list of available weather stations"""
    # Force reload if empty
    global stations_meta
    if not stations_meta:
        stations_meta = get_station_mapping()
        
    if not stations_meta:
        # Fallback to hardcoded list if API fails
        return [{"id": "S50", "name": "Clementi", "location": {"latitude": 1.3337, "longitude": 103.7768}}]
        
    return stations_meta

@api_router.get("/predict")
def predict_weather(
    request: Request,
    lat: Optional[float] = Query(None, description="Latitude"),
    lon: Optional[float] = Query(None, description="Longitude"),
    location: Optional[str] = Query(None, description="Location Name")
):
    """Predict weather at specific coordinates or location name"""
    global model, df
    
    # Check system readiness
    if model is None or df is None:
        model, df = load_system()
        if model is None:
            raise HTTPException(503, "Model not loaded. Service is starting up.")

    try:
        # Resolve Location
        if location and (lat is None or lon is None):
            lat, lon = geocode_location(location)
            if lat is None:
                 raise HTTPException(404, f"Could not locate '{location}'")
        
        _predict_start = time.time()
                 
        if lat is None or lon is None:
             raise HTTPException(422, "Must provide 'lat'/'lon' OR 'location'.")
             
        # Determine target time (Latest usually)
        target_time = df['timestamp'].max()
        
        # Use Ensemble Prediction
        raw = predict_ensemble(
            lat, lon, target_time, model, df, stations_meta, ensemble_size=3
        )
        
        if not raw:
             raise HTTPException(404, "Prediction failed (No sensors nearby or data missing)")
        
        # 查找最近的站点信息，用于前端显示
        nearest = find_nearest_sensor(lat, lon, stations_meta)
        nearest_name = location or "Unknown"
        if nearest and stations_meta:
            for s in stations_meta:
                if s['id'] == nearest:
                    nearest_name = s.get('name', nearest_name)
                    break
        
        # 获取该站点的最新观测数据
        current_temp = None
        current_humidity = None
        current_pm25 = None
        if nearest and not df.empty:
            sensor_df = df[df['sensor_id'] == nearest].sort_values('timestamp')
            if not sensor_df.empty:
                latest = sensor_df.iloc[-1]
                current_temp = float(latest.get('temperature', 0)) if 'temperature' in latest else None
                current_humidity = float(latest.get('humidity', 0)) if 'humidity' in latest else None
                current_pm25 = float(latest.get('pm25', 0)) if 'pm25' in latest else None
        
        # 生成建议文本
        rain = raw.get('rainfall', 0.0)
        if rain < 0.1:
            recommendation = "Good conditions for outdoor activities."
            status_color = "green"
        elif rain < 2.0:
            recommendation = "Light rain expected. Bring an umbrella."
            status_color = "yellow"
        else:
            recommendation = "Heavy rain likely. Seek shelter."
            status_color = "red"
        
        # 适配前端 ForecastResult 接口结构
        response = {
            "timestamp": target_time.isoformat(),
            "location_query": location or f"{lat},{lon}",
            "nearest_station": {
                "id": nearest or "unknown",
                "name": nearest_name,
            },
            "contributing_stations": raw.get('contributing_sensors', []),
            "forecast": {
                "rainfall_mm_next_10min": rain,
                "description": raw.get('status', 'Unknown'),
            },
            "current_weather": {
                "temperature": current_temp,
                "humidity": current_humidity,
                "pm25": current_pm25,
            },
            "confidence": raw.get('confidence', 0.5),
            "cloud_cover": raw.get('cloud_cover', False),
            "recommendation": recommendation,
            "status_color": status_color,
            "debug": raw.get('debug', ''),
        }
        
        # 记录搜索历史与结构化预测结果
        if location:
            elapsed_ms = (time.time() - _predict_start) * 1000
            client_ip = request.client.host if request.client else None

            # 旧表：保留兼容
            try:
                result_summary = json.dumps({
                    'rainfall': rain,
                    'description': raw.get('status', ''),
                    'temperature': current_temp,
                    'humidity': current_humidity,
                    'recommendation': recommendation
                }, ensure_ascii=False)
                conn = sqlite3.connect('weather.db')
                c = conn.cursor()
                c.execute(
                    "INSERT INTO search_history (query, ip_address, response_time_ms, response_result) VALUES (?, ?, ?, ?)",
                    (location, client_ip, round(elapsed_ms, 1), result_summary)
                )
                conn.commit()
                conn.close()
            except Exception as db_err:
                logger.warning(f"search_history write failed: {db_err}")

            # 新表：结构化存储（独立 try，不受旧表影响）
            try:
                query_id = weather_db.save_user_activity(
                    query=location,
                    response_time_ms=round(elapsed_ms, 1),
                    forecast_outcome=recommendation,
                    ip_address=client_ip
                )
                place_id = weather_db.get_or_create_place(
                    place_name=location, place_type="point",
                    center_lat=lat, center_lon=lon
                )
                loc_ids = weather_db.save_locations_for_place(place_id, [(lat, lon)])
                weather_db.save_forecast_results(query_id, [{
                    "loc_id": loc_ids[0],
                    "rainfall_mm": rain,
                    "status": raw.get('status', 'Unknown'),
                    "confidence": raw.get('confidence', 0.5),
                    "is_risky": rain >= 2.0,
                    "response_time_ms": round(elapsed_ms, 1),
                    "forecast_time": target_time.isoformat(),
                }])
            except Exception as db_err:
                logger.warning(f"Structured DB write failed: {db_err}")
        
        return response
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(500, f"Analysis failed: {e}")

@api_router.get("/predict/path")
def predict_path(query: str):
    """Analyze weather along a path (e.g. Rail Corridor)"""
    global model, df, stations_meta
    
    # Check system readiness
    if model is None: model, df = load_system()
    if not stations_meta: stations_meta = get_station_mapping()
    
    try:
        # Re-use analyze_path_weather from smart_query logic
        # Default Params
        start_hour = datetime.now().hour
        end_hour = min(23, start_hour + 2)
        tolerance = 0.5 # Default Medium
        
        # If query has time info, parsing it would be better.
        # But /predict/path usually implies "Check this path now".
        # We can use parse_query just for time extraction?
        parsed = parse_query(query) 
        # parsed['location'] might be different if query is complex.
        # But if query="Rail Corridor", parsed['location']="Rail Corridor".
        
        result = analyze_path_weather(
            parsed['location'] or query,
            parsed['start_hour'],
            parsed['end_hour'],
            parsed['tolerance'],
            model, df, stations_meta
        )
        
        # Inject parsed metadata for Frontend
        result['parsed'] = parsed
        
        return result
        
    except Exception as e:
        logger.error(f"Path prediction failed: {e}")
        raise HTTPException(500, f"Path Analysis failed: {e}")

@api_router.get("/smart-query")
def smart_query_endpoint(q: str, request: Request):
    """Process natural language query."""
    global model, df, stations_meta
    
    try:
        _sq_start = time.time()
        
        # 2. Parse
        parsed = parse_query(q)
        
        # 3. Analyze
        # ensure loaded
        global model, df, stations_meta
        if not model: model, df = load_system()
        if not stations_meta: stations_meta = get_station_mapping()
        
        result = analyze_path_weather(
            parsed['location'],
            parsed['start_hour'],
            parsed['end_hour'],
            parsed['tolerance'],
            model, df, stations_meta
        )
        
        # Inject parsed metadata for Frontend
        result['parsed'] = parsed
        
        # 记录搜索历史 + 结构化存储
        elapsed_ms = (time.time() - _sq_start) * 1000
        client_ip = request.client.host if request.client else None

        # 旧表：保留兼容
        try:
            result_summary = json.dumps({
                'location': parsed.get('location', ''),
                'advice': result.get('advice', ''),
                'overall_risk': result.get('overall_risk', '')
            }, ensure_ascii=False)
            conn = sqlite3.connect('weather.db')
            c = conn.cursor()
            c.execute(
                "INSERT INTO search_history (query, ip_address, response_time_ms, response_result) VALUES (?, ?, ?, ?)",
                (q, client_ip, round(elapsed_ms, 1), result_summary)
            )
            conn.commit()
            conn.close()
        except Exception as db_err:
            logger.warning(f"search_history write failed: {db_err}")

        # 新表：结构化存储（独立 try）
        try:
            forecast_outcome = result.get('recommendation', 'Unknown')
            query_id = weather_db.save_user_activity(
                query=q,
                response_time_ms=round(elapsed_ms, 1),
                forecast_outcome=forecast_outcome,
                ip_address=client_ip
            )

            # 保存活动
            weather_db.save_activity(
                query_id=query_id,
                activity_name=parsed.get('activity', 'General Activity'),
                rain_tolerance=parsed.get('tolerance')
            )

            # 保存地点和坐标
            location_name = parsed.get('location', 'Singapore')
            details = result.get('details', [])
            place_type = 'path' if len(details) > 1 else 'point'
            center_lat = details[0]['lat'] if details else None
            center_lon = details[0]['lon'] if details else None
            place_id = weather_db.get_or_create_place(
                place_name=location_name, place_type=place_type,
                center_lat=center_lat, center_lon=center_lon
            )

            # 保存各点坐标
            if details:
                points = [{"lat": d['lat'], "lon": d['lon'], "point_index": d.get('point_index', i+1)}
                          for i, d in enumerate(details)]
                loc_ids = weather_db.save_locations_for_place(place_id, points)

                # 保存各点的预测结果
                forecast_records = []
                for i, d in enumerate(details):
                    forecast_records.append({
                        "loc_id": loc_ids[i],
                        "rainfall_mm": d.get('rainfall', 0),
                        "status": d.get('status', 'Unknown'),
                        "confidence": None,
                        "is_risky": d.get('is_risky', False),
                        "response_time_ms": round(elapsed_ms / max(len(details), 1), 1),
                        "forecast_time": datetime.now().isoformat(),
                    })
                weather_db.save_forecast_results(query_id, forecast_records)

        except Exception as db_err:
            logger.warning(f"Structured DB write failed: {db_err}")
        
        return result
    except Exception as e:
        logger.error(f"Smart query failed: {e}")
        raise HTTPException(500, str(e))

@api_router.get("/popular-searches")
def get_popular_searches():
    # 默认新加坡热门地点（当搜索历史为空时使用）
    DEFAULT_PLACES = [
        {"id": 0, "name": "Marina Bay Sands", "count": 50},
        {"id": 1, "name": "Sentosa", "count": 45},
        {"id": 2, "name": "Orchard Road", "count": 40},
        {"id": 3, "name": "Changi Airport", "count": 35},
        {"id": 4, "name": "Jurong East", "count": 30},
        {"id": 5, "name": "Ang Mo Kio", "count": 25},
        {"id": 6, "name": "Tampines", "count": 20},
        {"id": 7, "name": "Woodlands", "count": 15},
    ]
    try:
        conn = sqlite3.connect('weather.db')
        c = conn.cursor()
        c.execute("SELECT query, COUNT(*) as count FROM search_history GROUP BY query ORDER BY count DESC LIMIT 8")
        rows = c.fetchall()
        conn.close()
        if rows:
            return [{"id": i, "name": r[0], "count": r[1]} for i, r in enumerate(rows)]
        # 无搜索历史时返回默认热门地点
        return DEFAULT_PLACES
    except Exception as e:
        logger.warning(f"Failed to fetch popular searches: {e}")
        return DEFAULT_PLACES

# --- Training Monitor Endpoints ---
# 从 S3 读取真实的 download_state.json 和 training_state.json 以展示实时进度
@api_router.get("/monitor/overview")
def monitor_overview():
    """返回当前系统运行概览，匹配前端 OverviewStatus 接口"""
    import json as _json
    import boto3
    
    # 统一格式化时间到秒级，去除微秒和时区后缀
    def fmt_time(iso_str):
        if not iso_str:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return iso_str[:19].replace("T", " ")
    
    csv_exists = os.path.exists("real_sensor_data.csv")
    model_exists = os.path.exists("weather_fusion_model.pth")
    
    # --- 1. 从 S3 获取真实状态 ---
    download_state = {}
    training_state = {}
    s3_satellite_dates = set()
    s3_total_files = 0
    
    if S3_BUCKET:
        try:
            s3 = boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)
            logger.info(f"Monitor: Reading S3 state from bucket={S3_BUCKET}, endpoint={S3_ENDPOINT_URL}")
            
            # 读取 download_state.json
            try:
                obj = s3.get_object(Bucket=S3_BUCKET, Key="state/download_state.json")
                download_state = _json.loads(obj['Body'].read().decode('utf-8'))
                logger.info(f"Monitor: download_state loaded: {download_state.get('status')}")
            except Exception as e:
                logger.warning(f"Monitor: Failed to read download_state.json: {e}")
            
            # 读取 training_state.json
            try:
                obj = s3.get_object(Bucket=S3_BUCKET, Key="state/training_state.json")
                training_state = _json.loads(obj['Body'].read().decode('utf-8'))
                logger.info(f"Monitor: training_state loaded: batches={training_state.get('completedBatches')}")
            except Exception as e:
                logger.warning(f"Monitor: Failed to read training_state.json: {e}")
            
            # 统计 S3 中卫星数据的日期目录和文件数
            try:
                paginator = s3.get_paginator('list_objects_v2')
                for page in paginator.paginate(Bucket=S3_BUCKET, Prefix="satellite/", Delimiter="/"):
                    for prefix in page.get('CommonPrefixes', []):
                        date_str = prefix['Prefix'].replace("satellite/", "").rstrip("/")
                        if date_str:
                            s3_satellite_dates.add(date_str)
                s3_total_files = len(s3_satellite_dates) * 144
                logger.info(f"Monitor: Found {len(s3_satellite_dates)} satellite date folders")
            except Exception as e:
                logger.warning(f"Monitor: Failed to list satellite dates: {e}")
        except Exception as e:
            logger.warning(f"Monitor: Failed to create S3 client: {e}")
    else:
        logger.warning("Monitor: S3_BUCKET is not set, returning local-only data")
    
    completed_days = len(s3_satellite_dates)
    
    # --- 2. 构建下载状态 ---
    download_status = {
        "currentDate": download_state.get("current_target_date"),
        "completedDays": completed_days,
        "totalDays": max(completed_days, 120),  # 目标约 120 天的历史数据
        "filesDownloaded": s3_total_files,
        "status": download_state.get("status", "idle"),
        "lastUpdate": fmt_time(download_state.get("last_updated")),
        "dateProgress": [],
    }
    
    # 为已完成的日期生成进度条目
    for date_str in sorted(s3_satellite_dates)[-10:]:  # 最近 10 天
        download_status["dateProgress"].append({
            "date": date_str,
            "satelliteFiles": 144,
            "satelliteTotal": 144,
            "neaFiles": 1,
            "neaTotal": 1,
            "status": "completed",
        })
    
    # --- 3. 构建训练状态（直接使用 S3 中的 training_state.json）---
    # 翻译中文 phase 名称为英文（前端使用英文）
    phase_name_map = {"下载数据": "Data Download", "预处理": "Preprocessing", "训练": "Training", "同步模型": "Model Sync"}
    raw_phases = training_state.get("phases", [])
    translated_phases = []
    for p in raw_phases:
        translated_phases.append({
            "name": phase_name_map.get(p.get("name", ""), p.get("name", "")),
            "status": p.get("status", "pending"),
        })
    # 如果 S3 无数据，给默认值
    if not translated_phases:
        translated_phases = [
            {"name": "Data Download", "status": "completed" if csv_exists else "pending"},
            {"name": "Training", "status": "completed" if model_exists else "pending"},
            {"name": "Model Sync", "status": "completed" if model_exists else "pending"},
        ]
    
    training_status = {
        "currentDate": training_state.get("currentDate"),
        "completedBatches": training_state.get("completedBatches", 0),
        "totalEpochs": training_state.get("totalEpochs", 0),
        "currentPhase": training_state.get("currentPhase", "idle"),
        "phases": translated_phases,
        "status": training_state.get("status", "completed" if model_exists else "idle"),
        "lastUpdate": fmt_time(training_state.get("lastUpdate")),
        "history": [],
    }
    
    # 从 S3 加载训练历史，并转换为前端 TrainingHistoryItem 格式
    # 前端接口: { id, timestamp, dateRange, epochs, duration, mae, rmse, success }
    # S3 数据:  { id, timestamp, duration_formatted, success, metrics: {mae, rmse}, data_info: {date_range}, training_config: {epochs} }
    if S3_BUCKET:
        try:
            s3_hist = boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)
            obj = s3_hist.get_object(Bucket=S3_BUCKET, Key="history/training_history.json")
            raw_history = _json.loads(obj['Body'].read().decode('utf-8'))
            mapped_history = []
            for item in raw_history:
                metrics = item.get("metrics", {})
                data_info = item.get("data_info", {})
                config = item.get("training_config", {})
                mapped_history.append({
                    "id": item.get("id", 0),
                    "timestamp": item.get("timestamp", ""),
                    "dateRange": data_info.get("date_range", ""),
                    "epochs": config.get("epochs", 0),
                    "duration": item.get("duration_formatted", "N/A"),
                    "mae": metrics.get("mae", 0),
                    "rmse": metrics.get("rmse", 0),
                    "success": item.get("success", False),
                })
            training_status["history"] = mapped_history
            logger.info(f"Monitor: Loaded {len(mapped_history)} training history entries from S3")
        except Exception as e:
            logger.warning(f"Monitor: Failed to load training history from S3: {e}")
    
    # --- 4. 构建同步状态 ---
    # 格式化时间精确到秒（用户要求），避免原始 ISO 格式
    now_formatted = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sync_status = {
        "modelSynced": model_exists,
        "sensorDataSynced": csv_exists,
        "lastSyncTime": now_formatted if (model_exists or csv_exists) else None,
        "status": "synced" if (model_exists and csv_exists) else "partial",
    }
    
    # 判断当前阶段
    ts = training_state.get("status", "")
    ds = download_state.get("status", "")
    if ts == "running":
        current_stage = "training"
    elif ds in ("downloading", "checking", "running"):
        current_stage = "download"
    elif model_exists and csv_exists:
        current_stage = "idle"
    else:
        current_stage = "unknown"
    
    return {
        "currentStage": current_stage,
        "download": download_status,
        "training": training_status,
        "sync": sync_status,
    }

@api_router.get("/monitor/logs/{log_type}")
def monitor_logs(log_type: str, lines: int = 100):
    """返回指定类型的日志内容，优先从 S3 读取（各服务通过 crontab 推送日志到 S3）"""
    import boto3
    import subprocess as _sp
    
    # S3 日志路径映射（由各实例的 push_log 脚本上传）
    s3_log_keys = {
        "download": "logs/download.log",
        "training": "logs/training.log",
        "sync": "logs/api.log",
    }
    
    s3_key = s3_log_keys.get(log_type)
    log_lines = []
    source = "unknown"
    path = ""
    
    # 优先从 S3 读取
    if S3_BUCKET and s3_key:
        try:
            s3 = boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)
            obj = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
            content = obj['Body'].read().decode('utf-8', errors='replace')
            all_lines = content.splitlines()
            log_lines = all_lines[-lines:]
            source = f"S3 ({S3_BUCKET})"
            path = s3_key
            logger.info(f"Logs: Loaded {len(log_lines)} lines from S3 {s3_key}")
        except Exception as e:
            logger.warning(f"Logs: Failed to read from S3 {s3_key}: {e}")
            # sync 类型的日志在 API 服务器本地（systemd journal），直接从 journalctl 读取
            if log_type == "sync":
                try:
                    result = _sp.run(
                        ["/usr/bin/journalctl", "-u", "weather-api", "--no-pager", "-n", str(lines)],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.stdout.strip():
                        log_lines = result.stdout.strip().splitlines()
                        source = "journalctl (weather-api)"
                        path = "systemd journal"
                    else:
                        log_lines = ["No journal entries found for weather-api"]
                        source = "journalctl"
                        path = "systemd journal"
                except Exception as je:
                    log_lines = [f"Failed to read from both S3 and journalctl: {je}"]
                    source = "error"
                    path = s3_key
            else:
                log_lines = [f"Failed to load logs from S3: {e}"]
                source = "error"
                path = s3_key
    else:
        log_lines = [f"S3 not configured or unknown log type: {log_type}"]
        source = "none"
    
    return {
        "type": log_type,
        "lines": log_lines,
        "source": source,
        "path": path,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

# Register Router (Match both /api prefix and root for dev convenience)
app.include_router(api_router)
app.include_router(api_router, prefix="/api")

# --- 静态文件服务（前端）---
# 自动检测前端构建目录，支持开发环境和生产环境
# Local Dev: ../../frontend/dist
# Docker: ./frontend/dist (if copied)
# --- Frontend Static Files ---
FRONTEND_DIR_ENV = os.environ.get("FRONTEND_DIR")
if FRONTEND_DIR_ENV:
    FRONTEND_DIR = Path(FRONTEND_DIR_ENV)
else:
    # Fallback dev path
    FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend" / "dist"

if FRONTEND_DIR.exists():
    logger.info(f"Serving frontend from {FRONTEND_DIR}")
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    logger.warning(f"Frontend directory not found at {FRONTEND_DIR}. Skipping static file serving.")

if __name__ == "__main__":
    import sys
    # 默认 2 workers 以利用双核 vCPU，可通过 --workers N 覆盖
    workers = 2
    for i, arg in enumerate(sys.argv):
        if arg == "--workers" and i + 1 < len(sys.argv):
            workers = int(sys.argv[i + 1])
    uvicorn.run("api:app", host="0.0.0.0", port=8000, workers=workers)
