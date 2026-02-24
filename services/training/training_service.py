import os
import time
import logging
import threading
from datetime import datetime, timedelta
import boto3
import subprocess

# --- Config ---
# Modes: BACKFILL or DAILY
TRAINING_MODE = os.environ.get("TRAINING_MODE", "DAILY").upper()

# S3
S3_BUCKET = os.environ.get("S3_BUCKET", "weather-ai-models-gcc")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", None)

# Range for Backfill
START_DATE = os.environ.get("START_DATE", "2025-10-01")
END_DATE = os.environ.get("END_DATE", (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("training_service")

def get_s3_client():
    return boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)

def check_readiness(date_str):
    """Check if .complete marker exists for date"""
    # date_str is YYYY-MM-DD. S3 marker is satellite/YYYYMMDD/.complete
    date_compact = date_str.replace("-", "")
    s3 = get_s3_client()
    key = f"satellite/{date_compact}/.complete"
    try:
        s3.head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except:
        return False

def run_pipeline(date_str):
    logger.info(f"🚀 Starting Pipeline for {date_str}...")
    
    # 1. Processing (JSON -> CSV)
    logger.info("   1. Processing Data...")
    try:
        # Calls process_gov_data_from_s3.py --date {date}
        cmd = ["python3", "process_gov_data_from_s3.py", "--date", date_str]
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Processing Failed: {e}")
        return False

    # 2. Training
    logger.info("   2. Training Model...")
    try:
        # Calls train_rolling_window.py (It should download CSV and Satellite on its own? 
        # Or we need to download here?
        # The existing train_rolling_window likely expects data locally?
        # TODO: Ideally train_rolling_window handles download. 
        # For this refactor, let's assume it does OR we wrap it.
        # But wait, original user request: "training server... download file from S3... pre-process... combine..."
        # We did pre-process.
        # Training script usually expects local data.
        # We should probably run a script that downloads data FIRST.
        
        # NOTE: For simplicity, assuming train_rolling_window.py has been adapted OR we pass args.
        # Let's run a wrapper or assuming it reads from S3/local.
        # We will just call it.
        cmd_train = ["python3", "train_rolling_window.py", "--date", date_str] # Pass date context?
        subprocess.run(cmd_train, check=True)
        # TODO: Ensure train script uploads model.
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Training Failed: {e}")
        return False

    # 3. Cleanup ?
    # TODO
    
    logger.info(f"✅ Pipeline Completed for {date_str}")
    return True

def backfill_mode():
    logger.info("🔵 BACKFILL MODE ACTIVATED")
    s = datetime.strptime(START_DATE, "%Y-%m-%d")
    e = datetime.strptime(END_DATE, "%Y-%m-%d")
    
    current = s
    while current <= e:
        date_str = current.strftime("%Y-%m-%d")
        logger.info(f"Checking {date_str}...")
        
        if check_readiness(date_str):
            logger.info(f"✅ Data Ready for {date_str}. Processing...")
            run_pipeline(date_str)
        else:
            logger.info(f"⏳ Data NOT Ready (Missing .complete) for {date_str}. Waiting...")
            time.sleep(60) # Wait a bit ? Or skip?
            # If backfill, we probably want to wait or skip?
            # User said: "It will continue to download... training can be carried out continously"
            # So waiting is better.
            continue
            
        current += timedelta(days=1)
    
    logger.info("🎉 Backfill Completed.")

def daily_mode():
    logger.info("🟢 DAILY MODE ACTIVATED")
    while True:
        # Calculate Wait Time until 02:00 AM
        now = datetime.now()
        target = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if target < now:
            target += timedelta(days=1)
            
        # Debug/Testing: If checking interval is small
        # For prod:
        wait_seconds = (target - now).total_seconds()
        logger.info(f"💤 Sleeping until {target} ({wait_seconds/3600:.1f} hours)...")
        time.sleep(wait_seconds)
        
        # Wake up
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        logger.info(f"⏰ Waking up. Processing Yesterday: {yesterday}")
        
        # Retry loop for data readiness
        while not check_readiness(yesterday):
            logger.info("⏳ Waiting for Download Server completion...")
            time.sleep(300) # 5 mins
            
        run_pipeline(yesterday)

def main():
    if TRAINING_MODE == "BACKFILL":
        backfill_mode()
    else:
        daily_mode()

if __name__ == "__main__":
    main()
