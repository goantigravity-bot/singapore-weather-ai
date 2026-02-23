"""
backfill.py — ad-hoc 回填脚本（手动运行）

用法：
  python3 backfill.py --start 2024-01-01 --end 2024-12-31
  python3 backfill.py --start 2025-06-01 --end 2025-06-30 --satellite-only
  python3 backfill.py --start 2025-06-01 --end 2025-06-30 --sensor-only

卫星：逐日调用 download_aws_satellite.process_day()，有 .complete 标记则跳过
传感器：逐日 curl 6 种 data.gov.sg API → 上传 JSON 到 S3，已有则跳过
"""
import argparse
import logging
import os
from datetime import datetime, timedelta

import boto3
import requests
from botocore.exceptions import ClientError

from download_aws_satellite import process_day, _check_day_complete_s3

S3_BUCKET = os.environ.get("S3_BUCKET", "weather-ai-models-gcc")

# data.gov.sg 传感器 API（与 download_manager 保持一致）
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
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("backfill")


def backfill_satellite(start: datetime, end: datetime, workers: int):
    """逐日回填 3-ch 卫星数据"""
    from botocore.config import Config
    from download_aws_satellite import UNSIGNED

    noaa_s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED), region_name="us-east-1")
    upload_s3 = boto3.client("s3")

    current = start
    stats = {"days": 0, "skipped": 0, "done": 0, "failed": 0}

    while current <= end:
        date_str = current.strftime("%Y%m%d")
        stats["days"] += 1

        if _check_day_complete_s3(date_str, upload_s3):
            logger.info(f"✅ {current.strftime('%Y-%m-%d')} — already complete, skipping")
            stats["skipped"] += 1
        else:
            logger.info(f"⬇️ Processing {current.strftime('%Y-%m-%d')}...")
            result = process_day(current, noaa_s3, workers=workers)
            logger.info(f"   → uploaded={result['uploaded']} failed={result['failed']} / {result['total']}")

            if result["uploaded"] > 0:
                stats["done"] += 1
            else:
                stats["failed"] += 1

        current += timedelta(days=1)

    return stats


def backfill_sensor(start: datetime, end: datetime):
    """逐日回填传感器 JSON（S3 已有则跳过）"""
    s3 = boto3.client("s3")
    current = start
    stats = {"days": 0, "skipped": 0, "downloaded": 0, "failed": 0}

    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        year = current.strftime("%Y")
        stats["days"] += 1
        day_downloaded = 0

        for api_name, api_url in SENSOR_APIS.items():
            s3_key = f"govdata/{year}/{api_name}_{date_str}.json"

            # S3 已有则跳过
            try:
                s3.head_object(Bucket=S3_BUCKET, Key=s3_key)
                stats["skipped"] += 1
                continue
            except ClientError:
                pass

            try:
                resp = requests.get(f"{api_url}?date={date_str}", timeout=30)
                resp.raise_for_status()
                s3.put_object(
                    Bucket=S3_BUCKET,
                    Key=s3_key,
                    Body=resp.content,
                    ContentType="application/json",
                )
                stats["downloaded"] += 1
                day_downloaded += 1
            except Exception as e:
                logger.warning(f"  ❌ {api_name} {date_str}: {e}")
                stats["failed"] += 1

        if day_downloaded > 0:
            logger.info(f"📡 {date_str}: downloaded {day_downloaded} APIs")

        current += timedelta(days=1)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill satellite and sensor data")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--satellite-only", action="store_true", help="Only backfill satellite")
    parser.add_argument("--sensor-only", action="store_true", help="Only backfill sensor")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers for satellite (default: 4)")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d")
    end = datetime.strptime(args.end, "%Y-%m-%d")
    do_satellite = not args.sensor_only
    do_sensor = not args.satellite_only

    logger.info(f"🔄 Backfill: {args.start} → {args.end}")
    logger.info(f"   Satellite: {'✅' if do_satellite else '⏭️ skip'}")
    logger.info(f"   Sensor:    {'✅' if do_sensor else '⏭️ skip'}")

    if do_satellite:
        logger.info("=== Satellite Backfill ===")
        sat_stats = backfill_satellite(start, end, args.workers)
        logger.info(f"🛰️ Satellite: {sat_stats}")

    if do_sensor:
        logger.info("=== Sensor Backfill ===")
        sensor_stats = backfill_sensor(start, end)
        logger.info(f"📡 Sensor: {sensor_stats}")

    logger.info("✅ Backfill complete!")


if __name__ == "__main__":
    main()
