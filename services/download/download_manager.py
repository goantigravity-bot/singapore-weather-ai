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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("download_manager")


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
    logger.info("🛰️ Satellite Thread Started (3-ch, hourly)")
    noaa_s3 = get_noaa_s3_client()
    upload_s3 = get_s3_client()

    while True:
        try:
            now_sgt = datetime.now()
            # NOAA 数据有 ~30 分钟延迟，取 30 分钟前的 10 分钟整时刻
            target = now_sgt - timedelta(minutes=30)
            target = target.replace(minute=(target.minute // 10) * 10, second=0, microsecond=0)

            logger.info(f"🛰️ [Satellite] Processing {target.strftime('%Y-%m-%d %H:%M')} SGT")
            update_status("real-time", target.strftime("%Y-%m-%d"), "downloading")

            result = process_slot(target, noaa_s3, upload_s3)
            logger.info(f"🛰️ [Satellite] {target.strftime('%H:%M')} SGT → {result}")
            update_status("real-time", target.strftime("%Y-%m-%d"), "sleeping")

        except Exception as e:
            logger.error(f"🛰️ [Satellite] Error: {e}")

        time.sleep(SATELLITE_INTERVAL)


# === Thread 2: Sensor（每 5 分钟） ===

def sensor_thread():
    """每 5 分钟从 data.gov.sg 拉 6 种传感器 → 覆写 S3 govdata/{year}/{type}_{date}.json"""
    logger.info("📡 Sensor Thread Started (6 APIs, every 5 min)")
    s3 = get_s3_client()

    while True:
        today = datetime.now().strftime("%Y-%m-%d")
        year = datetime.now().strftime("%Y")

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
                logger.debug(f"📡 [Sensor] {api_name} → {s3_key} ({len(resp.content)} bytes)")

            except Exception as e:
                logger.warning(f"📡 [Sensor] {api_name} failed: {e}")

        logger.info(f"📡 [Sensor] Cycle done for {today} ({len(SENSOR_APIS)} APIs)")
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
        return

    t1 = threading.Thread(target=satellite_thread, daemon=True, name="satellite")
    t2 = threading.Thread(target=sensor_thread, daemon=True, name="sensor")

    t1.start()
    t2.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("🛑 Stopping Download Manager...")


if __name__ == "__main__":
    main()
