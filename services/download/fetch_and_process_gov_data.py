import requests
import pandas as pd
import datetime
import os
import time

# --- Configuration ---
# FETCH_CONFIG can contain:
# 1. Single datetime.date objects: datetime.date(2026, 1, 22)
# 2. Dictionaries with 'start' and 'end' keys: {'start': ..., 'end': ...}
FETCH_CONFIG = [
    # 2023 ~ 2025 全量历史数据
    {'start': datetime.date(2023, 1, 1), 'end': datetime.date(2025, 12, 31)},
]

# 🆕 Check Environment Variables (Override/Append)
if os.environ.get('FETCH_START_DATE') and os.environ.get('FETCH_END_DATE'):
    try:
        s = datetime.date.fromisoformat(os.environ.get('FETCH_START_DATE'))
        e = datetime.date.fromisoformat(os.environ.get('FETCH_END_DATE'))
        print(f"Adding Env Config: {s} to {e}")
        FETCH_CONFIG.insert(0, {'start': s, 'end': e})
        # Optional: Clear others if you want STRICT env control
        # FETCH_CONFIG = [{'start': s, 'end': e}]
    except ValueError as err:
        print(f"Error parsing env dates: {err}")

OUTPUT_FILE = "real_sensor_data.csv"
# TODO: Replace with your actual .pem or .crt file path
# CUSTOM_CERT_PATH = "/path/to/your/custom_root_ca.pem"
CUSTOM_CERT_PATH = "${HOME}/.config/cloudflare/combined-bundle.pem"

# API Endpoints
BASE_URL = "https://api.data.gov.sg/v1/environment"
ENDPOINTS = {
    "temperature": "air-temperature",
    "rainfall": "rainfall",
    "humidity": "relative-humidity",
    "pm25": "pm25"
}

# --- Region Mapping for PM2.5 ---
# Coordinates (approx centroids) for Singapore regions
REGION_CENTROIDS = {
    "north": {"lat": 1.41803, "lon": 103.8200},
    "south": {"lat": 1.29587, "lon": 103.8200},
    "east":  {"lat": 1.35735, "lon": 103.9400},
    "west":  {"lat": 1.35735, "lon": 103.7000},
    "central": {"lat": 1.35735, "lon": 103.8200}
}

def get_region_from_latlon(lat, lon):
    """Find the nearest region key for a given lat/lon."""
    min_dist = float('inf')
    best_region = "central" # default
    
    for region, coords in REGION_CENTROIDS.items():
        # Simple Euclidean distance is sufficient for small area
        d = ((lat - coords['lat'])**2 + (lon - coords['lon'])**2)**0.5
        if d < min_dist:
            min_dist = d
            best_region = region
    return best_region

def fetch_data(date_str, type_key):
    """Fetch one day of data for a specific type (e.g., rainfall)."""
    url = f"{BASE_URL}/{ENDPOINTS[type_key]}"
    params = {"date": date_str}
    
    print(f"  Fetching {type_key} for {date_str}...")
    try:
        # Use custom cert path if it exists, otherwise default to True (Standard Trust Store)
        # Verify argument can trigger error if path is invalid, so ensure path is correct.
        # FIX: Expand shell variables like ${HOME} or ~
        resolved_cert_path = os.path.expandvars(os.path.expanduser(CUSTOM_CERT_PATH))
        
        verify_arg = resolved_cert_path if os.path.exists(resolved_cert_path) else True
        
        if verify_arg is True and resolved_cert_path != "/path/to/your/custom_root_ca.pem":
             # Only warn if it's not the placeholder
             if "combined-bundle.pem" in CUSTOM_CERT_PATH: # Specific check for user current case
                 print(f"    Warning: Custom cert path '{resolved_cert_path}' not found. Using default SSL.")

        resp = requests.get(url, params=params, timeout=10, verify=verify_arg)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"    Error: {e}")
        return None

def process_day(date_obj):
    date_str = date_obj.strftime("%Y-%m-%d")
    print(f"Processing {date_str}...")
    
    # 1. Fetch metadata first (to build station map)
    # We use temperature call to get station metadata
    print("    Fetching metadata from temperature endpoint...")
    temp_data = fetch_data(date_str, "temperature")
    
    station_region_map = {} # station_id -> region_key
    
    if temp_data and 'metadata' in temp_data and 'stations' in temp_data['metadata']:
        for s in temp_data['metadata']['stations']:
            if 'location' in s and 'latitude' in s['location']:
                lat = s['location']['latitude']
                lon = s['location']['longitude']
                sid = s['id']
                station_region_map[sid] = get_region_from_latlon(lat, lon)
    
    # 2. Fetch all types
    data_raw = {}
    data_raw['temperature'] = temp_data # Reuse
    
    for key in ENDPOINTS:
        if key == 'temperature': continue
        data_raw[key] = fetch_data(date_str, key)
        time.sleep(0.5)

    # 2. Flatten Data
    # structure: { metadata: {stations...}, items: [{timestamp, readings: [{station_id, value}]}] }
    
    records = []
    
    # We drive by Timestamp from one metric (e.g. Temperature) and try to match others
    # Or better: Flatten everything into (Timestamp, StationID, Type, Value) then pivot.
    
    for dtype, json_data in data_raw.items():
        if not json_data or 'items' not in json_data:
            continue
            
        if dtype == 'pm25':
            # Structure: items -> [{timestamp, readings: {pm25_one_hourly: {west: X, ...}}}]
            # Iterate through time steps
            for item in json_data['items']:
                timestamp = item['timestamp']
                if 'readings' not in item or 'pm25_one_hourly' not in item['readings']:
                    continue
                    
                regional_readings = item['readings']['pm25_one_hourly']
                
                # For every known station, assign the value of its region
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
            # Standard Structure: items -> [{timestamp, readings: [{station_id: ..., value: ...}]}]
            for item in json_data['items']:
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

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    
    # 3. Pivot to wide format: [timestamp, sensor_id] -> [temperature, rainfall, humidity]
    # Timestamp might slightly differ (seconds), so needs careful merge or rough rounding.
    # Data.gov.sg timestamps are usually consistent per minute.
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Pivot
    df_pivot = df.pivot_table(
        index=['timestamp', 'sensor_id'], 
        columns='type', 
        values='value'
    ).reset_index()
    
    return df_pivot

def main():
    # Collect all unique dates to process
    dates_to_process = set()
    
    for item in FETCH_CONFIG:
        if isinstance(item, datetime.date):
            dates_to_process.add(item)
        elif isinstance(item, dict) and 'start' in item and 'end' in item:
            current = item['start']
            end = item['end']
            while current <= end:
                dates_to_process.add(current)
                current += datetime.timedelta(days=1)
        else:
            print(f"Warning: Invalid config item: {item}")

    sorted_dates = sorted(list(dates_to_process))
    
    if not sorted_dates:
        print("No dates configured to fetch.")
        return

    print(f"Scheduled to fetch {len(sorted_dates)} days: {sorted_dates[0]} ~ {sorted_dates[-1]}")

    # 逐批处理（每 30 天写一次 CSV），避免大规模数据内存溢出
    BATCH_SIZE = 30
    total_rows = 0
    header_written = os.path.exists(OUTPUT_FILE)

    for i in range(0, len(sorted_dates), BATCH_SIZE):
        batch = sorted_dates[i:i + BATCH_SIZE]
        print(f"\n--- Batch {i // BATCH_SIZE + 1}: {batch[0]} ~ {batch[-1]} ({len(batch)} days) ---")
        
        batch_dfs = []
        for current_date in batch:
            df_day = process_day(current_date)
            if not df_day.empty:
                batch_dfs.append(df_day)

        if not batch_dfs:
            continue

        batch_df = pd.concat(batch_dfs, ignore_index=True)
        batch_df = batch_df.sort_values(['sensor_id', 'timestamp'])

        required = ['temperature', 'rainfall', 'humidity', 'pm25']
        for col in required:
            if col not in batch_df.columns:
                batch_df[col] = 0.0

        batch_df = batch_df.ffill().fillna(0.0)

        # 追加写入 CSV
        batch_df.to_csv(OUTPUT_FILE, mode="a", header=not header_written, index=False)
        header_written = True
        total_rows += len(batch_df)
        print(f"  ✅ Batch written: {len(batch_df)} rows (total: {total_rows})")
        
        # 释放内存
        del batch_dfs, batch_df

    print(f"\nDone! Total {total_rows} rows saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
