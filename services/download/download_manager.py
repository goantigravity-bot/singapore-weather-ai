import os
import subprocess
import time
import logging
import threading
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError
from download_satellite import process_day, load_env

# --- Configuration ---
# 1. Real-Time Thread
CHECK_INTERVAL_REALTIME = int(os.environ.get("CHECK_INTERVAL_REALTIME", "300")) # 5 Minutes
# 2. Backfill Thread
CHECK_INTERVAL_BACKFILL = int(os.environ.get("CHECK_INTERVAL_BACKFILL", "14400")) # 4 Hours

# Date Range (For Backfill)
START_DATE = os.environ.get("START_DATE", "2025-10-01")
# Default End Date is Yesterday (Full history until today)
yest = datetime.now() - timedelta(days=1)
END_DATE = os.environ.get("END_DATE", yest.strftime("%Y-%m-%d"))

# S3 Config
S3_BUCKET = os.environ.get("S3_BUCKET", "weather-ai-models-de08370c")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", None)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("download_manager")

def get_s3_client():
    return boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)

def update_status(mode, date, status, sat_count=0):
    """Updates status to S3"""
    try:
        s3 = get_s3_client()
        import json
        status_data = {
            "last_updated": datetime.now().isoformat(),
            "mode": mode,
            "current_target_date": date,
            "satellite_files_count": sat_count,
            "status": status
        }
        # Save locally and upload
        # with open("download_state.json", "w") as f:
        #    json.dump(status_data, f)
        
        # s3.upload_file("download_state.json", S3_BUCKET, "state/download_state.json")
        
        # Use put_object to avoid ChecksumMismatch issues in some envs
        s3.put_object(
            Bucket=S3_BUCKET,
            Key="state/download_state.json",
            Body=json.dumps(status_data)
        )
    except Exception as e:
        logger.warning(f"Failed to update status: {e}")

def check_s3_exists(date_str):
    """Check if processed satellite .npy exists for this date."""
    s3 = get_s3_client()
    prefix = f"processed/satellite/{date_str}/"
    try:
        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix, MaxKeys=1)
        return 'Contents' in resp
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
def realtime_thread():
    """每 5 分钟下载+预处理今天的卫星数据（增量）。"""
    logger.info("🟢 Real-Time Thread Started")
    s3 = get_s3_client()
    while True:
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        logger.info(f"⚡ [RealTime] Processing {today_str}")
        update_status("real-time", today_str, "downloading")

        result = process_day(today_str, s3)
        logger.info(f"⚡ [RealTime] {today_str}: {result['uploaded']}↑ {result['skipped']}⏭ {result['failed']}❌")
        update_status("real-time", today_str, "sleeping")

        # 凌晨 0-2 点补查昨天
        if now.hour < 2:
            yest_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            logger.info(f"🌙 [RealTime] Late night check for {yest_str}")
            process_day(yest_str, s3)

        time.sleep(CHECK_INTERVAL_REALTIME)

# --- Thread 2: Backfill ---
def backfill_thread():
    """历史回填：逐日检查并下载+预处理缺失的卫星数据。"""
    logger.info("🔵 Backfill Thread Started")
    s3 = get_s3_client()

    s = datetime.strptime(START_DATE, "%Y-%m-%d")
    e = datetime.strptime(END_DATE, "%Y-%m-%d")

    current = s
    while True:
        if current > e:
            logger.info("🔄 [Backfill] Cycle complete. Restarting in 4 hours.")
            time.sleep(CHECK_INTERVAL_BACKFILL)
            current = s
            e = datetime.now() - timedelta(days=1)
            continue

        date_str = current.strftime("%Y-%m-%d")
        date_compact = current.strftime("%Y%m%d")

        if check_s3_exists(date_compact):
            logger.info(f"✅ [Backfill] {date_str} exists. Skipping.")
        else:
            logger.info(f"⬇️ [Backfill] Processing {date_str}...")
            update_status("backfill", date_str, "downloading")
            result = process_day(date_str, s3)

            if result["uploaded"] > 0:
                # 上传 .complete 标记
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
    logger.info("🚀 Download Server Orchestrator Starting...")

    # 加载 JAXA 凭证
    load_env()

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
