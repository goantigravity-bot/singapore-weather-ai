"""
从 S3 govdata 生成传感器 CSV — 逐天处理避免 OOM。

每天有 6 种 JSON 文件 (rainfall, humidity, temperature, pm25, wind-speed, wind-direction)，
按天合并为横向 CSV 行，追加到输出文件。支持断点恢复。

用法:
    python3 process_gov_data_from_s3.py --year 2020 --output processed/2020/sensor/real_sensor_data.csv
"""
import os
import json
import boto3
import csv
import argparse
import logging
from datetime import datetime, timedelta
from collections import defaultdict

S3_BUCKET = os.environ.get("S3_BUCKET", "weather-ai-models-gcc")
GOVDATA_PREFIX = "govdata"
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", None)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("process_gov_data")

# 6 种数据类型映射到 JSON 文件名前缀
DATA_TYPES = {
    'rainfall': 'rainfall',
    'temperature': 'temperature',
    'humidity': 'humidity',
    'pm25': 'pm25',
    'wind_speed': 'wind-speed',
    'wind_direction': 'wind-direction',
}

CSV_COLUMNS = ['timestamp', 'sensor_id', 'humidity', 'pm25', 'rainfall', 'temperature', 'wind_speed', 'wind_direction']

REGION_CENTROIDS = {
    "north": {"lat": 1.41803, "lon": 103.8200},
    "south": {"lat": 1.29587, "lon": 103.8200},
    "east":  {"lat": 1.35735, "lon": 103.9400},
    "west":  {"lat": 1.35735, "lon": 103.7000},
    "central": {"lat": 1.35735, "lon": 103.8200},
}


def get_s3_client():
    return boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)


def get_region_from_latlon(lat, lon):
    min_dist = float('inf')
    best = "central"
    for region, c in REGION_CENTROIDS.items():
        d = ((lat - c['lat'])**2 + (lon - c['lon'])**2)**0.5
        if d < min_dist:
            min_dist = d
            best = region
    return best


def build_station_region_map(s3, year):
    """从 temperature JSON 的 metadata 中提取 station → region 映射（用于 PM2.5）。"""
    key = f"{GOVDATA_PREFIX}/{year}/temperature_{year}-01-01.json"
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
        data = json.loads(obj['Body'].read().decode('utf-8'))
        mapping = {}
        if 'metadata' in data and 'stations' in data['metadata']:
            for s in data['metadata']['stations']:
                if 'location' in s and 'latitude' in s['location']:
                    sid = s['id']
                    mapping[sid] = get_region_from_latlon(
                        s['location']['latitude'], s['location']['longitude']
                    )
        return mapping
    except Exception as e:
        logger.warning(f"Failed to build station map: {e}")
        return {}


def parse_json_file(s3, key, dtype, station_region_map):
    """解析单个 JSON 文件，返回 {(timestamp, sensor_id): value} 字典。

    支持两种 NEA API 格式:
      格式 A (rainfall / temperature / humidity): 顶层含 "items" 列表
      格式 B (wind-speed / wind-direction):       顶层含 "data" 字典,
                readings 在 data.readings 内, 站点 key 为 stationId
    """
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
        data = json.loads(obj['Body'].read().decode('utf-8'))
    except Exception as e:
        logger.warning(f"Error reading {key}: {e}")
        return {}

    if not data:
        return {}

    result = {}

    # --- PM2.5: 区域级数据，映射到各站点 ---
    if dtype == 'pm25':
        if 'items' not in data:
            return {}
        for item in data['items']:
            ts = item['timestamp']
            readings = item.get('readings', {})
            pm25_data = readings.get('pm25_one_hourly', {})
            for sid, region_key in station_region_map.items():
                if region_key in pm25_data:
                    result[(ts, sid)] = pm25_data[region_key]
        return result

    # --- 格式 B: wind-speed / wind-direction ---
    # { "code": 0, "data": { "readings": [{"timestamp": "...", "data": [{"stationId": "Sxx", "value": N}]}] } }
    if 'data' in data and 'items' not in data:
        data_section = data.get('data', {})
        if isinstance(data_section, dict):
            for reading_block in data_section.get('readings', []):
                ts = reading_block.get('timestamp', '')
                for r in reading_block.get('data', []):
                    sid = r.get('stationId')
                    val = r.get('value')
                    if sid and val is not None:
                        result[(ts, sid)] = val
        return result

    # --- 格式 A: rainfall / temperature / humidity ---
    if 'items' not in data:
        return {}
    for item in data['items']:
        ts = item['timestamp']
        for r in item.get('readings', []):
            val = r.get('value')
            if val is not None:
                result[(ts, r['station_id'])] = val

    return result


def process_day(s3, year, date_str, station_region_map):
    """处理一天的 6 种 JSON，合并为横向 CSV 行，并做 10 分钟重采样。"""
    # 获取 6 种数据
    type_data = {}
    for col_name, file_prefix in DATA_TYPES.items():
        key = f"{GOVDATA_PREFIX}/{year}/{file_prefix}_{date_str}.json"
        type_data[col_name] = parse_json_file(s3, key, col_name, station_region_map)

    # 收集所有 (timestamp, sensor_id) 组合
    all_keys = set()
    for d in type_data.values():
        all_keys.update(d.keys())

    if not all_keys:
        return []

    # 合并为横向行
    rows = []
    for ts, sid in sorted(all_keys):
        row = {
            'timestamp': ts,
            'sensor_id': sid,
        }
        for col_name in DATA_TYPES:
            val = type_data[col_name].get((ts, sid))
            # Use NaN for missing values so resampling mean ignores them.
            # Only rainfall defaults to 0 (no rain = 0 is semantically correct).
            row[col_name] = val if val is not None else (0.0 if col_name == 'rainfall' else float('nan'))
        rows.append(row)

    # 10 分钟重采样：减少数据量 ~75%，避免训练时重复计算
    import pandas as pd
    df = pd.DataFrame(rows)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    # 按 station 分组，10 分钟聚合（rainfall 求和，其余取均值）
    df['ts_bucket'] = df['timestamp'].dt.floor('10min')
    agg_dict = {col: ('sum' if col == 'rainfall' else 'mean')
                for col in DATA_TYPES}
    resampled = df.groupby(['ts_bucket', 'sensor_id']).agg(agg_dict).reset_index()
    resampled.rename(columns={'ts_bucket': 'timestamp'}, inplace=True)
    # 转回 ISO 格式字符串
    resampled['timestamp'] = resampled['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S')
    # rainfall NaN → 0; other metrics keep NaN (→ empty string in CSV → NULL in Snowflake)
    resampled['rainfall'] = resampled['rainfall'].fillna(0.0)

    return resampled.to_dict('records')


def get_processed_days(csv_path):
    """从已有 CSV 中读取已处理的日期集合（用于断点恢复）。"""
    processed = set()
    if not os.path.exists(csv_path):
        return processed
    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                day = row['timestamp'][:10]
                processed.add(day)
    except Exception:
        pass
    return processed


def list_available_days(s3, year):
    """列出 S3 上该年份有哪些天的 govdata。"""
    prefix = f"{GOVDATA_PREFIX}/{year}/"
    days = set()
    paginator = s3.get_paginator('list_objects_v2')
    try:
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
            for obj in page.get('Contents', []):
                key = obj['Key']
                if key.endswith('.json'):
                    # humidity_2020-01-01.json → 2020-01-01
                    fname = key.split('/')[-1]
                    parts = fname.rsplit('_', 1)
                    if len(parts) == 2:
                        date_part = parts[1].replace('.json', '')
                        if len(date_part) == 10:  # YYYY-MM-DD
                            days.add(date_part)
    except Exception as e:
        logger.warning(f"Error listing days: {e}")
    return sorted(days)


def main():
    parser = argparse.ArgumentParser(description="Generate sensor CSV from S3 govdata (day-by-day)")
    parser.add_argument("--year", required=True, help="Year to process (e.g., 2020)")
    parser.add_argument("--output", default=None, help="Output CSV path")
    parser.add_argument("--reset", action="store_true", help="Start fresh (ignore existing CSV)")
    args = parser.parse_args()

    year = args.year
    output_path = args.output or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "real_sensor_data.csv"
    )

    s3 = get_s3_client()

    # 断点恢复：检查已处理的天
    if args.reset and os.path.exists(output_path):
        os.remove(output_path)

    processed_days = get_processed_days(output_path)
    if processed_days:
        logger.info(f"断点恢复: 已处理 {len(processed_days)} 天，从断点继续")

    # 列出该年所有可用的天
    available_days = list_available_days(s3, year)
    remaining = [d for d in available_days if d not in processed_days]
    logger.info(f"Year {year}: {len(available_days)} days available, {len(remaining)} to process")

    if not remaining:
        logger.info("No days to process. Done.")
        return

    # station region map 用于 PM2.5 数据解析
    station_region_map = build_station_region_map(s3, year)

    # 写 CSV header（如果是新文件）
    write_header = not os.path.exists(output_path)
    with open(output_path, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if write_header:
            writer.writeheader()

        for i, date_str in enumerate(remaining):
            rows = process_day(s3, year, date_str, station_region_map)
            # Convert NaN to empty string for NULL semantics in CSV
            clean_rows = [
                {k: ("" if isinstance(v, float) and v != v else
                     round(v, 2) if isinstance(v, float) else v)
                 for k, v in row.items()}
                for row in rows
            ]
            writer.writerows(clean_rows)
            f.flush()  # 每天写完 flush，确保中断时数据不丢

            if (i + 1) % 30 == 0 or (i + 1) == len(remaining):
                logger.info(f"  Progress: {i+1}/{len(remaining)} days, last: {date_str}")

    total_rows = sum(1 for _ in open(output_path)) - 1  # 减去 header
    logger.info(f"✅ Done: {output_path} ({total_rows} rows)")


if __name__ == "__main__":
    main()
