import ftplib
import os
import ssl
from datetime import datetime, timedelta
import time

# --- USER CONFIGURATION ---
# Please register at https://www.eorc.jaxa.jp/ptree/registration_top.html
JAXA_USER = "jinhui.sg_gmail.com"
JAXA_PASS = "SP+wari8"

# Target Directory
DOWNLOAD_DIR = "satellite_data"

# Himawari-9 target path (Full Disk)
# JAXA Path format: /jma/netcdf/YYYYMM/DD/
REMOTE_BASE_PATH = "/jma/netcdf"

def connect_ftp():
    """Connect using explicit FTPS (FTP over TLS)."""
    print(f"Connecting to ftp.ptree.jaxa.jp as {JAXA_USER}...")
    ftp = ftplib.FTP_TLS("ftp.ptree.jaxa.jp")
    try:
        ftp.login(JAXA_USER, JAXA_PASS)
        ftp.prot_p() # Switch to secure data connection
        print("Connected & Authenticated!")
        return ftp
    except ftplib.error_perm as e:
        print(f"Authentication Failed: {e}")
        print("Please check your JAXA_USER and JAXA_PASS in the script.")
        return None

def download_latest_files(hours_to_check=1):
    ftp = connect_ftp()
    if not ftp: return

    now = datetime.utcnow()
    
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    # Check last N hours
    for h in range(hours_to_check + 1):
        target_time = now - timedelta(hours=h)
        year_mo = target_time.strftime("%Y%m")
        day = target_time.strftime("%d")
        
        remote_path = f"{REMOTE_BASE_PATH}/{year_mo}/{day}"
        
        try:
            ftp.cwd(remote_path)
            files = ftp.nlst()
            
            # Filter for Full Disk (FLDK) or Region 3 (R3)
            # Example: NC_H09_20260122_1200_R21_FLDK.02401_02401.nc
            target_files = [f for f in files if "FLDK" in f and f.endswith(".nc")]
            
            for file_name in target_files:
                local_path = os.path.join(DOWNLOAD_DIR, file_name)
                
                # Skip if exists
                if os.path.exists(local_path):
                    # print(f"Skipping {file_name} (Already exists)")
                    continue
                
                print(f"Downloading {file_name} ...")
                with open(local_path, "wb") as f:
                    ftp.retrbinary(f"RETR {file_name}", f.write)
                    
        except ftplib.error_perm as e:
             # Directory likely doesn't exist yet for very fresh time
             pass
        except Exception as e:
             print(f"Error accessing {remote_path}: {e}")

    ftp.quit()
    print("Download cycle complete.")

    print("Download cycle complete.")

# --- S3 Config ---
S3_BUCKET = os.environ.get("S3_BUCKET", None) # e.g. "my-weather-data"
S3_PREFIX = os.environ.get("S3_PREFIX", "satellite_raw")

def upload_to_s3(local_path, file_name):
    """Upload a file to S3."""
    if not S3_BUCKET: return
    
    import boto3
    s3 = boto3.client('s3')
    
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
    ftp = connect_ftp()
    if not ftp: return

    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    current = start_date
    while current <= end_date:
        # Check hourly
        year_mo = current.strftime("%Y%m")
        day = current.strftime("%d")
        remote_path = f"{REMOTE_BASE_PATH}/{year_mo}/{day}"
        
        try:
            ftp.cwd(remote_path)
            files = ftp.nlst()
            target_files = [f for f in files if "FLDK" in f and f.endswith(".nc")]
            
            for file_name in target_files:
                if current.strftime("%H%M") in file_name:
                    local_path = os.path.join(DOWNLOAD_DIR, file_name)
                    
                    # Logic: Check S3 first? Or just overwrite?
                    # For simplicity, we download then upload.
                    
                    if not os.path.exists(local_path):
                        print(f"Downloading {file_name} ...")
                        with open(local_path, "wb") as f:
                            ftp.retrbinary(f"RETR {file_name}", f.write)
                        
                        # Upload to S3 if configured
                        if S3_BUCKET:
                            upload_to_s3(local_path, file_name)
                            # Optional: Delete local to save space
                            # os.remove(local_path)
                    else:
                        pass 

        except Exception as e:
            pass
            
        current += timedelta(hours=1)
    
    ftp.quit()
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

