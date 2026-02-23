"""
Download Manager — 常驻服务（realtime only）

职责：
  1. satellite_thread: 每小时从 NOAA AWS 下载 3-ch 卫星帧 → S3 processed/satellite-3ch/
  2. sensor_thread: 每 5 分钟从 data.gov.sg 拉 6 种传感器数据 → S3 govdata/
  3. update_status: 更新 download_state.json 供 Dashboard 展示

不包含 backfill（由 backfill.py 手动运行）。
"""
import os
import json
import time
import logging
import threading
from datetime import datetime, timedelta

import boto3
import requests
from botocore.config import Config
from botocore.exceptions import ClientError

# 3-ch 卫星处理核心（共享模块）
from download_aws_satellite import process_slot, UNSIGNED

# 通知模块（email + telegram）
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from notify import send_notification

# --- 配置 ---
SATELLITE_INTERVAL = int(os.environ.get("SATELLITE_INTERVAL", "3600"))   # 1 小时
SENSOR_INTERVAL = int(os.environ.get("SENSOR_INTERVAL", "300"))          # 5 分钟

S3_BUCKET = os.environ.get("S3_BUCKET", "weather-ai-models-gcc")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", None)

# data.gov.sg 传感器 API
SENSOR_APIS = {
    "rainfall":        "https://api.data.gov.sg/v1/environment/rainfall",
    "temperature":     "https://api.data.gov.sg/v1/environment/air-temperature",
    "humidity":        "https://api.data.gov.sg/v1/environment/relative-humidity",
    "pm25":            "https://api.data.gov.sg/v1/environment/pm25",
    "wind-speed":      "https://api-open.data.gov.sg/v2/real-time/api/wind-speed",
    "wind-direction":  "https://api-open.data.gov.sg/v2/real-time/api/wind-direction",
}

# === 日志配置 — 分文件输出到 logs/ ===
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_LOG_FORMATTER = logging.Formatter(_LOG_FORMAT)

def _setup_logger(name: str, filename: str, level=logging.INFO) -> logging.Logger:
    """为每个子系统创建独立的 logger + 文件 handler"""
    log = logging.getLogger(name)
    log.setLevel(level)
    # 文件
    fh = logging.FileHandler(os.path.join(LOG_DIR, filename))
    fh.setFormatter(_LOG_FORMATTER)
    log.addHandler(fh)
    # 同时输出到 stdout（被 nohup 捕获到 download.log）
    sh = logging.StreamHandler()
    sh.setFormatter(_LOG_FORMATTER)
    log.addHandler(sh)
    return log

logger = _setup_logger("download_manager", "download-main.log")
sat_logger = _setup_logger("satellite", "download-satellite.log")
sensor_logger = _setup_logger("sensor", "download-sensor.log")



# === S3 Helpers ===

def get_s3_client():
    return boto3.client("s3", endpoint_url=S3_ENDPOINT_URL)


def get_noaa_s3_client():
    """无认证 S3 client，读 AWS Open Data 公开 bucket"""
    return boto3.client("s3", config=Config(signature_version=UNSIGNED), region_name="us-east-1")


def update_status(mode, date, status, sat_count=0):
    """更新 download_state.json，包含 completedDays 累计统计"""
    try:
        s3 = get_s3_client()

        # 统计已完成的卫星天数
        completed_days = 0
        try:
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=S3_BUCKET, Prefix="processed/satellite-3ch/", Delimiter="/"):
                completed_days += len(page.get("CommonPrefixes", []))
        except Exception as e:
            logger.warning(f"Failed to count satellite dates: {e}")

        s3.put_object(
            Bucket=S3_BUCKET,
            Key="state/download_state.json",
            Body=json.dumps({
                "last_updated": datetime.now().isoformat(),
                "mode": mode,
                "current_target_date": date,
                "satellite_files_count": sat_count,
                "status": status,
                "completedDays": completed_days,
                "totalFiles": completed_days * 144,
            }),
        )
    except Exception as e:
        logger.warning(f"Failed to update status: {e}")

# === Thread 1: Satellite（每小时） ===

def satellite_thread():
    """每小时从 NOAA AWS 下载最新 3-ch 卫星帧"""
    sat_logger.info("🛰️ Satellite Thread Started (3-ch, hourly)")
    noaa_s3 = get_noaa_s3_client()
    upload_s3 = get_s3_client()

    while True:
        try:
            now_sgt = datetime.now()
            # NOAA 数据有 ~30 分钟延迟，取 30 分钟前的 10 分钟整时刻
            target = now_sgt - timedelta(minutes=30)
            target = target.replace(minute=(target.minute // 10) * 10, second=0, microsecond=0)
            slot_str = target.strftime("%Y-%m-%d %H:%M")

            sat_logger.info(f"Processing {slot_str} SGT")
            update_status("real-time", target.strftime("%Y-%m-%d"), "downloading")

            result = process_slot(target, noaa_s3, upload_s3)
            sat_logger.info(f"{slot_str} SGT → {result}")
            update_status("real-time", target.strftime("%Y-%m-%d"), "sleeping")

            if result == "done":
                send_notification("satellite_done", source="download",
                                 details=f"slot={slot_str}, bands=B08+B11+B13")
            elif result == "skipped":
                send_notification("satellite_skipped", source="download",
                                 details=f"slot={slot_str}, reason=already exists in S3")
            elif result == "missing":
                sat_logger.info(f"No data available for {slot_str} (NOAA source missing)")
            elif result == "failed":
                send_notification("satellite_error", source="download",
                                 details=f"slot={slot_str}, result=failed")

        except Exception as e:
            sat_logger.error(f"Error: {e}")
            send_notification("satellite_error", source="download",
                             details=f"slot={slot_str}, error={e}")

        time.sleep(SATELLITE_INTERVAL)


# === Thread 2: Sensor（每 5 分钟） ===

def sensor_thread():
    """每 5 分钟从 data.gov.sg 拉 6 种传感器 → 覆写 S3 govdata/{year}/{type}_{date}.json"""
    sensor_logger.info("📡 Sensor Thread Started (6 APIs, every 5 min)")
    s3 = get_s3_client()

    while True:
        today = datetime.now().strftime("%Y-%m-%d")
        year = datetime.now().strftime("%Y")
        success_count = 0
        failed_apis = []
        total_bytes = 0

        for api_name, api_url in SENSOR_APIS.items():
            s3_key = f"govdata/{year}/{api_name}_{today}.json"
            try:
                resp = requests.get(f"{api_url}?date={today}", timeout=30)
                resp.raise_for_status()

                s3.put_object(
                    Bucket=S3_BUCKET,
                    Key=s3_key,
                    Body=resp.content,
                    ContentType="application/json",
                )
                success_count += 1
                total_bytes += len(resp.content)
                sensor_logger.debug(f"{api_name} → {s3_key} ({len(resp.content)} bytes)")

            except Exception as e:
                sensor_logger.warning(f"{api_name} failed: {e}")
                failed_apis.append(api_name)

        total_kb = total_bytes // 1024
        if failed_apis:
            sensor_logger.warning(f"Cycle {today}: {len(failed_apis)}/{len(SENSOR_APIS)} failed")
            send_notification("sensor_error", source="download",
                             details=f"date={today}, ok={success_count}, failed={','.join(failed_apis)}")
        else:
            sensor_logger.info(f"Cycle done for {today} ({success_count} APIs, {total_kb}KB)")
            send_notification("sensor_done", source="download",
                             details=f"date={today}, apis={success_count}, size={total_kb}KB")

        time.sleep(SENSOR_INTERVAL)


# === Main ===

def main():
    logger.info("🚀 Download Manager Starting (satellite hourly + sensor 5min)")

    # 验证 S3 连接
    try:
        s3 = get_s3_client()
        s3.head_bucket(Bucket=S3_BUCKET)
        logger.info(f"✅ S3 Connection OK → {S3_BUCKET}")
    except Exception as e:
        logger.error(f"❌ S3 Connection Failed: {e}")
        send_notification("error", source="download",
                         details=f"S3 connection failed, bucket={S3_BUCKET}, error={e}")
        return

    # Startup notification
    send_notification("server_start", source="download",
                     details=f"bucket={S3_BUCKET}, satellite_interval={SATELLITE_INTERVAL}s, sensor_interval={SENSOR_INTERVAL}s")

    t1 = threading.Thread(target=satellite_thread, daemon=True, name="satellite")
    t2 = threading.Thread(target=sensor_thread, daemon=True, name="sensor")

    t1.start()
    t2.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("🛑 Stopping Download Manager...")
        send_notification("server_stop", source="download",
                         details="manual shutdown (KeyboardInterrupt)")


if __name__ == "__main__":
    main()

