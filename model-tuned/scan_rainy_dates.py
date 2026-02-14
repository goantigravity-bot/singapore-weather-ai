"""
Step 1: 扫描 S3 已有的 93 天传感器数据，找出哪些天下了雨。
输出 data/rainy_dates.json 供后续步骤使用。
"""
import boto3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

S3_BUCKET = "weather-ai-models-de08370c"
S3_REGION = "ap-southeast-1"
# 日总降雨量阈值(mm)：超过此值才视为"有效下雨日"
RAIN_THRESHOLD_MM = 5.0

OUTPUT_DIR = Path(__file__).parent / "data"


def list_available_dates(s3):
    """从 S3 gobdata/ 列出所有可用的 rainfall JSON 日期。"""
    paginator = s3.get_paginator('list_objects_v2')
    dates = []

    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix='govdata/rainfall_'):
        for obj in page.get('Contents', []):
            # govdata/rainfall_2025-10-01.json
            key = obj['Key']
            try:
                date_str = key.split('rainfall_')[1].replace('.json', '')
                dates.append(date_str)
            except (IndexError, ValueError):
                continue

    return sorted(dates)


def analyze_rainfall_for_date(s3, date_str):
    """下载单日 rainfall JSON，计算降雨统计。"""
    key = f"govdata/rainfall_{date_str}.json"
    try:
        resp = s3.get_object(Bucket=S3_BUCKET, Key=key)
        data = json.loads(resp['Body'].read())
    except Exception as e:
        logger.warning(f"  {date_str}: Failed to read rainfall data: {e}")
        return None

    total_rainfall = 0.0
    max_rainfall = 0.0
    rain_stations = set()
    total_readings = 0

    for item in data.get('items', []):
        for reading in item.get('readings', []):
            val = reading.get('value', 0)
            if val is None:
                continue
            total_readings += 1
            total_rainfall += val
            if val > max_rainfall:
                max_rainfall = val
            if val > 0:
                rain_stations.add(reading.get('station_id', ''))

    return {
        'date': date_str,
        'total_rainfall_mm': round(total_rainfall, 2),
        'max_rainfall_mm': round(max_rainfall, 2),
        'rain_station_count': len(rain_stations),
        'total_readings': total_readings,
    }


def check_satellite_available(s3, date_str):
    """检查该日期是否有预处理好的卫星 .npy 数据。"""
    date_compact = date_str.replace('-', '')
    prefix = f"processed/satellite/{date_compact}/"
    resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix, MaxKeys=1)
    npy_count = resp.get('KeyCount', 0)

    if npy_count == 0:
        # 尝试查找原始 satellite 数据
        raw_prefix = f"satellite/{date_compact}/"
        resp2 = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=raw_prefix, MaxKeys=1)
        raw_count = resp2.get('KeyCount', 0)
        return {'has_processed': False, 'has_raw': raw_count > 0}

    return {'has_processed': True, 'has_raw': True}


def main():
    s3 = boto3.client('s3', region_name=S3_REGION)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 列出所有可用日期
    logger.info("Scanning S3 for available rainfall data...")
    dates = list_available_dates(s3)
    logger.info(f"Found {len(dates)} dates with rainfall data")

    # 2. 逐日分析降雨
    all_days = []
    rainy_days = []

    for i, date_str in enumerate(dates):
        stats = analyze_rainfall_for_date(s3, date_str)
        if stats is None:
            continue

        sat_info = check_satellite_available(s3, date_str)
        stats['has_satellite_processed'] = sat_info['has_processed']
        stats['has_satellite_raw'] = sat_info['has_raw']

        is_rainy = stats['total_rainfall_mm'] > RAIN_THRESHOLD_MM
        stats['is_rainy'] = is_rainy

        all_days.append(stats)
        if is_rainy and sat_info['has_raw']:
            rainy_days.append(stats)

        marker = "🌧️" if is_rainy else "  "
        sat_marker = "📡" if sat_info['has_raw'] else "  "
        logger.info(
            f"  [{i+1}/{len(dates)}] {date_str}: "
            f"{stats['total_rainfall_mm']:>8.1f}mm "
            f"max={stats['max_rainfall_mm']:.1f}mm "
            f"stations={stats['rain_station_count']:>2} "
            f"{marker} {sat_marker}"
        )

    # 3. 汇总
    logger.info(f"\n{'='*60}")
    logger.info(f"SUMMARY")
    logger.info(f"  Total dates scanned: {len(all_days)}")
    logger.info(f"  Rainy days (>{RAIN_THRESHOLD_MM}mm): {len([d for d in all_days if d['is_rainy']])}")
    logger.info(f"  Rainy days with satellite data: {len(rainy_days)}")
    logger.info(f"{'='*60}")

    if rainy_days:
        logger.info("\nRainy days with satellite data:")
        for d in rainy_days:
            logger.info(f"  {d['date']}: {d['total_rainfall_mm']:.1f}mm (max {d['max_rainfall_mm']:.1f}mm)")

    # 4. 保存结果
    output_file = OUTPUT_DIR / "rainy_dates.json"
    result = {
        'scan_time': datetime.now().isoformat(),
        'threshold_mm': RAIN_THRESHOLD_MM,
        'total_dates': len(all_days),
        'rainy_dates_count': len(rainy_days),
        'all_days': all_days,
        'rainy_days': rainy_days,
    }

    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)

    logger.info(f"\nSaved to {output_file}")


if __name__ == "__main__":
    main()
