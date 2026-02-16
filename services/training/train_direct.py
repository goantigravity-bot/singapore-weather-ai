"""
train_direct.py  — 直接使用本地 CSV + .npy 从零训练新模型

用法: python3 train_direct.py [--epochs 50] [--batch-size 16]

前提条件:
  - real_sensor_data.csv 在当前目录
  - processed_data/ 下有预处理好的 .npy 卫星图
  - weather_fusion_model.py 和 weather_dataset.py 在当前目录
"""

import argparse
import logging
import time
import os
import torch
import torch.nn as nn
from weather_fusion_model import WeatherFusionNet
from weather_dataset import get_dataloaders

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def train(epochs: int, batch_size: int, lr: float, model_path: str):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"🔧 Device: {device}")
    if device.type == "cuda":
        logger.info(f"   GPU: {torch.cuda.get_device_name(0)}")

    # 数据加载
    logger.info("📊 Loading dataset...")
    csv_path = "real_sensor_data.csv"
    sat_dir = "satellite_data"
    train_loader, val_loader = get_dataloaders(csv_path, sat_dir, batch_size=batch_size)
    logger.info(f"   Train batches: {len(train_loader)}, Val batches: {len(val_loader)}")

    # 模型初始化（sensor_features=7: temp, rain, humidity, pm25, wind_speed, wind_sin, wind_cos）
    model = WeatherFusionNet(sat_channels=1, sensor_features=7, prediction_dim=1)
    model.to(device)

    total_params = sum(p.numel() for p in model.parameters())
    logger.info(f"🧠 Model: WeatherFusionNet ({total_params:,} params)")

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    best_val_loss = float("inf")
    best_epoch = -1
    start_time = time.time()

    for epoch in range(1, epochs + 1):
        # --- Train ---
        model.train()
        train_loss_sum = 0.0
        train_count = 0
        for sat, sensor, coord, target in train_loader:
            sat = sat.to(device)
            sensor = sensor.to(device)
            coord = coord.to(device)
            target = target.to(device)

            optimizer.zero_grad()
            output = model(sat, sensor, coord)
            loss = criterion(output, target)
            loss.backward()
            optimizer.step()

            train_loss_sum += loss.item() * sat.size(0)
            train_count += sat.size(0)

        train_loss = train_loss_sum / max(train_count, 1)

        # --- Validate ---
        model.eval()
        val_loss_sum = 0.0
        val_count = 0
        val_mae_sum = 0.0
        with torch.no_grad():
            for sat, sensor, coord, target in val_loader:
                sat = sat.to(device)
                sensor = sensor.to(device)
                coord = coord.to(device)
                target = target.to(device)

                output = model(sat, sensor, coord)
                loss = criterion(output, target)
                val_loss_sum += loss.item() * sat.size(0)
                val_mae_sum += torch.abs(output - target).sum().item()
                val_count += sat.size(0)

        val_loss = val_loss_sum / max(val_count, 1)
        val_mae = val_mae_sum / max(val_count, 1)

        elapsed = time.time() - start_time
        logger.info(
            f"Epoch {epoch:3d}/{epochs} | "
            f"Train Loss: {train_loss:.5f} | "
            f"Val Loss: {val_loss:.5f} | "
            f"Val MAE: {val_mae:.5f} | "
            f"Time: {elapsed:.0f}s"
        )

        # 保存最优模型
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_epoch = epoch
            torch.save(model.state_dict(), model_path)
            logger.info(f"   💾 Saved best model (epoch {epoch}, val_loss={val_loss:.5f})")

    total_time = time.time() - start_time
    logger.info(f"✅ Training complete in {total_time:.0f}s")
    logger.info(f"   Best: epoch {best_epoch}, val_loss={best_val_loss:.5f}")

    # 上传到 S3
    try:
        import boto3
        s3 = boto3.client("s3")
        bucket = os.environ.get("S3_BUCKET", "weather-ai-models-de08370c")
        s3.upload_file(model_path, bucket, f"models/latest.pth")
        logger.info(f"   ☁️ Uploaded to s3://{bucket}/models/latest.pth")
    except Exception as e:
        logger.warning(f"   ⚠️ S3 upload failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Direct GPU training")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--model-path", default="weather_fusion_model.pth")
    args = parser.parse_args()

    train(args.epochs, args.batch_size, args.lr, args.model_path)
