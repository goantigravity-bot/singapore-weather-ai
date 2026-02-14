"""
V3 Pipeline: 逐日处理卫星数据 + 逐日训练

流程（对 rainy_timestamps.json 中每天循环）：
1. 从 S3 下载该日 raw .nc（只下载雨时段）
2. 裁剪 SG 区域 → .npy
3. 上传 .npy 到 S3 processed/satellite/YYYYMMDD/
4. 保留 .npy 在本地（供训练用）
5. 删除本地 .nc 释放空间
6. 用累积数据训练模型（增量 fine-tune）

用法:
  python3 model-tuned/process_and_train_daily.py                # 全部日期
  python3 model-tuned/process_and_train_daily.py --process-only  # 只处理卫星，不训练
  python3 model-tuned/process_and_train_daily.py --start 2025-10-15  # 从指定日期开始
"""
import os
import sys
import json
import logging
import argparse
import tempfile
import time
import numpy as np
import xarray as xr
import torch
import torch.nn.functional as F
import boto3
from pathlib import Path
from datetime import datetime

# 将项目根目录加入 path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ── 配置 ──
S3_BUCKET = "weather-ai-models-de08370c"
S3_REGION = "ap-southeast-1"

DATA_DIR = Path(__file__).parent / "data"
SATELLITE_DIR = DATA_DIR / "satellite"   # processed .npy 保留在本地
RAW_DIR = Path(__file__).parent / "raw-data"  # 临时存放 S3 下载的 raw .nc
TIMESTAMPS_FILE = DATA_DIR / "rainy_timestamps.json"
STATE_FILE = DATA_DIR / "daily_process_state.json"

# 卫星裁剪参数（与 preprocess_images.py 一致）
TARGET_SIZE = (64, 64)

# 需要从 weather_dataset.py 导入
from weather_dataset import latlon2xy
SG_LAT_MAX, SG_LON_MIN = 1.50, 103.6
C1, L1 = latlon2xy(SG_LAT_MAX, SG_LON_MIN)
SG_LAT_MIN, SG_LON_MAX = 1.15, 104.1
C2, L2 = latlon2xy(SG_LAT_MIN, SG_LON_MAX)

# 训练参数
EPOCHS_PER_DAY = 50
BATCH_SIZE = 32
LEARNING_RATE = 1e-3
RAIN_WEIGHT = 3.0
SEQUENCE_LENGTH = 6


def load_state():
    """加载处理进度状态。"""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_processed_date": None, "days_completed": 0}


def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def process_nc_to_npy(nc_path):
    """将单个 .nc 文件裁剪为 SG 区域 64x64 .npy（和 preprocess_images.py 一致）。"""
    try:
        ds = xr.open_dataset(nc_path, decode_timedelta=False)

        var_name = 'tbb'
        if 'tbb_13' in ds:
            var_name = 'tbb_13'

        if var_name not in ds:
            ds.close()
            return None

        # Full Disk → 裁剪新加坡区域
        if ds[var_name].shape[0] > 1000:
            r_min, r_max = min(L1, L2), max(L1, L2)
            c_min, c_max = min(C1, C2), max(C1, C2)
            data = ds[var_name][r_min:r_max, c_min:c_max].values
        else:
            data = ds[var_name].values

        # 缩放到 64x64
        tensor = torch.tensor(data, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
        resized = F.interpolate(tensor, size=TARGET_SIZE, mode='bilinear', align_corners=False)
        final_arr = resized.squeeze().numpy()

        ds.close()
        return final_arr
    except Exception as e:
        logger.error(f"Error processing {nc_path}: {e}")
        return None


def process_single_day(s3, day_info):
    """处理单日：下载 raw .nc → 裁剪 → 上传 .npy → 清理 .nc。"""
    date_compact = day_info['date_compact']
    date_str = day_info['date']
    rainy_slots = day_info['rainy_slots']

    day_start = time.time()
    processed_count = 0
    skipped_count = 0

    for slot in rainy_slots:
        # S3 raw .nc: NC_H08_YYYYMMDD_HHMM_*.nc (Himawari-8) 或 NC_H09_* (Himawari-9)
        # 要兼容两种命名
        slot_prefix = f"{date_compact}_{slot}"

        # 先检查 S3 是否已有 processed（通用前缀匹配）
        proc_prefix = f"processed/satellite/{date_compact}/"
        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=proc_prefix)
        existing_npys = [o['Key'] for o in resp.get('Contents', []) if slot_prefix in o['Key']]
        if existing_npys:
            skipped_count += 1
            continue

        # 列出该时间点的 raw .nc（兼容 H08/H09）
        raw_prefix = f"satellite/{date_compact}/"
        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=raw_prefix)
        nc_keys = [
            obj['Key'] for obj in resp.get('Contents', [])
            if obj['Key'].endswith('.nc') and slot_prefix in obj['Key']
        ]

        if not nc_keys:
            continue

        # 下载、处理、上传（逐文件，处理完立即删除 .nc）
        for nc_key in nc_keys:
            nc_fname = nc_key.split('/')[-1]
            npy_fname = nc_fname.replace('.nc', '.npy')

            # 本地已有 .npy？跳过
            local_npy = SATELLITE_DIR / npy_fname
            if local_npy.exists():
                _upload_npy(s3, local_npy, npy_fname, date_compact)
                skipped_count += 1
                continue

            # 下载 .nc 到 raw-data 目录（处理完删除）
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            tmp_path = str(RAW_DIR / nc_fname)

            try:
                # 1. 下载
                t0 = time.time()
                s3.download_file(S3_BUCKET, nc_key, tmp_path)
                file_size_mb = os.path.getsize(tmp_path) / (1024 * 1024)
                t_download = time.time() - t0
                logger.info(f"    ⬇️  Downloaded {nc_fname} ({file_size_mb:.0f}MB) in {t_download:.1f}s")

                # 2. 裁剪
                t0 = time.time()
                arr = process_nc_to_npy(tmp_path)
                t_crop = time.time() - t0

                if arr is not None:
                    # 3. 保存 .npy
                    SATELLITE_DIR.mkdir(parents=True, exist_ok=True)
                    np.save(str(local_npy), arr)
                    logger.info(f"    ✂️  Cropped to {arr.shape} in {t_crop:.1f}s → {npy_fname}")

                    # 4. 上传到 S3
                    t0 = time.time()
                    _upload_npy(s3, local_npy, npy_fname, date_compact)
                    t_upload = time.time() - t0
                    logger.info(f"    ⬆️  Uploaded .npy to S3 in {t_upload:.1f}s")

                    processed_count += 1
                else:
                    logger.warning(f"    ⚠️  Crop failed for {nc_fname} ({t_crop:.1f}s)")
            finally:
                # 5. 删除临时 .nc
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    logger.info(f"    🗑️  Deleted raw .nc")

    elapsed = time.time() - day_start
    logger.info(
        f"  {date_str}: processed={processed_count}, skipped={skipped_count}, "
        f"time={elapsed:.1f}s"
    )
    return processed_count


def _upload_npy(s3, local_path, npy_fname, date_compact):
    """上传 .npy 到 S3 processed/ 目录。"""
    s3_key = f"processed/satellite/{date_compact}/{npy_fname}"
    try:
        s3.upload_file(str(local_path), S3_BUCKET, s3_key)
    except Exception as e:
        logger.warning(f"S3 upload failed for {npy_fname}: {e}")


def _ensure_h09_symlinks(sat_dir):
    """WeatherDataset hardcodes NC_H09_ prefix for loading .npy files.
    For older Himawari-8 data (NC_H08_), create H09 symlinks.
    """
    sat_path = Path(sat_dir)
    created = 0
    for f in sat_path.glob("NC_H08_*.npy"):
        h09_name = f.name.replace("NC_H08_", "NC_H09_")
        h09_path = sat_path / h09_name
        if not h09_path.exists():
            h09_path.symlink_to(f)
            created += 1
    if created > 0:
        logger.info(f"  Created {created} H09 symlinks for H08 files")


def train_on_accumulated_data(day_info):
    """用累积的本地数据训练模型（和 download_and_train.py 的训练逻辑一致）。"""
    from weather_dataset import WeatherDataset
    from weather_fusion_model import WeatherFusionNet

    date_str = day_info['date']
    logger.info(f"  🧠 Training with data up to {date_str}...")

    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')

    # 准备数据：symlink processed_data → model-tuned/data/satellite
    processed_link = PROJECT_ROOT / "processed_data"
    backup_path = PROJECT_ROOT / "processed_data_backup"

    if processed_link.exists() and not processed_link.is_symlink():
        processed_link.rename(backup_path)
    elif processed_link.is_symlink():
        processed_link.unlink()

    processed_link.symlink_to(SATELLITE_DIR)

    try:
        # WeatherDataset 内部 hardcodes NC_H09_ 前缀，
        # 需要为 H08 文件创建 H09 符号链接以兼容
        _ensure_h09_symlinks(SATELLITE_DIR)

        sensor_csv = DATA_DIR / "real_sensor_data.csv"
        if not sensor_csv.exists():
            logger.warning("No sensor CSV yet, skipping training")
            return

        # WeatherDataset(csv_file, sat_dir, sequence_length)
        dataset = WeatherDataset(
            csv_file=str(sensor_csv),
            sat_dir=str(SATELLITE_DIR),
            sequence_length=SEQUENCE_LENGTH,
        )

        if len(dataset) == 0:
            logger.warning("Dataset empty, skipping training")
            return

        split = int(len(dataset) * 0.8)
        train_ds = torch.utils.data.Subset(dataset, range(split))
        val_ds = torch.utils.data.Subset(dataset, range(split, len(dataset)))

        train_loader = torch.utils.data.DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
        val_loader = torch.utils.data.DataLoader(val_ds, batch_size=BATCH_SIZE)

        # 加载或初始化模型
        model_path = Path(__file__).parent / "models" / "weather_fusion_tuned.pth"
        model = WeatherFusionNet(sat_channels=1, sensor_features=4, prediction_dim=1).to(device)

        if model_path.exists():
            model.load_state_dict(torch.load(model_path, map_location=device, weights_only=True))
            logger.info(f"  Loaded existing model from {model_path.name}")

        optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(optimizer, T_0=10)

        # Focal-inspired weighted loss
        criterion = WeightedMSELoss(rain_threshold=0.1, rain_weight=RAIN_WEIGHT)

        best_val_loss = float('inf')
        no_improve = 0
        patience = 10

        for epoch in range(EPOCHS_PER_DAY):
            # Train
            model.train()
            train_loss = 0.0
            for sat, sensor, target in train_loader:
                sat, sensor, target = sat.to(device), sensor.to(device), target.to(device)
                optimizer.zero_grad()
                pred = model(sat, sensor)
                loss = criterion(pred, target)
                loss.backward()
                optimizer.step()
                train_loss += loss.item()
            train_loss /= len(train_loader)
            scheduler.step()

            # Validate
            model.eval()
            val_loss = 0.0
            val_mae = 0.0
            with torch.no_grad():
                for sat, sensor, target in val_loader:
                    sat, sensor, target = sat.to(device), sensor.to(device), target.to(device)
                    pred = model(sat, sensor)
                    val_loss += criterion(pred, target).item()
                    val_mae += torch.mean(torch.abs(pred - target)).item()
            val_loss /= len(val_loader)
            val_mae /= len(val_loader)

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                no_improve = 0
                model_path.parent.mkdir(parents=True, exist_ok=True)
                torch.save(model.state_dict(), model_path)
            else:
                no_improve += 1

            if (epoch + 1) % 5 == 0 or no_improve == 0:
                marker = "⭐ BEST" if no_improve == 0 else f"(no_improve={no_improve})"
                logger.info(
                    f"    Epoch {epoch+1:3d}/{EPOCHS_PER_DAY}: "
                    f"train_loss={train_loss:.4f} val_loss={val_loss:.4f} "
                    f"val_mae={val_mae:.4f}mm {marker}"
                )

            if no_improve >= patience:
                logger.info(f"    Early stop at epoch {epoch+1}")
                break

        logger.info(f"  ✅ Training done for {date_str}: best_val_loss={best_val_loss:.4f}")

    finally:
        # 恢复 processed_data
        if processed_link.is_symlink():
            processed_link.unlink()
        if backup_path.exists():
            backup_path.rename(processed_link)


class WeightedMSELoss(torch.nn.Module):
    def __init__(self, rain_threshold=0.1, rain_weight=3.0):
        super().__init__()
        self.rain_threshold = rain_threshold
        self.rain_weight = rain_weight

    def forward(self, pred, target):
        weights = torch.where(
            target > self.rain_threshold,
            torch.tensor(self.rain_weight, device=pred.device),
            torch.tensor(1.0, device=pred.device)
        )
        return torch.mean(weights * (pred - target) ** 2)


def main():
    parser = argparse.ArgumentParser(description="V3: 逐日处理卫星数据 + 训练")
    parser.add_argument("--process-only", action="store_true", help="只处理卫星，不训练")
    parser.add_argument("--train-once", action="store_true",
                        help="处理完所有天后集中训练一次（~45min），而非逐天训练（~32h）")
    parser.add_argument("--start", type=str, help="从指定日期开始 (YYYY-MM-DD)")
    parser.add_argument("--max-days", type=int, help="最多处理 N 天")
    args = parser.parse_args()

    # 加载 rainy timestamps
    if not TIMESTAMPS_FILE.exists():
        logger.error(f"Missing {TIMESTAMPS_FILE}. Run scan_rainy_timestamps.py first.")
        return

    with open(TIMESTAMPS_FILE) as f:
        data = json.load(f)

    days = data['days']
    logger.info(f"Loaded {len(days)} days with {data['total_rainy_slots']} rainy slots")

    # 过滤起始日期
    if args.start:
        days = [d for d in days if d['date'] >= args.start]
        logger.info(f"Filtered to {len(days)} days from {args.start}")

    if args.max_days:
        days = days[:args.max_days]
        logger.info(f"Limited to {args.max_days} days")

    # 加载进度状态
    state = load_state()

    # 跳过已处理的日期
    if state['last_processed_date']:
        days = [d for d in days if d['date'] > state['last_processed_date']]
        logger.info(f"Resuming from after {state['last_processed_date']}: {len(days)} days remaining")

    s3 = boto3.client('s3', region_name=S3_REGION)
    total_start = time.time()
    total_processed = 0

    for i, day_info in enumerate(days):
        logger.info(f"\n[{i+1}/{len(days)}] Processing {day_info['date']} "
                     f"({day_info['rainy_slot_count']} slots, {day_info['total_rainfall_mm']:.1f}mm)")

        # Step 1: 处理卫星数据
        count = process_single_day(s3, day_info)
        total_processed += count

        # Step 2: 逐天训练（仅默认模式）
        if not args.process_only and not args.train_once:
            train_on_accumulated_data(day_info)

        # 更新进度
        state['last_processed_date'] = day_info['date']
        state['days_completed'] += 1
        save_state(state)

    # Step 3: 一次性训练（--train-once 模式）
    # 即使 days 为空（数据已全部处理过），也要执行训练
    if args.train_once:
        # 优先用未过滤的 days 列表中最后一天，确保即使所有天已处理也能训练
        all_days = data['days']
        last_day = days[-1] if days else all_days[-1]
        logger.info(f"\n{'='*60}")
        logger.info(f"🧠 Train-once: 用全量数据集中训练一次")
        logger.info(f"{'='*60}")
        train_on_accumulated_data(last_day)

    elapsed = time.time() - total_start
    logger.info(f"\n{'='*60}")
    logger.info(f"COMPLETE: {state['days_completed']} days, {total_processed} new .npy files")
    logger.info(f"Total time: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
