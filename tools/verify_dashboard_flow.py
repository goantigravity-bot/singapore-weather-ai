import boto3
import json
import os
import subprocess
import time
import requests
from datetime import datetime, timedelta, timezone

# Config from context
S3_BUCKET = "weather-ai-models-de08370c"
S3_ENDPOINT_URL = "http://127.0.0.1:5000"
API_URL = "http://127.0.0.1:8000"

os.environ["S3_BUCKET"] = S3_BUCKET
os.environ["S3_ENDPOINT_URL"] = S3_ENDPOINT_URL
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

def reset_s3():
    print("Resetting S3 state...")
    s3 = boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)
    # Create bucket if not exists (Moto starts empty)
    try:
        s3.create_bucket(Bucket=S3_BUCKET)
    except: pass # Already exists

    # Clear state
    try:
        s3.delete_object(Bucket=S3_BUCKET, Key="state/training_state.json")
    except: pass
    
    # ... (rest of reset logic is fine)
    
    # Set to IDLE initially
    idle_state = {
        "status": "idle",
        "current_batch": 0,
        "total_batches": 0,
        "current_step": "Ready",
        "batch_start": "-",
        "batch_end": "-",
        "last_updated": datetime.now(timezone.utc).isoformat()
    }
    s3.put_object(Bucket=S3_BUCKET, Key="state/training_state.json", Body=json.dumps(idle_state))

def run_training_script():
    print("Running training script (short duration)...")
    # Run for 2 days ago to yesterday (1 batch)
    start = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    cmd = [
        "python3", "-u", "train_rolling_window.py",
        "--start", start,
        "--end", end,
        "--batch-days", "1",
        "--epochs", "1",
        "--mock-data"
    ]
    
    # We expect this to likely fail on sensor data fetch if no keys, which is fine.
    # We just want to see the status update.
    subprocess.run(cmd, env=os.environ, capture_output=False) # Let it print to stdout

def check_status_and_history():
    print("Checking API Status...")
    try:
        r_status = requests.get(f"{API_URL}/training/status")
        status = r_status.json()
        print(f"Current Status: {status.get('status')} - {status.get('current_step')}")
        
        r_hist = requests.get(f"{API_URL}/training/history")
        history = r_hist.json()
        print(f"History Count: {len(history)}")
        if history:
            last = history[-1]
            print(f"Last Run: Success={last.get('success')}, Metrics={last.get('metrics')}")
            
        return status, history
    except Exception as e:
        print(f"API Check Failed: {e}")
        return None, None

if __name__ == "__main__":
    reset_s3()
    time.sleep(1)
    
    start_status, start_history = check_status_and_history()
    if start_status.get('status') != 'idle':
        print("WARNING: Status didn't reset to idle properly.")
        
    run_training_script()
    
    print("\n--- Post Run Check ---")
    end_status, end_history = check_status_and_history()
    
    # Verification criteria
    # 1. Status should be 'failed' (if fetch failed) or 'completed' (if everything worked mocked)
    # 2. History should have +1 entry.
    
    if end_status.get('status') in ['failed', 'completed']:
        print("SUCCESS: Status updated correctly.")
    else:
        print(f"FAILURE: Status is {end_status.get('status')}, expected completed/failed.")
        
    if end_history and len(end_history) > len(start_history or []):
         print("SUCCESS: History entry added.")
         last_metrics = end_history[-1].get('metrics', {})
         if "rmse" in last_metrics:
             print(f"SUCCESS: RMSE found in metrics: {last_metrics['rmse']}")
         else:
             print("FAILURE: RMSE missing from metrics.")
    else:
         print("FAILURE: History not updated.")

