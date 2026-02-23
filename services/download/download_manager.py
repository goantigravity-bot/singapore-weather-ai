import os
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import boto3
import numpy as np
from botocore.exceptions import ClientError

# AWS Open Data 数据源，替代 JAXA FTP
from noaa_satellite import download_and_crop

# --- Configuration ---
# 1. Real-Time Thread
CHECK_INTERVAL_REALTIME = int(os.environ.get("CHECK_INTERVAL_REALTIME", "600")) # 10 Minutes (match satellite interval)
# 2. Backfill Thread
CHECK_INTERVAL_BACKFILL = int(os.environ.get("CHECK_INTERVAL_BACKFILL", "14400")) # 4 Hours

# Date Range (For Backfill)
START_DATE = os.environ.get("START_DATE", "2023-01-01")
# Default End Date is Yesterday (Full history until today)
yest = datetime.now() - timedelta(days=1)
END_DATE = os.environ.get("END_DATE", yest.strftime("%Y-%m-%d"))

# S3 Config
S3_BUCKET = os.environ.get("S3_BUCKET", "weather-ai-models-de08370c")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", None)
PARALLEL_JOBS = int(os.environ.get("PARALLEL_JOBS", "12"))
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "arn:aws:sns:ap-southeast-1:105506693880:weather-ai-download-complete")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("download_manager")

def get_s3_client():
    return boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)

def update_status(mode, date, status, sat_count=0):
    """Updates status to S3, including cumulative progress stats."""
    try:
        s3 = get_s3_client()
        import json

        # 统计 S3 中已完成的卫星数据天数（processed/satellite-3ch/ 下的日期目录）
        completed_days = 0
        try:
            paginator = s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=S3_BUCKET, Prefix="processed/satellite-3ch/", Delimiter="/"):
                completed_days += len(page.get('CommonPrefixes', []))
        except Exception as e:
            logger.warning(f"Failed to count satellite dates: {e}")

        status_data = {
            "last_updated": datetime.now().isoformat(),
            "mode": mode,
            "current_target_date": date,
            "satellite_files_count": sat_count,
            "status": status,
            # 累计统计 — API Dashboard 直接读取展示
            "completedDays": completed_days,
            "totalFiles": completed_days * 144,
        }

        s3.put_object(
            Bucket=S3_BUCKET,
            Key="state/download_state.json",
            Body=json.dumps(status_data)
        )
    except Exception as e:
        logger.warning(f"Failed to update status: {e}")

def check_s3_exists(date_str):
    """Check if processed satellite data for this date is COMPLETE (.complete marker exists)."""
    s3 = get_s3_client()
    marker_key = f"processed/satellite/{date_str}/.complete"
    try:
        s3.head_object(Bucket=S3_BUCKET, Key=marker_key)
        return True
    except ClientError:
        return False

def check_s3_archived(date_str):
    """Check if satellite data exists in archive folder"""
    s3 = get_s3_client()
    prefix = f"archived/satellite/{date_str}/"
    try:
        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix, MaxKeys=1)
        return 'Contents' in resp
    except ClientError:
        return False

def restore_from_archive(date_str):
    """Restore from archive to active folder"""
    s3 = get_s3_client()
    src_prefix = f"archived/satellite/{date_str}/"
    
    # List and Copy each object
    # For large datasets, S3 Batch Operations is better, but this is simple python loop
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=S3_BUCKET, Prefix=src_prefix)
    
    count = 0
    for page in pages:
        if 'Contents' in page:
            for obj in page['Contents']:
                src_key = obj['Key']
                # archived/satellite/20251001/file.nc -> satellite/20251001/file.nc
                dest_key = src_key.replace("archived/", "", 1)
                
                logger.info(f"♻️ Restoring {src_key} -> {dest_key}")
                copy_source = {'Bucket': S3_BUCKET, 'Key': src_key}
                s3.copy_object(CopySource=copy_source, Bucket=S3_BUCKET, Key=dest_key)
                count += 1
    
    logger.info(f"✅ Restored {count} files for {date_str}")
    return count > 0

# --- Thread 1: Real-Time ---
def _download_and_upload_frame(dt_sgt: datetime, s3) -> bool:
    """下载单帧卫星图（NOAA AWS Open Data）并上传 npy 到 S3。"""
    date_compact = dt_sgt.strftime("%Y%m%d")
    s3_prefix = f"processed/satellite/{date_compact}/"

    arr, npy_name = download_and_crop(dt_sgt)
    if arr is None:
        return False

    tmp_npy = f"/tmp/{npy_name}"
    np.save(tmp_npy, arr)
    s3.upload_file(tmp_npy, S3_BUCKET, s3_prefix + npy_name)
    os.remove(tmp_npy)
    logger.info(f"📤 {npy_name} → s3 TBB={arr.min():.0f}~{arr.max():.0f}K")
    return True


def realtime_thread():
    """每 10 分钟从 NOAA AWS Open Data 下载最新卫星帧。"""
    logger.info("🟢 Real-Time Thread Started (NOAA Open Data)")
    s3 = get_s3_client()
    while True:
        now_sgt = datetime.now()  # 服务器设为 SGT
        # NOAA 数据有 ~20 分钟延迟，取 20 分钟前的 10 分钟整时刻
        target = now_sgt - timedelta(minutes=20)
        target = target.replace(minute=(target.minute // 10) * 10, second=0, microsecond=0)

        logger.info(f"⚡ [RealTime] Fetching {target.strftime('%H:%M')} SGT")
        update_status("real-time", target.strftime("%Y-%m-%d"), "downloading")

        ok = _download_and_upload_frame(target, s3)
        status = "✅" if ok else "⏭️ no data"
        logger.info(f"⚡ [RealTime] {target.strftime('%H:%M')} SGT → {status}")
        update_status("real-time", target.strftime("%Y-%m-%d"), "sleeping")

        time.sleep(CHECK_INTERVAL_REALTIME)

# --- Thread 2: Backfill ---
def _download_single_frame(dt_sgt):
    """子进程 worker：独立进程下载单帧，避免 netCDF4 线程安全问题。"""
    try:
        s3 = boto3.client('s3')
        arr, npy_name = download_and_crop(dt_sgt)
        if arr is None:
            return False
        import io
        buf = io.BytesIO()
        np.save(buf, arr)
        buf.seek(0)
        date_str = dt_sgt.strftime("%Y%m%d")
        key = f"processed/satellite/{date_str}/{npy_name}"
        s3.upload_fileobj(buf, S3_BUCKET, key)
        return True
    except Exception as e:
        return False


def _process_day_noaa(date: datetime, s3) -> dict:
    """用 NOAA 数据源并行处理一整天（4 进程，每 10 分钟一帧，共 144 帧）。"""
    from concurrent.futures import ProcessPoolExecutor

    slots = []
    t = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = t + timedelta(hours=23, minutes=50)
    while t <= end:
        slots.append(t)
        t += timedelta(minutes=10)

    ok, fail = 0, 0

    with ProcessPoolExecutor(max_workers=PARALLEL_JOBS) as pool:
        futures = {pool.submit(_download_single_frame, slot): slot for slot in slots}
        for future in as_completed(futures):
            try:
                if future.result():
                    ok += 1
                else:
                    fail += 1
            except Exception as e:
                logger.warning(f"Frame error {futures[future]}: {e}")
                fail += 1

    return {"total": len(slots), "uploaded": ok, "failed": fail}



def _send_year_notification(s3, year: int, stats: dict):
    """当一年的回填完成时，通过 SNS 发送邮件通知。"""
    try:
        sns = boto3.client('sns', region_name='ap-southeast-1')
        subject = f"☁️ Satellite Backfill Complete: {year}"
        message = (
            f"Year {year} satellite data backfill finished!\n\n"
            f"  Days processed : {stats['days']}\n"
            f"  Frames uploaded: {stats['uploaded']}\n"
            f"  Frames failed  : {stats['failed']}\n"
            f"  Days skipped   : {stats['skipped']}\n\n"
            f"S3 path: s3://{S3_BUCKET}/processed/satellite/{year}*/\n"
        )
        sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=message)
        logger.info(f"📧 [Backfill] Year {year} completion notification sent")
    except Exception as e:
        logger.warning(f"Failed to send SNS notification for year {year}: {e}")


def backfill_thread():
    """历史回填：逐日从 NOAA Open Data 下载缺失的卫星数据。"""
    logger.info("🔵 Backfill Thread Started (NOAA Open Data)")
    s3 = get_s3_client()

    s = datetime.strptime(START_DATE, "%Y-%m-%d")
    e = datetime.strptime(END_DATE, "%Y-%m-%d")

    current = s
    # 年度统计：检测年份切换时发送通知
    current_year = current.year
    year_stats = {"days": 0, "uploaded": 0, "failed": 0, "skipped": 0}

    while True:
        if current > e:
            # 最后一年的通知
            if year_stats["days"] + year_stats["skipped"] > 0:
                _send_year_notification(s3, current_year, year_stats)
            logger.info("🔄 [Backfill] Cycle complete. Restarting in 4 hours.")
            time.sleep(CHECK_INTERVAL_BACKFILL)
            current = s
            e = datetime.now() - timedelta(days=1)
            current_year = current.year
            year_stats = {"days": 0, "uploaded": 0, "failed": 0, "skipped": 0}
            continue

        # 年份切换时发送通知
        if current.year != current_year:
            _send_year_notification(s3, current_year, year_stats)
            current_year = current.year
            year_stats = {"days": 0, "uploaded": 0, "failed": 0, "skipped": 0}

        date_str = current.strftime("%Y-%m-%d")
        date_compact = current.strftime("%Y%m%d")

        if check_s3_exists(date_compact):
            logger.info(f"✅ [Backfill] {date_str} exists. Skipping.")
            year_stats["skipped"] += 1
        else:
            logger.info(f"⬇️ [Backfill] Processing {date_str}...")
            update_status("backfill", date_str, "downloading")
            result = _process_day_noaa(current, s3)
            logger.info(f"⬇️ [Backfill] {date_str}: {result['uploaded']}↑ {result['failed']}❌ / {result['total']}")

            year_stats["days"] += 1
            year_stats["uploaded"] += result["uploaded"]
            year_stats["failed"] += result["failed"]

            if result["uploaded"] > 0:
                try:
                    s3.put_object(
                        Bucket=S3_BUCKET,
                        Key=f"processed/satellite/{date_compact}/.complete",
                        Body=""
                    )
                except Exception as ex:
                    logger.error(f"❌ Failed to upload marker: {ex}")

        current += timedelta(days=1)
        time.sleep(1)

# --- Thread 3: Gov Data ---
def gov_data_thread():
    logger.info("🟢 Gov Data Thread Started")
    s3 = get_s3_client()
    
    while True:
        try:
            logger.info("📡 [GovData] Fetching recent sensor data...")
            # Run the script
            # We assume it is in the same directory
            cmd = ["python", "fetch_and_process_gov_data.py"]
            subprocess.run(cmd, check=True)
            
            # Check if file exists
            if os.path.exists("real_sensor_data.csv"):
                logger.info("📤 [GovData] Uploading to S3...")
                s3.upload_file("real_sensor_data.csv", S3_BUCKET, "govdata/real_sensor_data.csv")
                logger.info("✅ [GovData] Upload Complete")
            else:
                logger.warning("⚠️ [GovData] real_sensor_data.csv not found after script run.")
                
        except Exception as e:
            logger.error(f"❌ [GovData] Failed: {e}")
            
        # Sleep 4 hours
        time.sleep(14400)

def main():
    logger.info("🚀 Download Server Orchestrator Starting (NOAA Open Data)...")

    # Verify S3 connection
    try:
        s3 = get_s3_client()
        s3.list_buckets()
        logger.info("✅ S3 Connection OK")

        if S3_ENDPOINT_URL:
            try:
                s3.head_bucket(Bucket=S3_BUCKET)
            except Exception:
                logger.info(f"🔧 Creating bucket {S3_BUCKET} for local simulation...")
                s3.create_bucket(Bucket=S3_BUCKET)
    except Exception as e:
        logger.error(f"❌ S3 Connection Failed: {e}")

    # Start Threads
    t1 = threading.Thread(target=realtime_thread, daemon=True)
    t2 = threading.Thread(target=backfill_thread, daemon=True)
    t3 = threading.Thread(target=gov_data_thread, daemon=True)

    t1.start()
    t2.start()
    t3.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("🛑 Stopping Download Server...")

if __name__ == "__main__":
    main()
