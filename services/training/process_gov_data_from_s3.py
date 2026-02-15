import os
import json
import boto3
import pandas as pd
import io
import argparse
import logging
from datetime import datetime

# Configuration
S3_BUCKET = os.environ.get("S3_BUCKET", "weather-ai-models-de08370c")
GOVDATA_PREFIX = "govdata"
PROCESSED_PREFIX = "processed"
OUTPUT_FILENAME = "real_sensor_data.csv"
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", None)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("process_gov_data")

# Region Mapping
REGION_CENTROIDS = {
    "north": {"lat": 1.41803, "lon": 103.8200},
    "south": {"lat": 1.29587, "lon": 103.8200},
    "east":  {"lat": 1.35735, "lon": 103.9400},
    "west":  {"lat": 1.35735, "lon": 103.7000},
    "central": {"lat": 1.35735, "lon": 103.8200}
}

def get_s3_client():
    return boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)

def get_region_from_latlon(lat, lon):
    min_dist = float('inf')
    best_region = "central"
    for region, coords in REGION_CENTROIDS.items():
        d = ((lat - coords['lat'])**2 + (lon - coords['lon'])**2)**0.5
        if d < min_dist:
            min_dist = d
            best_region = region
    return best_region

def list_json_files(date_str=None):
    """List JSON files. If date_str provided, filter by prefix govdata/YYYY-MM-DD/"""
    s3 = get_s3_client()
    files = []
    paginator = s3.get_paginator('list_objects_v2')
    
    prefix = f"{GOVDATA_PREFIX}/"
    if date_str:
        prefix = f"{GOVDATA_PREFIX}/" # Assumes YYYY-MM-DD folder structure in S3?
        # Verify if download_manager uses YYYY-MM-DD or YYYYMMDD?
        # bulk_download script usually uses YYYYMMDD. 
        # API usually returns YYYY-MM-DD in json.
        # Let's check download_manager logic. 
        # It uploads to govdata/{date}/ where date is YYYY-MM-DD from python call.
        # Wait, bulk_download...sh:
        #  aws s3 cp ... s3://$BUCKET_NAME/govdata/$DATE_STR/ ...
        # If DATE_STR is YYYY-MM-DD (passed from python), then it is dashes.
    
    logger.info(f"Listing files in s3://{S3_BUCKET}/{prefix}...")
    
    try:
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
            for obj in page.get('Contents', []):
                key = obj['Key']
                if key.endswith(".json") and (date_str is None or date_str in key):
                    files.append(key)
    except Exception as e:
        logger.warning(f"Error listing files: {e}")
        
    return files

def process_single_json(s3, key, station_region_map):
    """Process single JSON file from S3"""
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
        data = json.loads(obj['Body'].read().decode('utf-8'))
        
        dtype = 'unknown'
        if 'rainfall' in key: dtype = 'rainfall'
        elif 'temperature' in key: dtype = 'temperature'
        elif 'humidity' in key: dtype = 'humidity'
        elif 'pm25' in key: dtype = 'pm25'
        elif 'wind-speed' in key: dtype = 'wind_speed'
        elif 'wind-direction' in key: dtype = 'wind_direction'
        
        records = []

        # Wind v2 格式: {code, data: {readings: [{timestamp, data: [{stationId, value}]}]}}
        if dtype in ('wind_speed', 'wind_direction'):
            inner = data.get('data', {})
            if not isinstance(inner, dict):
                return []
            for reading in inner.get('readings', []):
                timestamp = reading.get('timestamp')
                for entry in reading.get('data', []):
                    records.append({
                        "timestamp": timestamp,
                        "sensor_id": entry['stationId'],
                        "type": dtype,
                        "value": entry['value']
                    })
            return records

        # v1 格式: {items: [{timestamp, readings: [{station_id, value}]}]}
        if not data or 'items' not in data:
            return []

        if dtype == 'pm25':
            for item in data['items']:
                timestamp = item['timestamp']
                if 'readings' not in item or 'pm25_one_hourly' not in item['readings']:
                    continue
                regional_readings = item['readings']['pm25_one_hourly']
                for sid, region_key in station_region_map.items():
                    if region_key in regional_readings:
                        val = regional_readings[region_key]
                        records.append({
                            "timestamp": timestamp,
                            "sensor_id": sid,
                            "type": "pm25",
                            "value": val
                        })
        else:
            for item in data['items']:
                timestamp = item['timestamp']
                for reading in item['readings']:
                    sid = reading['station_id']
                    val = reading['value']
                    records.append({
                        "timestamp": timestamp,
                        "sensor_id": sid,
                        "type": dtype,
                        "value": val
                    })
        return records
    except Exception as e:
        logger.warning(f"Error processing {key}: {e}")
        return []

def build_station_map(s3, temp_files):
    station_region_map = {}
    if not temp_files: return {}
    latest_file = sorted(temp_files)[-1]
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=latest_file)
        data = json.loads(obj['Body'].read().decode('utf-8'))
        if 'metadata' in data and 'stations' in data['metadata']:
            for s in data['metadata']['stations']:
                if 'location' in s and 'latitude' in s['location']:
                    lat = s['location']['latitude']
                    lon = s['location']['longitude']
                    sid = s['id']
                    station_region_map[sid] = get_region_from_latlon(lat, lon)
    except Exception as e:
        logger.error(f"Error reading metadata: {e}")
    return station_region_map

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Date to process (YYYY-MM-DD)", default=None)
    parser.add_argument("--reset", action="store_true", help="Start fresh (ignore existing CSV)")
    args = parser.parse_args()
    
    s3 = get_s3_client()
    
    # 1. Download Existing CSV (if not reset)
    existing_df = pd.DataFrame()
    if not args.reset:
        try:
            logger.info("Downloading existing real_sensor_data.csv...")
            obj = s3.get_object(Bucket=S3_BUCKET, Key=f"{PROCESSED_PREFIX}/{OUTPUT_FILENAME}")
            existing_df = pd.read_csv(io.BytesIO(obj['Body'].read()))
            logger.info(f"Loaded {len(existing_df)} existing rows.")
        except s3.exceptions.NoSuchKey:
            logger.info("No existing CSV found. Creating new.")
        except Exception as e:
            logger.warning(f"Error loading existing CSV: {e}")

    # 2. List Files
    all_files = list_json_files(args.date)
    logger.info(f"Found {len(all_files)} files to process for date={args.date}")
    
    if not all_files:
        logger.info("No files found. Exiting.")
        return # Nothing to do

    # 3. Build Map
    temp_files = [f for f in all_files if 'temperature' in f]
    # If explicit date has no temp files, we might fail to map stations?
    # TODO: Station Mapping should rely on a static/global mapping if possible.
    # For now, fallback to whatever we found logic.
    station_region_map = build_station_map(s3, temp_files)
    
    # 4. Process
    all_records = []
    for idx, key in enumerate(all_files):
        records = process_single_json(s3, key, station_region_map)
        all_records.extend(records)
    
    if not all_records:
        logger.info("No records extracted.")
        return

    # 5. DataFrame Construction
    new_df = pd.DataFrame(all_records)
    new_df['timestamp'] = pd.to_datetime(new_df['timestamp'])
    
    # Pivot New Data
    new_pivot = new_df.pivot_table(
        index=['timestamp', 'sensor_id'], 
        columns='type', 
        values='value',
        aggfunc='mean'
    ).reset_index()
    
    # Standardize Columns
    required = ['temperature', 'rainfall', 'humidity', 'pm25', 'wind_speed', 'wind_direction']
    for col in required:
        if col not in new_pivot.columns:
            new_pivot[col] = 0.0
            
    # 6. Merge with Existing
    if not existing_df.empty:
        # Ensure timestamp match
        existing_df['timestamp'] = pd.to_datetime(existing_df['timestamp'])
        # Concat
        combined_df = pd.concat([existing_df, new_pivot])
        # Deduplicate (Overwrite old with new if distinct? no, just distinct timestamp+sensor)
        # sort by timestamp desc to keep latest?
        combined_df = combined_df.drop_duplicates(subset=['timestamp', 'sensor_id'], keep='last')
    else:
        combined_df = new_pivot

    # 7. Final Polish
    combined_df = combined_df.sort_values(['sensor_id', 'timestamp'])
    combined_df = combined_df.ffill().fillna(0.0) # Forward fill gaps
    
    # 8. Upload
    csv_buffer = io.StringIO()
    combined_df.to_csv(csv_buffer, index=False)
    
    target_key = f"{PROCESSED_PREFIX}/{OUTPUT_FILENAME}"
    logger.info(f"Uploading {len(combined_df)} rows to s3://{S3_BUCKET}/{target_key}...")
    s3.put_object(Bucket=S3_BUCKET, Key=target_key, Body=csv_buffer.getvalue())
    # Save locally for train_rolling_window.py
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), OUTPUT_FILENAME)
    combined_df.to_csv(local_path, index=False)
    logger.info(f"Local CSV saved: {local_path} ({len(combined_df)} rows)")

    logger.info("✅ Done.")

if __name__ == "__main__":
    main()
