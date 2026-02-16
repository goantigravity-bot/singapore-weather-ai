import boto3
from botocore import UNSIGNED
from botocore.config import Config
import os

BUCKET_NAME = "noaa-himawari8"
# Target path: noaa-himawari8/AHI-L1b-FLDK/2024/01/20/0400/
# We search for Band 13 files in this prefix.
PREFIX = "AHI-L1b-FLDK/2024/01/20/0400/" 

def download_with_boto3():
    print(f"Connecting to AWS S3 Bucket: {BUCKET_NAME} (Anonymous Mode)...")
    
    # Configure anonymous access (No keys needed)
    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))
    
    try:
        print(f"Listing objects in prefix: {PREFIX}")
        response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=PREFIX)
        
        if 'Contents' not in response:
            print("No files found! Bucket access OK, but path might be empty.")
            return

        # Find Band 13 (Infrared)
        target_key = None
        for obj in response['Contents']:
            key = obj['Key']
            # Look for B13 and .nc file
            if "B13" in key and key.endswith(".nc"):
                target_key = key
                break
        
        if not target_key:
            print("Files listed, but no Band 13 (.nc) file found.")
            # Print first few for debugging
            print("Sample files found:", [o['Key'] for o in response['Contents'][:3]])
            return

        local_filename = os.path.basename(target_key)
        print(f"Found file: {target_key}")
        print(f"Size: {response['Contents'][0]['Size'] / 1024 / 1024:.2f} MB")
        print(f"Downloading to: {local_filename} ...")
        
        s3.download_file(BUCKET_NAME, target_key, local_filename)
        print("\nDownload Complete!")
        
        # Verify with xarray
        import xarray as xr
        print("Verifying file integrity...")
        ds = xr.open_dataset(local_filename, engine="netcdf4")
        print(ds)
        ds.close()
        print("\nSUCCESS: Real data acquired.")

    except Exception as e:
        print(f"Main Error: {e}")

if __name__ == "__main__":
    download_with_boto3()
