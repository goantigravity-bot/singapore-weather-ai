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

# Shared notification module (email + telegram)
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from notify import send_notification

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
import requests as http_requests
from datetime import datetime, timedelta, timezone
from climatology import get_climatology

# --- S3 Config ---
S3_BUCKET = os.environ.get("S3_BUCKET", "weather-ai-models-de08370c") # Default fallback
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", None)
MODEL_KEY = "models/latest.pth"
# CSV 路径由 sensor_data_manager 管理，位于 processed/real_sensor_data.csv
CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "processed", "real_sensor_data.csv")
SYNC_INTERVAL = 300 # 5 minutes
SGT = timezone(timedelta(hours=8))

# 上次成功同步 S3 数据的时间，用于标注数据新鲜度
_last_sync_time: datetime | None = None

# PSI 缓存 — 按区域存储，后台线程每 5 分钟更新
_psi_readings: dict[str, int] = {}

# PSI 区域中心坐标（来源: data.gov.sg PSI API regionMetadata）
PSI_REGION_CENTERS = {
    "west":    (1.35735, 103.700),
    "east":    (1.35735, 103.940),
    "central": (1.35735, 103.820),
    "south":   (1.29587, 103.820),
    "north":   (1.41803, 103.820),
}


def get_psi_for_location(lat: float, lon: float) -> int | None:
    """根据坐标找最近的 PSI 区域，返回该区域的 24 小时 PSI 读数"""
    if not _psi_readings:
        return None
    best_region = min(
        PSI_REGION_CENTERS,
        key=lambda r: (lat - PSI_REGION_CENTERS[r][0])**2 + (lon - PSI_REGION_CENTERS[r][1])**2
    )
    return _psi_readings.get(best_region)


def get_psi_for_path(points: list) -> int | None:
    """路径查询：检查所经区域，返回最高 PSI 值"""
    if not _psi_readings or not points:
        return None
    psi_values = [get_psi_for_location(pt[0], pt[1]) for pt in points]
    valid = [v for v in psi_values if v is not None]
    return max(valid) if valid else None


def _refresh_psi_cache():
    """轻量 PSI 缓存更新 — PSI 不在 download server 的 6 种传感器中，API server 直接拉。"""
    global _psi_readings
    try:
        psi_resp = http_requests.get(
            "https://api-open.data.gov.sg/v2/real-time/api/psi", timeout=10
        )
        psi_data = psi_resp.json()
        psi_items = (psi_data.get("data") or {}).get("items", [])
        if psi_items:
            psi_24h = psi_items[0].get("readings", {}).get("psi_twenty_four_hourly", {})
            if psi_24h:
                _psi_readings.update(psi_24h)
                logger.info(f"🌫️ PSI updated: {psi_24h}")
    except Exception as e:
        logger.warning(f"PSI fetch failed: {e}")


def sync_satellite_data(s3, bucket):
    """Sync preprocessed satellite .npy from S3 (instead of raw .nc).

    Downloads from s3://bucket/processed/satellite/YYYYMMDD/ into local
    processed_data/. Each .npy is ~16KB (vs ~700MB raw .nc), so full-day
    sync costs ~2.3MB instead of ~100GB. predict.py already prioritizes
    processed_data/ .npy over satellite_data/ .nc, so no other changes needed.
    """
    now_utc = datetime.utcnow()
    dates_to_check = [now_utc.date()]
    if now_utc.hour < 3:
        dates_to_check.append(now_utc.date() - timedelta(days=1))

    local_dir = "processed_data"
    os.makedirs(local_dir, exist_ok=True)

    for d in dates_to_check:
        date_str = d.strftime("%Y%m%d")
        prefix = f"processed/satellite/{date_str}/"
        # 同时下载 3-channel 波段数据（SAT_B08/B11/B13），供模型推理使用
        prefix_3ch = f"processed/satellite-3ch/{date_str}/"
        for pfx in [prefix, prefix_3ch]:
            try:
                objs = s3.list_objects_v2(Bucket=bucket, Prefix=pfx)
                if 'Contents' in objs:
                    for obj in objs['Contents']:
                        key = obj['Key']
                        filename = os.path.basename(key)
                        if not filename.endswith(".npy"):
                            continue
                        local_path = os.path.join(local_dir, filename)
                        if not os.path.exists(local_path):
                            logger.info(f"⬇️ [API] Downloading processed satellite: {filename}")
                            s3.download_file(bucket, key, local_path)
            except Exception as e:
                logger.warning(f"Error syncing processed satellite data: {e}")

    # Cleanup: remove files older than 24 hours (keep full day for cloud animation)
    # SAT_128_YYYYMMDD_HHMM.npy — timestamp is SGT, need -8h to compare with UTC
    # NC_H09_YYYYMMDD_HHMM_* — timestamp is UTC
    cleanup_count = 0
    cutoff = now_utc - timedelta(hours=24)
    for f in os.listdir(local_dir):
        if not f.endswith(".npy"):
            continue
        try:
            parts = f.split("_")
            file_dt = datetime.strptime(f"{parts[2]}_{parts[3]}", "%Y%m%d_%H%M")
            # SAT_128_* 文件名是 SGT 时间，需转 UTC
            if f.startswith("SAT_128_"):
                file_dt = file_dt - timedelta(hours=8)
            if file_dt < cutoff:
                os.remove(os.path.join(local_dir, f))
                cleanup_count += 1
        except (ValueError, IndexError):
            pass
    if cleanup_count:
        logger.info(f"🧹 Cleaned {cleanup_count} old processed satellite files")

    # 将 npy 转为 PNG（供前端云图展示），放到 processed_data/png/
    png_dir = os.path.join(local_dir, "png")
    os.makedirs(png_dir, exist_ok=True)
    convert_count = 0
    for f in os.listdir(local_dir):
        if not f.endswith(".npy"):
            continue
        png_name = f.replace(".npy", ".png")
        png_path = os.path.join(png_dir, png_name)
        if os.path.exists(png_path):
            continue
        npy_path = os.path.join(local_dir, f)
        try:
            arr = np.load(npy_path)
            # 与 _npy_to_base64_png 渲染逻辑一致
            tbb_min, tbb_max = 200.0, 280.0
            alpha = np.clip((tbb_max - arr) / (tbb_max - tbb_min), 0.0, 1.0)
            alpha = np.power(alpha, 1.5)
            alpha_u8 = (alpha * 100).astype(np.uint8)
            cloud_mask = alpha_u8 > 0
            rgba = np.zeros((*arr.shape, 4), dtype=np.uint8)
            rgba[:, :, 0][cloud_mask] = 255
            rgba[:, :, 1][cloud_mask] = 255
            rgba[:, :, 2][cloud_mask] = 255
            rgba[:, :, 3] = alpha_u8
            from PIL import Image
            img = Image.fromarray(rgba, 'RGBA')
            img = img.resize((512, 512), Image.BILINEAR)
            # 消除低 alpha 像素（晴空区域残留白雾）
            ALPHA_FLOOR = 50
            arr_out = np.array(img)
            low_mask = arr_out[:, :, 3] < ALPHA_FLOOR
            arr_out[low_mask] = 0  # 清除 RGBA 全部通道
            img = Image.fromarray(arr_out, 'RGBA')
            img.save(png_path, format='PNG', optimize=True)
            convert_count += 1
        except Exception as e:
            logger.warning(f"Failed to convert {f} to PNG: {e}")
    if convert_count:
        logger.info(f"🎨 Converted {convert_count} npy → PNG for cloud animation")

    # Cleanup old PNGs
    for f in os.listdir(png_dir):
        if not f.endswith(".png"):
            continue
        try:
            parts = f.replace(".png", "").split("_")
            file_dt = datetime.strptime(f"{parts[2]}_{parts[3]}", "%Y%m%d_%H%M")
            if f.startswith("SAT_128_"):
                file_dt = file_dt - timedelta(hours=8)
            if file_dt < cutoff:
                os.remove(os.path.join(png_dir, f))
        except (ValueError, IndexError):
            pass

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

            # 2. Refresh sensor CSV（从 S3 govdata 同步最近 N 天并重建 CSV）
            try:
                from sensor_data_manager import SensorDataManager
                manager = SensorDataManager(base_dir=os.path.dirname(os.path.dirname(__file__)))
                manager.run()
                logger.info("✅ Sensor CSV refreshed from S3 govdata")
            except Exception as e:
                logger.warning(f"Failed to refresh sensor CSV: {e}")

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

            # 4. PSI cache update
            _refresh_psi_cache()

            global _last_sync_time
            _last_sync_time = datetime.now(SGT)
            send_notification("sync_done", source="api",
                             details=f"sensor_csv=refreshed, model=loaded, psi=updated")

        except Exception as e:
             logger.error(f"Sync thread fatal error: {e}")
             send_notification("sync_error", source="api", details=f"error={e}")
        
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

    send_notification("server_start", source="api",
                     details=f"version=0.14.0, bucket={S3_BUCKET or 'none'}")

    try:
        model, df = load_system()
        if model: model.eval()
        stations_meta = get_station_mapping()
        logger.info("API Startup: Success.")
    except Exception as e:
        logger.error(f"API Startup Failed: {e}")

    # Forecast vs Actual 闭环：仅一个 worker 启动采集线程（文件锁去重）
    # _collector_lock_file 必须是全局变量，防止 GC 关闭文件句柄释放锁
    global _collector_lock_file
    try:
        import fcntl
        import actual_collector
        _collector_lock_file = open("/tmp/weather-collector.lock", "w")
        fcntl.flock(_collector_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        actual_collector.start_collector(
            predict_fn=predict_ensemble,
            get_model_fn=lambda: model,
            get_df_fn=lambda: df,
            get_stations_fn=lambda: stations_meta,
        )
        logger.info("Actual collector thread started (this worker owns the lock)")
    except BlockingIOError:
        logger.info("Collector already running in another worker, skipping")
    except Exception as e:
        logger.warning(f"Actual collector start failed: {e}")

# --- Endpoints ---

import geocoding

@api_router.get("/config/geocoding")
def get_geocoding_config():
    """返回当前 geocoding provider 配置"""
    return {"provider": geocoding.get_provider()}

@api_router.post("/config/geocoding")
def set_geocoding_config(body: dict):
    """运行时切换 geocoding provider（nominatim | onemap）"""
    provider = body.get("provider", "")
    try:
        result = geocoding.set_provider(provider)
        return {"provider": result, "status": "ok"}
    except ValueError as e:
        raise HTTPException(400, str(e))

@api_router.get("/health")
def health():
    return {"status": "ok", "version": "0.14.0", "service": "api", "geocoding_provider": geocoding.get_provider()}

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
    location: Optional[str] = Query(None, description="Location Name"),
    target_time: Optional[str] = Query(None, alias="time", description="Target time (ISO 8601). Omit for current time.")
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

        # 判定目标时间和数据来源
        import pandas as pd
        now_sgt = datetime.now(SGT)
        data_latest = df['timestamp'].max() if df is not None and not df.empty else None

        if target_time:
            # 用户指定时间
            req_time = pd.Timestamp(target_time)
            if req_time.tzinfo is None:
                req_time = req_time.tz_localize(SGT)
            # 如果在传感器数据范围内 → actual；否则 → forecast
            if data_latest and req_time <= data_latest:
                data_source = "actual"
            else:
                data_source = "forecast"
        else:
            # 默认当前时间
            req_time = now_sgt
            # 数据是否足够新（15 分钟内）→ actual，否则用气候均值
            if data_latest and (now_sgt - data_latest.to_pydatetime().astimezone(SGT)).total_seconds() < 900:
                data_source = "actual"
            elif data_latest:
                data_source = "forecast"
            else:
                data_source = "climatology"

        # 模型推理用的 target_time：如果有传感器数据就用数据最新时间，
        # 否则用气候均值填充后仍用 CSV 最后时间
        model_target_time = data_latest if data_latest else req_time
        
        # Use Ensemble Prediction
        raw = predict_ensemble(
            lat, lon, model_target_time, model, df, stations_meta, ensemble_size=3
        )

        # 如果模型预测失败（无传感器数据），尝试用气候均值构造输入
        if not raw and data_source != "actual":
            climate = get_climatology(req_time.month, req_time.hour)
            raw = {
                'rainfall': 0.0,
                'status': 'Unknown (Climatology Fallback)',
                'confidence': 0.3,
                'cloud_cover': False,
                'contributing_sensors': [],
                'debug': 'Fallback: climatology data used (no sensor data available)',
            }
            data_source = "climatology"

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
        
        # 获取最新观测数据（temperature / humidity / pm25）
        # Note: rainfall stations and temperature stations use DIFFERENT IDs
        # So we search the entire CSV for the latest non-zero readings
        current_temp = None
        current_humidity = None
        current_pm25 = None
        if not df.empty:
            # Get the latest row per station, then filter for non-zero values
            latest_per_station = df.sort_values('timestamp').groupby('sensor_id').tail(1)

            for col, attr in [('temperature', 'current_temp'), ('humidity', 'current_humidity'), ('pm25', 'current_pm25')]:
                if col not in latest_per_station.columns:
                    continue
                has_data = latest_per_station[latest_per_station[col] > 0]
                if has_data.empty:
                    continue
                # Pick the first station with data (they're all Singapore-wide, close enough)
                val = round(float(has_data.iloc[0][col]), 1)
                if attr == 'current_temp':
                    current_temp = val
                elif attr == 'current_humidity':
                    current_humidity = val
                elif attr == 'current_pm25':
                    current_pm25 = val

        # Climatology fallback if still no data
        if data_source == "climatology" and current_temp is None:
            climate = get_climatology(req_time.month, req_time.hour)
            current_temp = climate["temperature"]
            current_humidity = climate["humidity"]
            current_pm25 = climate["pm25"]
        
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
        # 前端显示的时间 = 用户请求的时间（非传感器数据时间）
        display_time = req_time

        # 数据新鲜度提示
        freshness = None
        if _last_sync_time:
            age_min = (datetime.now(SGT) - _last_sync_time).total_seconds() / 60
            freshness = f"{int(age_min)} min ago" if age_min < 60 else f"{int(age_min/60)}h ago"

        response = {
            "timestamp": display_time.isoformat(),
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
                "psi": get_psi_for_location(lat, lon),
            },
            "data_source": data_source,
            "data_freshness": freshness,
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
                place_id = weather_db.get_or_create_place(
                    place_name=location, place_type="point",
                    center_lat=lat, center_lon=lon
                )
                query_id = weather_db.save_user_activity(
                    query=location,
                    response_time_ms=round(elapsed_ms, 1),
                    forecast_outcome=recommendation,
                    ip_address=client_ip,
                    place_id=place_id
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
        
        # Send forecast query notification
        query_label = location or f"{lat:.4f},{lon:.4f}"
        elapsed_ms = (time.time() - _predict_start) * 1000
        send_notification("forecast_query", source="api",
                         details=f"query={query_label}, rainfall={rain:.1f}mm, temp={current_temp:.1f}°C, status={recommendation}, time={elapsed_ms:.0f}ms")

        return response
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        send_notification("error", source="api", details=f"forecast failed, error={e}")
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

        # PSI
        path_points = [(d['lat'], d['lon']) for d in result.get('details', [])]
        result['psi'] = get_psi_for_path(path_points)

        # Notification for path query
        risk = result.get('overall_risk', 'unknown')
        points_count = len(result.get('details', []))
        send_notification("forecast_query", source="api",
                         details=f"type=path, query={query}, risk={risk}, points={points_count}")

        return result
        
    except Exception as e:
        logger.error(f"Path prediction failed: {e}")
        send_notification("error", source="api", details=f"path query failed, query={query}, error={e}")
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

            query_id = weather_db.save_user_activity(
                query=q,
                response_time_ms=round(elapsed_ms, 1),
                forecast_outcome=forecast_outcome,
                ip_address=client_ip,
                place_id=place_id
            )

            # 关联活动（M:N — 一个查询可能涉及多个活动）
            activity_id = weather_db.get_or_create_activity(
                activity_name=parsed.get('activity', 'General Activity'),
                rain_tolerance=parsed.get('tolerance')
            )
            weather_db.link_activity_to_query(query_id, activity_id)

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
                        "confidence": d.get('confidence', 0.5),
                        "is_risky": d.get('is_risky', False),
                        "response_time_ms": round(elapsed_ms / max(len(details), 1), 1),
                        "forecast_time": datetime.now().isoformat(),
                    })
                weather_db.save_forecast_results(query_id, forecast_records)

        except Exception as db_err:
            logger.warning(f"Structured DB write failed: {db_err}")

        # PSI
        path_points = [(d['lat'], d['lon']) for d in result.get('details', [])]
        result['psi'] = get_psi_for_path(path_points)

        # Notification for smart query
        risk = result.get('overall_risk', 'unknown')
        advice = result.get('advice', '')[:60]
        send_notification("forecast_query", source="api",
                         details=f"type=smart, query={q[:50]}, risk={risk}, advice={advice}, time={elapsed_ms:.0f}ms")

        return result
    except Exception as e:
        logger.error(f"Smart query failed: {e}")
        send_notification("error", source="api", details=f"smart query failed, query={q[:50]}, error={e}")
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
        c.execute("""
            SELECT p.place_name, COUNT(DISTINCT f.query_id) AS count
            FROM forecast_result f
            JOIN location l ON f.loc_id = l.loc_id
            JOIN place p ON l.place_id = p.place_id
            WHERE p.place_name NOT LIKE 'backtest:%'
              AND f.query_id IS NOT NULL
              AND p.center_lat IS NOT NULL
              AND length(p.place_name) > 2
              AND p.place_name NOT IN ('Singapore', 'tonight', 'today', 'tomorrow', 'now')
            GROUP BY p.place_name
            ORDER BY count DESC
            LIMIT 8
        """)
        rows = c.fetchall()
        conn.close()
        if rows:
            return [{"id": i, "name": r[0], "count": r[1]} for i, r in enumerate(rows)]
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
    
    csv_exists = os.path.exists(CSV_PATH)
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
            
        except Exception as e:
            logger.warning(f"Monitor: Failed to create S3 client: {e}")
    else:
        logger.warning("Monitor: S3_BUCKET is not set, returning local-only data")
    
    # completedDays 和 totalFiles 由 download server 计算并写入 download_state.json
    completed_days = download_state.get("completedDays", 0)
    total_files = download_state.get("totalFiles", 0)
    
    # --- 2. 构建下载状态 ---
    download_status = {
        "currentDate": download_state.get("current_target_date"),
        "completedDays": completed_days,
        "totalDays": max(completed_days, 120),  # 目标约 120 天的历史数据
        "filesDownloaded": total_files,
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
    """返回指定类型的日志。
    - sync (API): 直接读本地 api.log（API Server read-only，不推送到 S3）
    - download/training: 从 S3 logs/ 读取（由各服务器 crontab 推送）
    """
    import boto3
    
    log_lines = []
    source = "unknown"
    path = ""
    
    if log_type == "sync":
        # API 日志在项目根目录 (/home/ubuntu/weather-ai/api.log)
        # __file__ = .../services/api/backend/api.py → 上溯 3 级到 weather-ai/
        local_log = os.path.join(os.path.dirname(__file__), "..", "..", "..", "api.log")
        local_log = os.path.abspath(local_log)
        try:
            if os.path.exists(local_log):
                with open(local_log, 'r', errors='replace') as f:
                    all_lines = f.readlines()
                log_lines = [l.rstrip() for l in all_lines[-lines:]]
                source = "local"
                path = local_log
            else:
                log_lines = [f"Log file not found: {local_log}"]
                source = "error"
                path = local_log
        except Exception as e:
            log_lines = [f"Failed to read local log: {e}"]
            source = "error"
    else:
        # download/training 日志从 S3 读取
        s3_log_keys = {
            "download": "logs/download.log",
            "training": "logs/training.log",
        }
        s3_key = s3_log_keys.get(log_type)
        if S3_BUCKET and s3_key:
            try:
                s3 = boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)
                obj = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
                content = obj['Body'].read().decode('utf-8', errors='replace')
                all_lines = content.splitlines()
                log_lines = all_lines[-lines:]
                source = f"S3 ({S3_BUCKET})"
                path = s3_key
            except Exception as e:
                log_lines = [f"Failed to load logs from S3: {e}"]
                source = "error"
                path = s3_key
        else:
            log_lines = [f"Unknown log type: {log_type}"]
            source = "none"
    
    return {
        "type": log_type,
        "lines": log_lines,
        "source": source,
        "path": path,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

# ── Forecast vs Actual 闭环：误差分析 API ──

@api_router.get("/accuracy/summary")
def accuracy_summary():
    """总体准确度概览"""
    return weather_db.get_accuracy_summary()


@api_router.get("/accuracy/by-hour")
def accuracy_by_hour():
    """按小时聚合的 MAE 和 bias"""
    return weather_db.get_accuracy_by_hour()


@api_router.get("/accuracy/by-location")
def accuracy_by_location():
    """按地点聚合的 MAE"""
    return weather_db.get_accuracy_by_location()


@api_router.get("/accuracy/by-rain-level")
def accuracy_by_rain_level():
    """按降雨量级聚合的 MAE 和 bias"""
    return weather_db.get_accuracy_by_rain_level()


@api_router.get("/accuracy/by-distance")
def accuracy_by_distance():
    """按匹配距离分桶的 MAE — 验证 2km 阈值"""
    return weather_db.get_accuracy_by_distance()


# ── 卫星云图帧动画 API ──

# 新加坡+周边区域裁剪框 (128×128, 覆盖 SG+JB+巴淡岛)
# 41×37 HSD crop 的实际地理范围（新加坡+柔佛南部，每像素约 2km）
# 旧值 [[0.05, 102.5], [2.65, 105.1]] 是 128×128 NOAA ISatSS tile 的范围，已废弃
SG_BOUNDS = [[0.98, 103.49], [1.72, 104.15]]

def _npy_to_base64_png(npy_path: str) -> str | None:
    """将 128×128 TBB .npy 转为 RGBA PNG（白色=云，透明=晴空）并返回 base64。

    颜色映射逻辑：红外亮温(TBB) 越低意味着云越高越厚。
    - TBB ≤ 200K：最浓厚的云（白色，完全不透明）
    - TBB ~ 260K：中等厚度的云（半透明白色）
    - TBB ≥ 290K：晴空（完全透明）
    """
    import io
    import base64
    from PIL import Image

    try:
        arr = np.load(npy_path)  # float32, 128×128 or 64×64, Kelvin
        # 非线性映射：TBB → alpha（低温=高不透明度）
        # 280K 以上视为晴空（比之前 290K 更激进，去除薄云/霾）
        tbb_min, tbb_max = 200.0, 280.0
        alpha = np.clip((tbb_max - arr) / (tbb_max - tbb_min), 0.0, 1.0)
        # gamma=1.5 增强对比：薄云更透明、厚云更明显
        alpha = np.power(alpha, 1.5)
        alpha_u8 = (alpha * 100).astype(np.uint8)  # 最高 ~100/255≈39%，确保底图始终清晰可见
        # RGBA：仅云像素为白色，透明像素 RGB 也置零（预乘 alpha），
        # 避免浏览器缩放插值时白色 RGB 泄漏到透明区域
        cloud_mask = alpha_u8 > 0
        rgba = np.zeros((*arr.shape, 4), dtype=np.uint8)
        rgba[:, :, 0][cloud_mask] = 255
        rgba[:, :, 1][cloud_mask] = 255
        rgba[:, :, 2][cloud_mask] = 255
        rgba[:, :, 3] = alpha_u8

        img = Image.fromarray(rgba, 'RGBA')
        # 上采样到 512×512，双线性插值让云图更平滑
        img = img.resize((512, 512), Image.BILINEAR)

        # 消除低 alpha 像素（晴空区域残留白雾）——上采样后执行以处理插值产生的伪影
        ALPHA_FLOOR = 50
        arr_out = np.array(img)
        low_mask = arr_out[:, :, 3] < ALPHA_FLOOR
        arr_out[low_mask] = 0  # 清除 RGBA 全部通道
        img = Image.fromarray(arr_out, 'RGBA')

        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
        return base64.b64encode(buf.getvalue()).decode('ascii')
    except Exception as e:
        logger.warning(f"Failed to convert {npy_path} to PNG: {e}")
        return None


@api_router.get("/satellite/frames")
def get_satellite_frames():
    """返回最近 18 帧预渲染 PNG 云图（用于前端动画播放）。

    优先读取 processed_data/png/ 下的预渲染 PNG；
    若无 PNG 则 fallback 到 npy 实时转换。
    """
    png_dir = os.path.join("processed_data", "png")
    npy_dir = "processed_data"

    entries = []

    # 优先扫描 PNG 目录
    if os.path.isdir(png_dir):
        for f in os.listdir(png_dir):
            if not f.endswith(".png"):
                continue
            try:
                base = f.replace(".png", "")
                parts = base.split("_")
                file_dt = datetime.strptime(f"{parts[2]}_{parts[3]}", "%Y%m%d_%H%M")
                entries.append((file_dt, os.path.join(png_dir, f), "png"))
            except (ValueError, IndexError):
                continue

    # 如果没有 PNG，fallback 到 npy
    if not entries and os.path.isdir(npy_dir):
        for f in os.listdir(npy_dir):
            if not f.endswith(".npy"):
                continue
            try:
                if f.startswith("SAT_128_"):
                    parts = f.replace(".npy", "").split("_")
                    file_dt = datetime.strptime(f"{parts[2]}_{parts[3]}", "%Y%m%d_%H%M")
                elif f.startswith("NC_H0"):
                    parts = f.split("_")
                    file_dt = datetime.strptime(f"{parts[2]}_{parts[3]}", "%Y%m%d_%H%M")
                else:
                    continue
                entries.append((file_dt, os.path.join(npy_dir, f), "npy"))
            except (ValueError, IndexError):
                continue

    entries.sort(key=lambda x: x[0])

    # 全天展示（PNG 预渲染后每帧 ~50KB，144 帧 ≈ 7MB）
    MAX_FRAMES = 144
    entries = entries[-MAX_FRAMES:]

    frames = []
    for dt, path, fmt in entries:
        if fmt == "png":
            # 直接读 PNG 转 base64，无需 numpy
            try:
                import base64
                with open(path, "rb") as fh:
                    b64 = base64.b64encode(fh.read()).decode("ascii")
                # File timestamps are in UTC, convert to SGT for display
                dt_sgt = dt + timedelta(hours=8)
                frames.append({
                    "image": f"data:image/png;base64,{b64}",
                    "time": dt_sgt.strftime("%H:%M"),
                    "timestamp": dt_sgt.isoformat(),
                })
            except Exception as e:
                logger.warning(f"Failed to read PNG {path}: {e}")
        else:
            b64 = _npy_to_base64_png(path)
            if b64:
                # File timestamps are in UTC, convert to SGT for display
                dt_sgt = dt + timedelta(hours=8)
                frames.append({
                    "image": f"data:image/png;base64,{b64}",
                    "time": dt_sgt.strftime("%H:%M"),
                    "timestamp": dt_sgt.isoformat(),
                })

    return {"frames": frames, "bounds": SG_BOUNDS}


# ── Telegram 通知集成 ──

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
import telegram_notifier

@api_router.get("/telegram/status")
def telegram_status():
    """返回 Telegram 通知配置状态"""
    return {
        "configured": telegram_notifier.is_configured(),
        "bot_token_set": bool(telegram_notifier.TELEGRAM_BOT_TOKEN),
        "chat_id_set": bool(telegram_notifier.TELEGRAM_CHAT_ID),
        "cooldown_minutes": telegram_notifier.COOLDOWN_MINUTES,
    }


@api_router.post("/telegram/test")
def telegram_test():
    """发送测试消息验证 Telegram 连接"""
    if not telegram_notifier.is_configured():
        raise HTTPException(400, "Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars.")
    success = telegram_notifier.send_test_message()
    if success:
        return {"status": "ok", "message": "Test message sent"}
    raise HTTPException(500, "Failed to send test message. Check bot token and chat ID.")


@api_router.post("/telegram/alert")
def telegram_manual_alert(
    location: str = Query(..., description="Location name"),
    lat: float = Query(...),
    lon: float = Query(...),
):
    """手动触发某地的降雨预警 (用于测试或人工告警)"""
    if not telegram_notifier.is_configured():
        raise HTTPException(400, "Telegram not configured")

    # 对该坐标跑一次预测
    global model, df, stations_meta
    if model is None: model, df = load_system()
    if not stations_meta: stations_meta = get_station_mapping()

    raw = predict_ensemble(lat, lon, datetime.now(SGT), model, df, stations_meta, ensemble_size=3)
    if not raw:
        raise HTTPException(404, "Prediction failed for this location")

    rainfall = raw.get('rainfall', 0)
    confidence = raw.get('confidence', 0.5)

    success = telegram_notifier.send_rain_alert(
        location=location, probability=confidence,
        rainfall_mm=rainfall, lat=lat, lon=lon
    )
    return {
        "sent": success,
        "rainfall_mm": rainfall,
        "confidence": confidence,
        "location": location,
    }


# Register Router (Match both /api prefix and root for dev convenience)
app.include_router(api_router)
app.include_router(api_router, prefix="/api")
app.include_router(monitor_router)
app.include_router(monitor_router, prefix="/api")

# --- Frontend & Monitor Dashboard Static Files ---
FRONTEND_DIR_ENV = os.environ.get("FRONTEND_DIR")
if FRONTEND_DIR_ENV:
    FRONTEND_DIR = Path(FRONTEND_DIR_ENV)
else:
    # Dev fallback: services/api/ → services/frontend/dist
    FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"

MONITOR_DIR_ENV = os.environ.get("MONITOR_DIR")
if MONITOR_DIR_ENV:
    MONITOR_DIR = Path(MONITOR_DIR_ENV)
else:
    MONITOR_DIR = Path(__file__).parent.parent / "monitor-dashboard" / "dist"

# Monitor dashboard 挂载到 /monitor（必须在 frontend 之前，否则被 / 兜底）
if MONITOR_DIR.exists():
    logger.info(f"Serving monitor dashboard from {MONITOR_DIR}")
    app.mount("/monitor", StaticFiles(directory=str(MONITOR_DIR), html=True), name="monitor")
else:
    logger.warning(f"Monitor dashboard not found at {MONITOR_DIR}")

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
