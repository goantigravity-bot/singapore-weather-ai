import ftplib
import os
import ssl
from datetime import datetime, timedelta
import time
import subprocess
import re

# --- USER CONFIGURATION ---
# Please register at https://www.eorc.jaxa.jp/ptree/registration_top.html
# Set credentials via environment variables or replace these placeholders
JAXA_USER = os.environ.get("JAXA_USER", "your-jaxa-username")
JAXA_PASS = os.environ.get("JAXA_PASS", "your-jaxa-password")

# Target Directory
DOWNLOAD_DIR = "satellite_data"

# Himawari-9 target path (Full Disk)
# JAXA Path format: /jma/netcdf/YYYYMM/DD/
REMOTE_BASE_PATH = "/jma/netcdf"

# Helper: Run curl command
def run_curl_list(remote_path):
    """List files using curl."""
    # Note: --ftp-ssl is Explicit TLS. JAXA needs this.
    # -l lists filenames only
    cmd = [
        "curl", "-s", "--ftp-ssl", "-l",
        "--user", f"{JAXA_USER}:{JAXA_PASS}",
        f"ftp://ftp.ptree.jaxa.jp{remote_path}/"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.splitlines()
    except subprocess.CalledProcessError as e:
        print(f"Curl list failed for {remote_path}: {e}")
        return []

def run_curl_download(remote_path, file_name, local_path):
    """Download file using curl."""
    url = f"ftp://ftp.ptree.jaxa.jp{remote_path}/{file_name}"
    cmd = [
        "curl", "-s", "--ftp-ssl",
        "--user", f"{JAXA_USER}:{JAXA_PASS}",
        url, "-o", local_path
    ]
    try:
        print(f"Downloading {file_name} via curl...")
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Curl download failed: {e}")
        return False

def download_latest_files(hours_to_check=1):
    now = datetime.utcnow()
    
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    # Check last N hours
    for h in range(hours_to_check + 1):
        target_time = now - timedelta(hours=h)
        year_mo = target_time.strftime("%Y%m")
        day = target_time.strftime("%d")
        
        remote_path = f"{REMOTE_BASE_PATH}/{year_mo}/{day}"
        
        files = run_curl_list(remote_path)
        
        # Filter for Full Disk (FLDK) using Regex
        # Expected: NC_H09_YYYYMMDD_HHMM_R21_FLDK.06001_06001.nc (or 07001)
        pattern = re.compile(r"^NC_H09_\d{8}_\d{4}_R21_FLDK\.0[67]001_06001\.nc$")
        target_files = [f for f in files if pattern.match(f)]
        
        for file_name in target_files:
            local_path = os.path.join(DOWNLOAD_DIR, file_name)
            
            if os.path.exists(local_path):
                continue
            
            run_curl_download(remote_path, file_name, local_path)

    print("Download cycle complete.")

# --- S3 Config ---
S3_BUCKET = os.environ.get("S3_BUCKET", None) # e.g. "my-weather-data"
S3_PREFIX = os.environ.get("S3_PREFIX", "satellite_raw")

def upload_to_s3(local_path, file_name):
    """Upload a file to S3."""
    if not S3_BUCKET: return
    
    endpoint_url = os.environ.get("S3_ENDPOINT_URL")
    
    import boto3
    s3 = boto3.client('s3', endpoint_url=endpoint_url)
    
    s3_key = f"{S3_PREFIX}/{file_name}"
    print(f"  > Uploading to s3://{S3_BUCKET}/{s3_key} ...")
    try:
        s3.upload_file(local_path, S3_BUCKET, s3_key)
        # Optional: Delete local file after upload to save space?
        # os.remove(local_path) 
    except Exception as e:
        print(f"  > S3 Upload Failed: {e}")

def download_range(start_date, end_date):
    """Download all files between start_date and end_date."""
    # No connect_ftp needed for curl
    
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    current = start_date
    while current <= end_date:
        # Check hourly
        year_mo = current.strftime("%Y%m")
        day = current.strftime("%d")
        remote_path = f"{REMOTE_BASE_PATH}/{year_mo}/{day}"
        
        files = run_curl_list(remote_path)
        
        # Filter for Full Disk (FLDK) using Regex
        pattern = re.compile(r"^NC_H09_\d{8}_\d{4}_R21_FLDK\.0[67]001_06001\.nc$")
        target_files = [f for f in files if pattern.match(f)]
        
        for file_name in target_files:
            # Check if file timestamp matches current hour?
            # Or just download all in that folder if in range?
            # download_range usually implies getting everything for that day/hour.
            # JAXA organizes by Day folder. Logic:
            # If we iterate by Hour, we might list the same folder 24 times.
            # Optimization: List only when day changes?
            # Current logic iterates hours.
            
            # Extract timestamp from filename to check finer granularity if needed
            # NC_H09_20251201_0000_...
            if current.strftime("%H%M") in file_name:
                local_path = os.path.join(DOWNLOAD_DIR, file_name)
                
                if not os.path.exists(local_path):
                    if run_curl_download(remote_path, file_name, local_path):
                        # Upload to S3 if configured
                        if S3_BUCKET:
                            upload_to_s3(local_path, file_name)
                else:
                    pass 

        current += timedelta(hours=1)
    
    print("Batch download complete.")

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daemon", "batch"], default="daemon", help="Run as daemon (watch latest) or batch (download history)")
    parser.add_argument("--hours", type=int, default=1, help="Hours back to check (for daemon or simple batch)")
    parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD (for batch)")
    parser.add_argument("--end", type=str, help="End date YYYY-MM-DD (for batch)")
    
    args = parser.parse_args()

    # Check Credentials
    # Allow ENV override
    global JAXA_USER, JAXA_PASS
    JAXA_USER = os.environ.get("JAXA_USER", JAXA_USER)
    JAXA_PASS = os.environ.get("JAXA_PASS", JAXA_PASS)

    if JAXA_USER == "input_your_username" or JAXA_USER == "jinhui.sg_gmail.com":
        if JAXA_USER == "input_your_username":
            print("ERROR: Set JAXA_USER/PASS in script or env vars!")
            return
            
    if S3_BUCKET:
        print(f"S3 Backup Enabled: s3://{S3_BUCKET}/{S3_PREFIX}")

    if args.mode == "batch":
        print("Starting JAXA Batch Downloader...")
        if args.start and args.end:
            s = datetime.strptime(args.start, "%Y-%m-%d")
            e = datetime.strptime(args.end, "%Y-%m-%d") + timedelta(hours=23) # End of day
            download_range(s, e)
        else:
             print("Batch mode usually requires --start and --end. Falling back to latest check.")
             # For simpler logic, just use download_range for last N hours
             e = datetime.utcnow()
             s = e - timedelta(hours=args.hours)
             download_range(s, e)
    else:
        # Daemon Mode (Not actively updated for S3 in this snippet for brevity, but follows same logic)
        print("Starting JAXA Satellite Downloader (Daemon)...")
        # ... logic similar to batch ...
        # (Placeholder for daemon logic)
        download_latest_files(args.hours)

if __name__ == "__main__":
    main()

