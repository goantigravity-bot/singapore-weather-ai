"""
Step 1: 扫描 S3 NEA 数据，找出每天哪些 10-min 时段有雨 (> 0.10mm)。
输出 data/rainy_timestamps.json，供 process_and_train_daily.py 使用。

只处理【缺少 processed .npy 但有 raw .nc】的日期。
"""
import boto3
import json
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

S3_BUCKET = "weather-ai-models-de08370c"
# 每 5-min slot 内任何站点读数 > 此阈值即视为"有雨"
RAIN_THRESHOLD = 0.10
OUTPUT_DIR = Path(__file__).parent / "data"


def list_rainfall_dates(s3):
    """列出 S3 上所有 rainfall JSON 日期。"""
    paginator = s3.get_paginator('list_objects_v2')
    dates = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix='govdata/rainfall_'):
        for obj in page.get('Contents', []):
            key = obj['Key']
            try:
                date_str = key.split('rainfall_')[1].replace('.json', '')
                dates.append(date_str)
            except (IndexError, ValueError):
                continue
    return sorted(dates)


def check_satellite_status(s3, date_str):
    """检查日期的卫星数据状态：已处理/有原始/都没有。"""
    date_compact = date_str.replace('-', '')
    # processed
    resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=f'processed/satellite/{date_compact}/', MaxKeys=1)
    has_processed = resp.get('KeyCount', 0) > 0
    # raw
    resp2 = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=f'satellite/{date_compact}/', MaxKeys=1)
    has_raw = resp2.get('KeyCount', 0) > 0
    return has_processed, has_raw


def extract_rainy_slots(s3, date_str):
    """提取单日中降雨 > 0.10mm 的时段，对齐到 10-min 卫星时间 (HHMM)。"""
    key = f"govdata/rainfall_{date_str}.json"
    try:
        resp = s3.get_object(Bucket=S3_BUCKET, Key=key)
        data = json.loads(resp['Body'].read())
    except Exception as e:
        logger.warning(f"  {date_str}: Failed to read: {e}")
        return [], 0.0

    rainy_slots = set()
    total_rainfall = 0.0

    for item in data.get('items', []):
        ts_str = item.get('timestamp', '')
        has_rain = False
        for reading in item.get('readings', []):
            val = reading.get('value', 0) or 0
            total_rainfall += val
            if val > RAIN_THRESHOLD:
                has_rain = True

        if has_rain and ts_str:
            try:
                # NEA 时间戳: 2025-10-04T01:00:00+08:00
                dt = datetime.fromisoformat(ts_str)
                # 对齐到 10-min 区间（卫星数据以 10min 为间隔）
                aligned_min = (dt.minute // 10) * 10
                slot = f"{dt.hour:02d}{aligned_min:02d}"
                rainy_slots.add(slot)
            except ValueError:
                continue

    return sorted(rainy_slots), round(total_rainfall, 2)


def main():
    s3 = boto3.client('s3', region_name='ap-southeast-1')
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Scanning S3 for rainfall data...")
    dates = list_rainfall_dates(s3)
    logger.info(f"Found {len(dates)} dates")

    results = []
    total_need_process = 0

    for i, date_str in enumerate(dates):
        has_processed, has_raw = check_satellite_status(s3, date_str)

        # 只关注：未处理 + 有 raw .nc 的日期
        if has_processed or not has_raw:
            status = "✅ already processed" if has_processed else "⚠️ no raw satellite"
            logger.info(f"  [{i+1}/{len(dates)}] {date_str}: {status} — SKIP")
            continue

        rainy_slots, total_mm = extract_rainy_slots(s3, date_str)

        if not rainy_slots:
            logger.info(f"  [{i+1}/{len(dates)}] {date_str}: {total_mm:.1f}mm total but no slot > {RAIN_THRESHOLD}mm — SKIP")
            continue

        results.append({
            'date': date_str,
            'date_compact': date_str.replace('-', ''),
            'total_rainfall_mm': total_mm,
            'rainy_slots': rainy_slots,
            'rainy_slot_count': len(rainy_slots),
        })

        total_need_process += 1
        logger.info(
            f"  [{i+1}/{len(dates)}] {date_str}: "
            f"{total_mm:>8.1f}mm, {len(rainy_slots)} rainy slots 🌧️"
        )

    # 汇总
    logger.info(f"\n{'='*60}")
    logger.info(f"SUMMARY")
    logger.info(f"  Dates needing processing: {total_need_process}")
    total_slots = sum(r['rainy_slot_count'] for r in results)
    logger.info(f"  Total rainy slots: {total_slots}")
    # 估算下载量：每个 .nc ~680MB
    est_gb = total_slots * 0.68
    logger.info(f"  Estimated download: ~{est_gb:.0f}GB raw .nc")
    logger.info(f"{'='*60}")

    # 保存
    output_file = OUTPUT_DIR / "rainy_timestamps.json"
    output = {
        'scan_time': datetime.now().isoformat(),
        'rain_threshold': RAIN_THRESHOLD,
        'dates_to_process': len(results),
        'total_rainy_slots': total_slots,
        'days': results,
    }
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    logger.info(f"\nSaved to {output_file}")


if __name__ == "__main__":
    main()
