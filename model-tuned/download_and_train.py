"""
Step 2: 从 S3 下载预处理卫星数据 + 传感器数据，在本地训练 WeatherFusionNet。
要求: AWS credentials 已配置, rainy_dates.json 已生成(Step 1)

目录结构:
  model-tuned/data/satellite/  -- 存放 .npy 卫星图
  model-tuned/data/sensor/     -- 传感器 CSV
  model-tuned/models/          -- 训练产出的模型
"""
import boto3
import json
import logging
import os
import sys
import time
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from pathlib import Path
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ── Paths ──
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
SAT_DIR = DATA_DIR / "satellite"
SENSOR_DIR = DATA_DIR / "sensor"
MODEL_DIR = BASE_DIR / "models"
RESULTS_DIR = BASE_DIR / "results"

S3_BUCKET = "weather-ai-models-de08370c"
S3_REGION = "ap-southeast-1"

# ── 训练超参 ──
EPOCHS = 50
BATCH_SIZE = 32
LEARNING_RATE = 1e-3
RAIN_WEIGHT = 3.0
SEQUENCE_LENGTH = 6
TRAIN_SPLIT = 0.8

# ── 导入项目已有的模型和数据集 ──
PROJECT_ROOT = BASE_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
from weather_fusion_model import WeatherFusionNet
from weather_dataset import WeatherDataset


class WeightedMSELoss(nn.Module):
    """有雨样本权重更高，迫使模型学习降雨特征而非永远预测0。"""
    def __init__(self, rain_threshold=0.1, rain_weight=10.0):
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


# ═══════════════════════════════════════════
# Step 2a: 从 S3 下载数据
# ═══════════════════════════════════════════
def download_data():
    """下载 rainy dates 对应的卫星 .npy 和传感器 JSON 到本地。"""
    rainy_dates_file = DATA_DIR / "rainy_dates.json"
    if not rainy_dates_file.exists():
        logger.error(f"Missing {rainy_dates_file}. Run scan_rainy_dates.py first.")
        sys.exit(1)

    with open(rainy_dates_file) as f:
        scan_result = json.load(f)

    rainy_days = scan_result['rainy_days']
    logger.info(f"Found {len(rainy_days)} rainy days to download")

    SAT_DIR.mkdir(parents=True, exist_ok=True)
    SENSOR_DIR.mkdir(parents=True, exist_ok=True)

    s3 = boto3.client('s3', region_name=S3_REGION)

    # 也下载一些无雨天数据，让模型学会区分
    all_days = scan_result['all_days']
    dry_days = [d for d in all_days if not d['is_rainy'] and d['has_satellite_raw']]
    # 控制比例：干/湿 ≈ 1:2（78天有雨，取约40天无雨），避免再次不平衡
    import random
    random.seed(42)
    selected_dry = random.sample(dry_days, min(len(dry_days), len(rainy_days) // 2))
    target_days = rainy_days + selected_dry
    target_dates = sorted([d['date'] for d in target_days])

    logger.info(f"Training set: {len(rainy_days)} rainy + {len(selected_dry)} dry = {len(target_dates)} days")

    # ── 下载卫星 .npy ──
    sat_downloaded = 0
    for i, date_str in enumerate(target_dates):
        date_compact = date_str.replace('-', '')
        prefix = f"processed/satellite/{date_compact}/"

        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix, MaxKeys=200)
        objects = resp.get('Contents', [])

        if not objects:
            logger.warning(f"  [{i+1}/{len(target_dates)}] {date_str}: No processed satellite data in S3")
            continue

        for obj in objects:
            key = obj['Key']
            filename = key.split('/')[-1]
            local_path = SAT_DIR / filename

            if local_path.exists():
                continue

            s3.download_file(S3_BUCKET, key, str(local_path))
            sat_downloaded += 1

        logger.info(f"  [{i+1}/{len(target_dates)}] {date_str}: {len(objects)} satellite files")

    logger.info(f"Satellite: downloaded {sat_downloaded} new .npy files")

    # ── 下载传感器 JSON → 构建 CSV ──
    sensor_types = ['rainfall', 'temperature', 'humidity', 'pm25']
    all_records = []

    for i, date_str in enumerate(target_dates):
        day_records = []
        for stype in sensor_types:
            key = f"govdata/{stype}_{date_str}.json"
            try:
                resp = s3.get_object(Bucket=S3_BUCKET, Key=key)
                data = json.loads(resp['Body'].read())
            except Exception:
                continue

            if stype == 'pm25':
                # PM2.5 数据结构不同：按区域而非按站点
                for item in data.get('items', []):
                    ts = item.get('timestamp', '')
                    readings = item.get('readings', {}).get('pm25_one_hourly', {})
                    # 用全国平均值作为每站的 PM2.5
                    avg_pm25 = np.mean(list(readings.values())) if readings else 0
                    day_records.append({
                        'timestamp': ts,
                        'sensor_id': '__pm25__',
                        'type': 'pm25',
                        'value': avg_pm25,
                    })
            else:
                for item in data.get('items', []):
                    ts = item.get('timestamp', '')
                    for reading in item.get('readings', []):
                        day_records.append({
                            'timestamp': ts,
                            'sensor_id': reading.get('station_id', ''),
                            'type': stype,
                            'value': reading.get('value', 0),
                        })

        if day_records:
            df_raw = pd.DataFrame(day_records)
            df_raw['timestamp'] = pd.to_datetime(df_raw['timestamp'])

            # PM2.5 单独处理：广播到所有站
            pm25_df = df_raw[df_raw['type'] == 'pm25'].copy()
            other_df = df_raw[df_raw['type'] != 'pm25']

            # Pivot 非 PM2.5 数据
            if not other_df.empty:
                df_pivot = other_df.pivot_table(
                    index=['timestamp', 'sensor_id'],
                    columns='type',
                    values='value',
                    aggfunc='mean',
                ).reset_index()

                # 合并 PM2.5（按时间匹配最近值）
                if not pm25_df.empty:
                    pm25_hourly = pm25_df.groupby(
                        pd.Grouper(key='timestamp', freq='1h')
                    )['value'].mean().reset_index()
                    pm25_hourly.columns = ['timestamp', 'pm25']

                    df_pivot['hour_key'] = df_pivot['timestamp'].dt.floor('1h')
                    pm25_hourly['hour_key'] = pm25_hourly['timestamp'].dt.floor('1h')

                    df_pivot = df_pivot.merge(
                        pm25_hourly[['hour_key', 'pm25']],
                        on='hour_key',
                        how='left',
                    )
                    df_pivot.drop(columns=['hour_key'], inplace=True)

                if 'pm25' not in df_pivot.columns:
                    df_pivot['pm25'] = 0.0

                all_records.append(df_pivot)

        if (i + 1) % 10 == 0:
            logger.info(f"  Processed sensor data: {i+1}/{len(target_dates)} days")

    if not all_records:
        logger.error("No sensor records downloaded!")
        sys.exit(1)

    sensor_df = pd.concat(all_records, ignore_index=True)

    # 确保列齐全
    for col in ['temperature', 'rainfall', 'humidity', 'pm25']:
        if col not in sensor_df.columns:
            sensor_df[col] = 0.0

    sensor_df = sensor_df.ffill().fillna(0.0)
    sensor_df = sensor_df.sort_values(['sensor_id', 'timestamp'])

    csv_path = DATA_DIR / "real_sensor_data.csv"
    sensor_df.to_csv(csv_path, index=False)
    logger.info(f"Sensor CSV: {len(sensor_df):,} rows saved to {csv_path}")

    return csv_path


# ═══════════════════════════════════════════
# Step 2b: 本地训练
# ═══════════════════════════════════════════
def train():
    """使用下载的数据本地训练 WeatherFusionNet。"""
    csv_path = DATA_DIR / "real_sensor_data.csv"
    if not csv_path.exists():
        logger.error("No sensor CSV found. Run download first.")
        sys.exit(1)

    # 选择设备
    if torch.backends.mps.is_available():
        device = torch.device("mps")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")
    logger.info(f"Using device: {device}")

    # 构建数据集 — 使用项目原有的 WeatherDataset
    # 但 pointed satellite 目录改为 model-tuned/data/satellite
    # WeatherDataset 会从 processed_data/ 加载 .npy
    # 需要临时 symlink 或修改路径
    processed_data_link = PROJECT_ROOT / "processed_data"
    original_processed = None

    # 备份原始 processed_data 路径
    if processed_data_link.exists() and not processed_data_link.is_symlink():
        original_processed = PROJECT_ROOT / "processed_data_backup"
        if not original_processed.exists():
            processed_data_link.rename(original_processed)
            logger.info(f"Backed up original processed_data to {original_processed}")

    # 创建 symlink 指向我们的卫星数据
    if not processed_data_link.exists():
        processed_data_link.symlink_to(SAT_DIR.resolve())
        logger.info(f"Symlinked processed_data -> {SAT_DIR}")

    try:
        # 切换工作目录让 WeatherDataset 能找到文件
        old_cwd = os.getcwd()
        os.chdir(PROJECT_ROOT)

        dataset = WeatherDataset(
            csv_file=str(csv_path),
            sat_dir=str(SAT_DIR),
            sequence_length=SEQUENCE_LENGTH,
        )

        if len(dataset) == 0:
            logger.error("Dataset is empty after processing!")
            return

        # Time-based split: 前80%时间训练，后20%测试
        n_total = len(dataset)
        n_train = int(n_total * TRAIN_SPLIT)
        n_val = n_total - n_train

        train_dataset = torch.utils.data.Subset(dataset, range(n_train))
        val_dataset = torch.utils.data.Subset(dataset, range(n_train, n_total))

        train_loader = torch.utils.data.DataLoader(
            train_dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=0,
        )
        val_loader = torch.utils.data.DataLoader(
            val_dataset, batch_size=BATCH_SIZE, shuffle=False, num_workers=0,
        )

        logger.info(f"Dataset: {n_total} samples (train={n_train}, val={n_val})")

        # 模型
        model = WeatherFusionNet(
            sat_channels=1,   # 单通道卫星图（红外亮温）
            sensor_features=4, # temperature, rainfall, humidity, pm25
            prediction_dim=1,
        ).to(device)

        criterion = WeightedMSELoss(rain_weight=RAIN_WEIGHT)
        optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
        scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(
            optimizer, T_0=10, T_mult=2,
        )

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)

        best_val_loss = float('inf')
        no_improve = 0
        patience = 15
        history = {'train_loss': [], 'val_loss': [], 'val_mae': []}

        logger.info(f"Training: {EPOCHS} epochs, batch={BATCH_SIZE}, lr={LEARNING_RATE}, rain_weight={RAIN_WEIGHT}")

        for epoch in range(EPOCHS):
            # ── Train ──
            model.train()
            train_loss = 0.0
            train_batches = 0

            for sat, sensor, target in train_loader:
                sat = sat.to(device)
                sensor = sensor.to(device)
                target = target.to(device)

                optimizer.zero_grad()
                pred = model(sat, sensor)
                loss = criterion(pred, target)
                loss.backward()
                optimizer.step()

                train_loss += loss.item()
                train_batches += 1

            avg_train_loss = train_loss / max(train_batches, 1)

            # ── Validate ──
            model.eval()
            val_loss = 0.0
            val_mae = 0.0
            val_batches = 0

            with torch.no_grad():
                for sat, sensor, target in val_loader:
                    sat = sat.to(device)
                    sensor = sensor.to(device)
                    target = target.to(device)

                    pred = model(sat, sensor)
                    loss = criterion(pred, target)
                    mae = torch.mean(torch.abs(pred - target))

                    val_loss += loss.item()
                    val_mae += mae.item()
                    val_batches += 1

            avg_val_loss = val_loss / max(val_batches, 1)
            avg_val_mae = val_mae / max(val_batches, 1)

            scheduler.step()

            history['train_loss'].append(avg_train_loss)
            history['val_loss'].append(avg_val_loss)
            history['val_mae'].append(avg_val_mae)

            # ── Early stopping + save best ──
            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                no_improve = 0
                model_path = MODEL_DIR / "weather_fusion_tuned.pth"
                torch.save(model.state_dict(), model_path)
            else:
                no_improve += 1

            if (epoch + 1) % 5 == 0 or no_improve == 0:
                logger.info(
                    f"  Epoch {epoch+1:>3}/{EPOCHS}: "
                    f"train_loss={avg_train_loss:.6f} val_loss={avg_val_loss:.6f} "
                    f"val_mae={avg_val_mae:.4f}mm "
                    f"{'⭐ BEST' if no_improve == 0 else f'(no_improve={no_improve})'}"
                )

            if no_improve >= patience:
                logger.info(f"Early stopping at epoch {epoch+1}")
                break

        # ── 保存训练历史 ──
        metrics = {
            'best_val_loss': best_val_loss,
            'final_epoch': epoch + 1,
            'history': history,
            'config': {
                'epochs': EPOCHS,
                'batch_size': BATCH_SIZE,
                'lr': LEARNING_RATE,
                'rain_weight': RAIN_WEIGHT,
                'device': str(device),
                'n_train': n_train,
                'n_val': n_val,
            }
        }
        with open(RESULTS_DIR / "training_metrics.json", 'w') as f:
            json.dump(metrics, f, indent=2)

        logger.info(f"✅ Training done. Best val_loss={best_val_loss:.6f}")
        logger.info(f"   Model saved: {MODEL_DIR / 'weather_fusion_tuned.pth'}")

    finally:
        os.chdir(old_cwd)
        # 清理 symlink
        if processed_data_link.is_symlink():
            processed_data_link.unlink()
        if original_processed and original_processed.exists():
            original_processed.rename(processed_data_link)
            logger.info("Restored original processed_data")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download S3 data and train locally")
    parser.add_argument('--download-only', action='store_true', help='Only download, skip training')
    parser.add_argument('--train-only', action='store_true', help='Only train with existing data')
    args = parser.parse_args()

    start_time = time.time()

    if not args.train_only:
        logger.info("=" * 60)
        logger.info("Step 2a: Downloading data from S3")
        logger.info("=" * 60)
        download_data()

    if not args.download_only:
        logger.info("=" * 60)
        logger.info("Step 2b: Training WeatherFusionNet")
        logger.info("=" * 60)
        train()

    elapsed = time.time() - start_time
    logger.info(f"\nTotal time: {elapsed:.1f}s ({elapsed/60:.1f}min)")
