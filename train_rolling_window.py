import os
import argparse
import subprocess
from datetime import datetime, timedelta, timezone
import time
import shutil
import json

# --- S3 Configuration for Status Updates ---
S3_BUCKET = os.environ.get("S3_BUCKET", None)
S3_PREFIX = os.environ.get("S3_PREFIX", "satellite_raw")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", None)

def update_status(state):
    """Upload training state to S3."""
    if not S3_BUCKET: return

    # Add timestamp
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    
    # Save locally first
    local_path = "rolling_training_state.json"
    with open(local_path, "w") as f:
        json.dump(state, f, indent=2)

    # Upload to S3
    try:
        import boto3
        s3 = boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)
        s3_key = "state/rolling_training_state.json"
        s3.upload_file(local_path, S3_BUCKET, s3_key)
    except Exception as e:
        print(f"[WARNING] Failed to update status: {e}")

def get_history():
    """Fetch existing history from S3."""
    if not S3_BUCKET: return []
    try:
        import boto3
        s3 = boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)
        obj = s3.get_object(Bucket=S3_BUCKET, Key="history/training_history.json")
        return json.loads(obj['Body'].read().decode('utf-8'))
    except Exception as e:
        return []

def update_history(run_data):
    """Append new run to history and upload."""
    if not S3_BUCKET: return
    
    history = get_history()
    # Add ID if missing
    if not history:
        run_data["id"] = 1
    else:
        run_data["id"] = history[-1].get("id", 0) + 1
        
    history.append(run_data)
    
    # Keep last 50
    if len(history) > 50:
        history = history[-50:]
        
    local_path = "training_history.json"
    with open(local_path, "w") as f:
        json.dump(history, f, indent=2)
        
    try:
        import boto3
        s3 = boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)
        s3.upload_file(local_path, S3_BUCKET, "history/training_history.json")
    except Exception as e:
        print(f"[WARNING] Failed to update history: {e}")

def run_command(cmd_str):
    print(f"\n[EXEC] {cmd_str}")
    try:
        # Use shell=True for easier environment variable handling if needed, 
        # but list format is safer. sticking to string for simplicity with simple args.
        subprocess.check_call(cmd_str, shell=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Command failed: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Rolling Window Training Wrapper")
    parser.add_argument("--start", required=True, help="Overall start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Overall end date YYYY-MM-DD")
    parser.add_argument("--batch-days", type=int, default=10, help="Days per batch")
    parser.add_argument("--epochs", type=int, default=5, help="Epochs per batch")
    parser.add_argument("--mock-data", action="store_true", help="Skip data fetching for testing")
    
    args = parser.parse_args()
    
    start_date = datetime.strptime(args.start, "%Y-%m-%d")
    end_date = datetime.strptime(args.end, "%Y-%m-%d")
    
    current_start = start_date
    
    # Ensure directories exist
    os.makedirs("satellite_data", exist_ok=True)
    
    batch_idx = 1
    total_days = (end_date - start_date).days
    total_batches = (total_days // args.batch_days) + 1
    
    status = {"status": "pending"}

    while current_start <= end_date:
        current_end = min(current_start + timedelta(days=args.batch_days - 1), end_date)
        
        s_str = current_start.strftime("%Y-%m-%d")
        e_str = current_end.strftime("%Y-%m-%d")
        
        print(f"\n{'='*60}")
        print(f"BATCH {batch_idx}/{total_batches}: {s_str} to {e_str}")
        print(f"{'='*60}")
        
        # Base status
        status = {
            "status": "active",
            "current_batch": batch_idx,
            "total_batches": total_batches,
            "batch_start": s_str,
            "batch_end": e_str
        }

        # 1. Fetch Sensor Data
        # We use env vars for fetch_and_process_gov_data.py
        print("1. Fetching Sensor Data...")
        status["current_step"] = "Fetching Sensor Data"
        update_status(status)
        
        if not args.mock_data:
            # 使用本地 govdata JSON 生成 CSV，而非调用 NEA API
            # 调度器已从 S3 下载了对应日期的 JSON 到 govdata/ 目录，
            # convert_govdata_to_csv.py 会自动转换所有 JSON 为时间对齐的 CSV
            cmd_sensor = "python3 convert_govdata_to_csv.py"
            if not run_command(cmd_sensor):
                print("Failed to convert govdata to CSV. Skipping batch.")
                status["status"] = "failed"
                status["error"] = "Govdata conversion failed"
                update_status(status)
                break
        else:
             print(" [MOCK] Skipping sensor data fetch. Ensuring data file exists.")
             if not os.path.exists("real_sensor_data.csv"):
                 if os.path.exists("dummy_data/sensor_readings.csv"):
                     shutil.copy("dummy_data/sensor_readings.csv", "real_sensor_data.csv")
                 else:
                     print("Warning: No sensor data found for mock run.")
            
        # 2 & 3: 卫星数据下载和预处理已由 training_scheduler.py 完成
        # 调度器从 S3 下载 .nc 文件并调用 preprocess_images.py 生成 .npy
        # 此处无需重复执行

        # 4. Train
        print(f"4. Training (Epochs: {args.epochs})...")
        status["current_step"] = "Training Model"
        update_status(status)

        # 首次训练使用完整 epochs，增量训练使用较少的 epochs
        # 实际数据表明增量训练在 1-3 个 epoch 即收敛，配合 Early Stopping 自动终止
        incremental_epochs = max(5, args.epochs // 10)
        cmd_train = f"export EPOCHS_INITIAL={args.epochs} && export EPOCHS_INCREMENTAL={incremental_epochs} && export PYTHONUNBUFFERED=1 && python3 train.py" 
        
        train_start_time = time.time()
        if not run_command(cmd_train):
            print("Training failed.")
            status["status"] = "failed"
            status["error"] = "Training failed"
            update_status(status)
            status["status"] = "failed"
            status["error"] = "Training failed"
            update_status(status)
            break
        
        train_duration = time.time() - train_start_time
        print(f"Training Batch Completed in {train_duration:.1f}s")
        update_status(status)

            
        # 4.5 Capture Metrics & Update History
        metrics = {}
        if os.path.exists("training_metrics.json"):
             with open("training_metrics.json", "r") as f:
                 metrics = json.load(f)
                 
        # Create History Entry
        batch_duration = "Unknown" # simplified
        history_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_formatted": "N/A", # placeholder
            "success": True,
            "metrics": {
                "mae": metrics.get("last_val_mae", 0.0),
                "rmse": metrics.get("rmse", 0.0),
                "accuracy": 0.0 # Not applicable for regression
            },
            "data_info": {
                "date_range": f"{s_str} to {e_str}",
                "sensor_records": 0 # placeholder
            }
        }
        update_history(history_entry)
            
        # 5. Sync to S3 (Checkpoint)
        print("5. Syncing Checkpoint to S3...")
        status["current_step"] = "Syncing Checkpoint"
        update_status(status)

        # Optional: Setup a specific sync script or valid aws command
        run_command("./sync_model_to_s3.sh")

        # 6. Cleanup
        print("6. Cleaning up batch data...")
        status["current_step"] = "Cleaning Up"
        update_status(status)

        # Delete satellite images to free space
        # careful with wildcards
        os.system("rm -f satellite_data/*.nc")
        os.system("rm -f satellite_data/*.npy") # If preprocess output is here
        # Also clean processed images folder if it exists
        if os.path.exists("processed_images"):
            shutil.rmtree("processed_images")
            os.makedirs("processed_images", exist_ok=True)
            
        # Move to next batch
        current_start = current_end + timedelta(days=1)
        batch_idx += 1
        
        # Optional: Sleep to let system cool down?
        time.sleep(5)
        
    print("\nRolling Training Complete!")
    status["status"] = "completed"
    status["current_step"] = "Done"
    update_status(status)

if __name__ == "__main__":
    main()
