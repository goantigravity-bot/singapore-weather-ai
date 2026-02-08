import boto3
import requests
import os
import sys

def check_status():
    bucket = os.environ.get("S3_BUCKET")
    print(f"🔍 Verifying Production Status for bucket: {bucket}...")
    
    if not bucket:
        print("❌ S3_BUCKET not set. Did you source prod_env_setup.sh?")
        return

    # 1. Check S3 Assets
    s3 = boto3.client('s3')
    
    files_to_check = [
        "govdata/real_sensor_data.csv",
        "models/latest.pth" 
    ]
    
    all_files_ok = True
    print("\n📦 Checking S3 Assets:")
    for key in files_to_check:
        try:
            s3.head_object(Bucket=bucket, Key=key)
            print(f"   ✅ Found: {key}")
        except Exception as e:
            print(f"   ❌ MISSING: {key}")
            if "models" in key:
                 print("      -> Run 'python train.py' in training/ folder.")
            if "govdata" in key:
                 print("      -> Run 'python download_manager.py' in download/ folder.")
            all_files_ok = False
            
    # 2. Check API Health
    print("\n🌐 Checking API Service (localhost:8000)...")
    try:
        resp = requests.get("http://localhost:8000/health", timeout=2)
        if resp.status_code == 200:
             print("   ✅ API is Running & Healthy.")
        else:
             print(f"   ⚠️ API Running but returned {resp.status_code}: {resp.text}")
             
        # Try a prediction
        if all_files_ok:
            print("   🧪 Testing Prediction...")
            try:
                # Predict for Clementi
                pred_resp = requests.get("http://localhost:8000/predict?location=Clementi", timeout=5)
                if pred_resp.status_code == 200:
                    data = pred_resp.json()
                    print(f"   ✅ Prediction Success: {data.get('recommendation', 'No Rec')}")
                else:
                    print(f"   ❌ Prediction Failed ({pred_resp.status_code}): {pred_resp.text}")
            except Exception as e:
                print(f"   ❌ Prediction Error: {e}")
                
    except requests.exceptions.ConnectionError:
        print("   ❌ API Not Reachable (Is it running? 'uvicorn api:app --reload')")
    except Exception as e:
        print(f"   ❌ API Check Failed: {e}")

if __name__ == "__main__":
    check_status()
