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
    # 1. Single date: 1 Jan 2026
    datetime.date(2026, 1, 1),
    
    # 2. First Date range: 13 Jan to 16 Jan
    {'start': datetime.date(2026, 1, 14), 'end': datetime.date(2026, 1, 15)},

    # 3. First Date range: 18 Jan to 21 Jan
    {'start': datetime.date(2026, 1, 17), 'end': datetime.date(2026, 1, 20)},

    # 4. You can add more ranges! Example:
    # {'start': datetime.date(2026, 2, 1), 'end': datetime.date(2026, 2, 5)},
]

OUTPUT_FILE = "real_sensor_data.csv"
# TODO: Replace with your actual .pem or .crt file path
# CUSTOM_CERT_PATH = "/path/to/your/custom_root_ca.pem"
CUSTOM_CERT_PATH = "${HOME}/.config/cloudflare/combined-bundle.pem"

# API Endpoints
BASE_URL = "https://api.data.gov.sg/v1/environment"
ENDPOINTS = {
    "temperature": "air-temperature",
    "rainfall": "rainfall",
    "humidity": "relative-humidity"
}

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
    
    # 1. Fetch all 3 types
    data_raw = {}
    for key in ENDPOINTS:
        data_raw[key] = fetch_data(date_str, key)
        time.sleep(0.5) # Be nice to API

    # 2. Flatten Data
    # structure: { metadata: {stations...}, items: [{timestamp, readings: [{station_id, value}]}] }
    
    records = []
    
    # We drive by Timestamp from one metric (e.g. Temperature) and try to match others
    # Or better: Flatten everything into (Timestamp, StationID, Type, Value) then pivot.
    
    for dtype, json_data in data_raw.items():
        if not json_data or 'items' not in json_data:
            continue
            
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
    all_dfs = []
    
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

    # Sort dates to process in order
    sorted_dates = sorted(list(dates_to_process))
    
    if not sorted_dates:
        print("No dates configured to fetch.")
        return

    print(f"Scheduled to fetch {len(sorted_dates)} days: {[d.isoformat() for d in sorted_dates]}")

    for current_date in sorted_dates:
        df_day = process_day(current_date)
        if not df_day.empty:
            all_dfs.append(df_day)
        
    if not all_dfs:
        print("No data fetched.")
        return

    print("Merging all days...")
    final_df = pd.concat(all_dfs, ignore_index=True)
    
    # Clean up
    final_df = final_df.sort_values(['sensor_id', 'timestamp'])
    
    # Rename type columns to match our Dataset (if needed)
    # Our code expects: temperature, rainfall, humidity
    # Check if columns exist
    required = ['temperature', 'rainfall', 'humidity']
    for col in required:
        if col not in final_df.columns:
            print(f"Warning: Column '{col}' missing (maybe no data returned). Filling 0.")
            final_df[col] = 0.0

    # Fill NaNs
    final_df = final_df.ffill().fillna(0.0)

    print(f"Saving {len(final_df)} rows to {OUTPUT_FILE}...")
    final_df.to_csv(OUTPUT_FILE, index=False)
    print("Done! You can now use this file in train.py")
    print(f"Example:\n{final_df.head()}")

if __name__ == "__main__":
    main()
