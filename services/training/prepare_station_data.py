"""
prepare_station_data.py — 为指定基站提取雨/干样本并配对卫星 patch

用法:
  python3 prepare_station_data.py --station S66
  python3 prepare_station_data.py --station S66 --rain-threshold 5.0 --dry-ratio 3

输出:
  station_data/S66/rain_samples.npz
  station_data/S66/dry_samples.npz
"""

import argparse
import csv
import json
import logging
import math
import os
import random
import subprocess
import sys
import time
from datetime import datetime

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(SCRIPT_DIR, "real_sensor_data.csv")
SAT_DIR = os.path.join(SCRIPT_DIR, "processed_data")           # 旧单通道（兼容）
SAT_3CH_DIR = os.path.join(SCRIPT_DIR, "processed_data_3ch")   # 新 3 通道
COORDS_FILE = os.path.join(SCRIPT_DIR, "station_coords.json")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "station_data")

BANDS = ["B08", "B11", "B13"]  # 水汽 / 云相态 / 红外
PATCH_SIZE = 32
IMG_SIZE = 128
LOOKBACK_STEPS = 6   # LSTM 输入序列长度：当前 + 过去 5 步 = 6
MAX_GAP_SECONDS = 600  # 回溯时允许的最大间隔（10 分钟），超过则视为不连续

# 新加坡裁剪范围（和 weather_dataset.py 一致）
SG_LAT_MIN, SG_LAT_MAX = 1.15, 1.50
SG_LON_MIN, SG_LON_MAX = 103.6, 104.1

# 传感器特征列（和 weather_dataset.py 一致: 7 features）
SENSOR_COLS = ["temperature", "humidity", "rainfall", "pm25", "wind_speed", "wind_dir_sin", "wind_dir_cos"]


def _parse_sensor_vals(row):
    """从 CSV 行提取传感器特征向量"""
    vals = []
    for col in SENSOR_COLS:
        try:
            vals.append(float(row.get(col, 0)))
        except (ValueError, TypeError):
            vals.append(0.0)
    return vals


def _parse_timestamp(ts_str):
    """解析 CSV 时间戳为 datetime 对象（忽略时区，按本地时间处理）"""
    return datetime.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S")


def latlon_to_pixel(lat, lon):
    """基站经纬度 → 128×128 图的像素坐标 (px, py)"""
    py = int((SG_LAT_MAX - lat) / (SG_LAT_MAX - SG_LAT_MIN) * IMG_SIZE)
    px = int((lon - SG_LON_MIN) / (SG_LON_MAX - SG_LON_MIN) * IMG_SIZE)
    return px, py


def crop_patch(img, px, py):
    """从 128×128 图中裁剪以 (px, py) 为中心的 32×32 patch"""
    half = PATCH_SIZE // 2
    y1 = max(0, py - half)
    y2 = min(IMG_SIZE, py + half)
    x1 = max(0, px - half)
    x2 = min(IMG_SIZE, px + half)

    patch = np.zeros((PATCH_SIZE, PATCH_SIZE), dtype=np.float32)
    # 填充可能因边界裁剪不足 32 的部分
    dy = half - (py - y1)
    dx = half - (px - x1)
    patch[dy:dy + (y2 - y1), dx:dx + (x2 - x1)] = img[y1:y2, x1:x2]
    return patch


def timestamp_to_npy_path(ts_str):
    """将 CSV timestamp 转为旧版单通道 .npy 文件路径（兼容）"""
    clean = ts_str[:19].replace("-", "").replace("T", "_").replace(":", "")
    date_part = clean[:8]
    time_part = clean[9:13]
    filename = f"SAT_128_{date_part}_{time_part}.npy"
    return os.path.join(SAT_DIR, filename)


def timestamp_to_3ch_paths(ts_str):
    """将 CSV timestamp (SGT) 转为 3 通道 .npy 路径列表

    关键：传感器 CSV 是 SGT (UTC+8)，卫星文件名是 UTC，需减 8 小时。
    例: '2025-03-15T14:20:00+08:00' → UTC 06:20 → SAT_B08_20250315_0620.npy
    """
    from datetime import timedelta
    sgt_time = datetime.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S")
    # SGT → UTC: 减 8 小时
    utc_time = sgt_time - timedelta(hours=8)
    date_part = utc_time.strftime("%Y%m%d")
    time_part = utc_time.strftime("%H%M")
    return [os.path.join(SAT_3CH_DIR, f"SAT_{band}_{date_part}_{time_part}.npy") for band in BANDS]


def fast_read_station_csv(station_id):
    """用 grep 预过滤 + csv 读取，秒级完成"""
    csv_size_mb = os.path.getsize(CSV_PATH) / (1024 * 1024)
    logger.info(f"Reading CSV for station {station_id} (grep pre-filter, {csv_size_mb:.1f}MB)...")
    t0 = time.time()

    # grep 预过滤：只保留包含 station_id 的行（极快）
    try:
        header = subprocess.run(
            ["head", "-1", CSV_PATH],
            capture_output=True, text=True, check=True
        ).stdout.strip()

        result = subprocess.run(
            ["grep", station_id, CSV_PATH],
            capture_output=True, text=True
        )
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
    except Exception as e:
        logger.error(f"grep failed: {e}")
        return []

    if not lines:
        logger.warning(f"No data found for {station_id}")
        return []

    # 解析 CSV 行
    fields = header.split(",")
    rows = []
    reader = csv.DictReader([header] + lines)
    for row in reader:
        if row.get("sensor_id") != station_id:
            continue
        try:
            rainfall = float(row.get("rainfall", "nan"))
        except ValueError:
            continue
        rows.append(row)

    elapsed = time.time() - t0
    logger.info(f"  Found {len(rows)} rows for {station_id} in {elapsed:.1f}s")
    return rows


def build_dataset(rows, station_coords, condition_fn, label="rain"):
    """将 CSV 行配对成 (satellite_patch, sensor_seq, coord, rainfall) 训练数据集

    2a 改进：sensor_seq 使用真实的过去 6 个时间步（回溯 30 分钟），
            让 LSTM 能学到 "湿度上升 → 即将降雨" 等时序趋势。
    2b 改进：coord 包含基站位置 + hour/month 周期编码（6 维），
            让模型区分下午雷阵雨 vs 凌晨假信号。
    """
    px, py = station_coords

    samples = {"sat": [], "sensor": [], "coord": [], "label": []}
    matched = 0
    skipped = 0
    total = len(rows)

    # 逐天统计：日期切换时汇报前一天结果
    current_date = None
    day_matched = 0
    day_skipped = 0

    for i, row in enumerate(rows):
        if not condition_fn(row):
            continue

        # 检测日期切换，输出前一天统计
        row_date = row["timestamp"][:10]  # 'YYYY-MM-DD'
        if current_date is not None and row_date != current_date:
            logger.info(
                f"  [{label}] {current_date}: +{day_matched} matched, {day_skipped} skipped "
                f"(running total: {matched}/{total})"
            )
            day_matched = 0
            day_skipped = 0
        current_date = row_date

        # 1. 找卫星文件（优先 3 通道，回退到单通道）
        ch3_paths = timestamp_to_3ch_paths(row["timestamp"])
        use_3ch = all(os.path.exists(p) for p in ch3_paths)

        if not use_3ch:
            # 回退到旧单通道
            npy_path = timestamp_to_npy_path(row["timestamp"])
            if not os.path.exists(npy_path):
                skipped += 1
                day_skipped += 1
                continue

        # 2. 加载卫星数据
        try:
            if use_3ch:
                # 3 通道全图：stack 为 (3, H, W)
                channels = [np.load(p).astype(np.float32) for p in ch3_paths]
                sat_img = np.stack(channels)  # (3, ~41, ~37)
            else:
                # 旧单通道：裁剪 patch
                img = np.load(npy_path)
                if img.ndim == 3:
                    img = img[0]
                patch = crop_patch(img, px, py)
                sat_img = patch[np.newaxis, :, :]  # (1, 32, 32)
        except Exception:
            skipped += 1
            day_skipped += 1
            continue

        # 3. 构建真实传感器时序（回溯 past 5 步 + 当前 = 6 步）
        current_vals = _parse_sensor_vals(row)
        current_ts = _parse_timestamp(row["timestamp"])
        seq_steps = [current_vals]

        # 从当前行向前回溯，收集连续的历史记录
        for step_back in range(1, LOOKBACK_STEPS):
            prev_idx = i - step_back
            if prev_idx < 0:
                break
            prev_row = rows[prev_idx]
            prev_ts = _parse_timestamp(prev_row["timestamp"])
            gap = (current_ts - prev_ts).total_seconds()
            # 间隔超过阈值则停止回溯（数据不连续）
            if gap > MAX_GAP_SECONDS * step_back:
                break
            seq_steps.append(_parse_sensor_vals(prev_row))

        # 不足 6 步时用最早一步 padding
        while len(seq_steps) < LOOKBACK_STEPS:
            seq_steps.append(seq_steps[-1])

        # seq_steps 是 [当前, t-1, t-2, ...] → 反转为时间正序 [最早, ..., 当前]
        seq_steps.reverse()
        sensor_seq = np.array(seq_steps, dtype=np.float32)

        # 4. 坐标 + 时间周期编码 (6 维)
        hour = current_ts.hour + current_ts.minute / 60.0
        month = current_ts.month
        coord = np.array([
            px / IMG_SIZE,                              # 归一化 x 位置
            py / IMG_SIZE,                              # 归一化 y 位置
            math.sin(2 * math.pi * hour / 24),          # 日内周期 sin
            math.cos(2 * math.pi * hour / 24),          # 日内周期 cos
            math.sin(2 * math.pi * month / 12),         # 季节周期 sin
            math.cos(2 * math.pi * month / 12),         # 季节周期 cos
        ], dtype=np.float32)

        # 5. 标签
        rainfall = float(row.get("rainfall", 0))

        samples["sat"].append(sat_img)                    # (3, H, W) 或 (1, 32, 32)
        samples["sensor"].append(sensor_seq)              # (6, 7)
        samples["coord"].append(coord)                    # (6,)
        samples["label"].append(rainfall)
        matched += 1
        day_matched += 1

    # 最后一天的统计
    if current_date is not None and (day_matched > 0 or day_skipped > 0):
        logger.info(
            f"  [{label}] {current_date}: +{day_matched} matched, {day_skipped} skipped "
            f"(running total: {matched}/{total})"
        )

    logger.info(f"  ✅ {label}: {matched} matched, {skipped} skipped (no .npy)")
    return {k: np.array(v) for k, v in samples.items()} if matched > 0 else None


def main():
    parser = argparse.ArgumentParser(description="Prepare station-specific training data")
    parser.add_argument("--station", required=True, help="Station ID (e.g. S66)")
    parser.add_argument("--rain-threshold", type=float, default=5.0, help="Rain threshold in mm")
    parser.add_argument("--dry-ratio", type=int, default=3, help="Dry:Rain sample ratio")
    args = parser.parse_args()

    # 加载基站坐标
    with open(COORDS_FILE) as f:
        all_coords = json.load(f)

    if args.station not in all_coords:
        logger.error(f"Station {args.station} not found in {COORDS_FILE}")
        sys.exit(1)

    c = all_coords[args.station]
    px, py = latlon_to_pixel(c["lat"], c["lon"])
    logger.info(f"Station {args.station}: lat={c['lat']}, lon={c['lon']} → pixel=({px}, {py})")

    # 读取 CSV（grep 预过滤）
    rows = fast_read_station_csv(args.station)
    if not rows:
        sys.exit(1)

    # 输出目录
    out_dir = os.path.join(OUTPUT_DIR, args.station)
    os.makedirs(out_dir, exist_ok=True)

    # 统计可用卫星数据
    npy_count = len([f for f in os.listdir(SAT_DIR) if f.endswith(".npy")]) if os.path.isdir(SAT_DIR) else 0
    logger.info(f"📡 Satellite data: {npy_count} .npy files in {SAT_DIR}")

    # --- 雨样本: rainfall >= threshold ---
    rain_condition = lambda row: float(row.get("rainfall", 0)) >= args.rain_threshold
    rain_data = build_dataset(rows, (px, py), rain_condition, label="rain")

    if rain_data is None:
        logger.error("No rain samples matched. Check satellite data availability.")
        sys.exit(1)

    n_rain = len(rain_data["label"])
    rain_path = os.path.join(out_dir, "rain_samples.npz")
    np.savez_compressed(rain_path, **rain_data)
    logger.info(f"💾 Saved rain: {rain_path} ({n_rain} samples)")

    # --- 干样本: rainfall == 0.0, 随机抽样 ---
    dry_rows = [r for r in rows if float(r.get("rainfall", -1)) == 0.0]
    n_dry_target = n_rain * args.dry_ratio
    if len(dry_rows) > n_dry_target:
        random.seed(42)
        dry_rows = random.sample(dry_rows, n_dry_target)

    dry_condition = lambda row: True  # 已经预过滤了
    dry_data = build_dataset(dry_rows, (px, py), dry_condition, label="dry")

    if dry_data is not None:
        dry_path = os.path.join(out_dir, "dry_samples.npz")
        np.savez_compressed(dry_path, **dry_data)
        logger.info(f"💾 Saved dry: {dry_path} ({len(dry_data['label'])} samples)")
    else:
        logger.warning("No dry samples matched.")

    logger.info(f"✅ Done: {args.station}")


if __name__ == "__main__":
    main()
