"""
train_direct.py V3 — 直接训练新模型

改进 (相比 V2):
  - 使用 Focal Loss + 物理约束组合损失（替代 MSE）
  - 训练中跟踪分类指标（F1, Precision, Recall）
  - 支持 AMP 混合精度训练
  - 梯度裁剪防止梯度爆炸
  - 学习率余弦退火调度

用法: python3 train_direct.py [--epochs 50] [--batch-size 32]
"""
import argparse
import logging
import time
import os
import numpy as np
import torch
import torch.nn as nn
from weather_fusion_model import WeatherFusionNet, get_combined_loss
from weather_dataset import get_dataloaders

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def compute_classification_metrics(logits, targets, threshold=0.5):
    """从 logits 和二值标签计算分类指标。"""
    probs = torch.sigmoid(logits).detach()
    preds = (probs > threshold).float()

    tp = ((preds == 1) & (targets == 1)).sum().item()
    tn = ((preds == 0) & (targets == 0)).sum().item()
    fp = ((preds == 1) & (targets == 0)).sum().item()
    fn = ((preds == 0) & (targets == 1)).sum().item()

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-8)
    accuracy = (tp + tn) / max(tp + tn + fp + fn, 1)

    return {
        'accuracy': accuracy, 'precision': precision,
        'recall': recall, 'f1': f1,
        'tp': tp, 'tn': tn, 'fp': fp, 'fn': fn
    }


def train(epochs: int, batch_size: int, lr: float, model_path: str,
          focal_alpha: float = 0.75, focal_gamma: float = 2.0,
          physics_weight: float = 0.1, no_upload: bool = True,
          num_sat_frames: int = 1):
    device = torch.device("cuda" if torch.cuda.is_available() else
                          "mps" if torch.backends.mps.is_available() else "cpu")
    logger.info(f"🔧 Device: {device}")
    if device.type == "cuda":
        logger.info(f"   GPU: {torch.cuda.get_device_name(0)}")

    # 数据加载（启用时间切分验证）
    # 路径支持环境变量覆盖（train_yearly.sh 逐年传入不同路径）
    logger.info("📊 Loading dataset...")
    csv_path = os.environ.get("CSV_PATH", "real_sensor_data.csv")
    sat_dir = os.environ.get("SAT_DIR", "processed_data")
    logger.info(f"   CSV: {csv_path}")
    logger.info(f"   SAT: {sat_dir}")
    train_loader, val_loader = get_dataloaders(
        csv_path, sat_dir, batch_size=batch_size, temporal_split=True,
        num_sat_frames=num_sat_frames
    )
    logger.info(f"   Train batches: {len(train_loader)}, Val batches: {len(val_loader)}")

    # 模型初始化
    # sensor_features=13: temp, rain, humid, pm25, ws, w_sin, w_cos,
    #                     h_sin, h_cos, m_sin, m_cos, Δh, Δt
    model = WeatherFusionNet(
        sat_channels=3, sensor_features=13, coord_dim=2,
        num_sat_frames=num_sat_frames, use_cross_attention=True
    )
    model.to(device)

    total_params = sum(p.numel() for p in model.parameters())
    logger.info(f"🧠 Model: WeatherFusionNet V3 ({total_params:,} params)")

    # 增量训练：若模型文件已存在，加载权重继续训练
    if os.path.exists(model_path):
        checkpoint = torch.load(model_path, map_location=device, weights_only=False)
        if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
            model.load_state_dict(checkpoint['model_state_dict'])
        else:
            model.load_state_dict(checkpoint)
        logger.info(f"   📂 Loaded existing weights from {model_path} (incremental training)")
    else:
        logger.info(f"   🆕 Training from scratch (no existing model at {model_path})")

    # 组合损失: Focal Loss + 物理约束
    loss_fn = get_combined_loss(
        alpha=focal_alpha, gamma=focal_gamma,
        physics_weight=physics_weight
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    # 余弦退火学习率调度
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-6)

    # AMP 混合精度（仅 CUDA）
    use_amp = device.type == "cuda"
    scaler = torch.amp.GradScaler('cuda') if use_amp else None

    best_val_f1 = 0.0
    best_epoch = -1
    start_time = time.time()

    for epoch in range(1, epochs + 1):
        # --- Train ---
        model.train()
        train_loss_sum = 0.0
        train_count = 0
        all_logits = []
        all_targets = []

        for sat, sensor, coord, target in train_loader:
            sat = sat.to(device)
            sensor = sensor.to(device)
            coord = coord.to(device)
            target = target.to(device)

            optimizer.zero_grad()

            if use_amp:
                with torch.amp.autocast('cuda'):
                    logits = model(sat, sensor, coord)
                    loss = loss_fn(logits, target, sensor)
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                scaler.step(optimizer)
                scaler.update()
            else:
                logits = model(sat, sensor, coord)
                loss = loss_fn(logits, target, sensor)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimizer.step()

            train_loss_sum += loss.item() * sat.size(0)
            train_count += sat.size(0)

        scheduler.step()
        train_loss = train_loss_sum / max(train_count, 1)

        # --- Validate ---
        model.eval()
        val_loss_sum = 0.0
        val_count = 0
        val_logits_all = []
        val_targets_all = []

        with torch.no_grad():
            for sat, sensor, coord, target in val_loader:
                sat = sat.to(device)
                sensor = sensor.to(device)
                coord = coord.to(device)
                target = target.to(device)

                logits = model(sat, sensor, coord)
                loss = loss_fn(logits, target, sensor)
                val_loss_sum += loss.item() * sat.size(0)
                val_count += sat.size(0)

                val_logits_all.append(logits.cpu())
                val_targets_all.append(target.cpu())

        val_loss = val_loss_sum / max(val_count, 1)

        # 分类指标
        val_logits_cat = torch.cat(val_logits_all)
        val_targets_cat = torch.cat(val_targets_all)
        metrics = compute_classification_metrics(val_logits_cat, val_targets_cat)

        elapsed = time.time() - start_time
        lr_current = scheduler.get_last_lr()[0]
        logger.info(
            f"Epoch {epoch:3d}/{epochs} | "
            f"Loss: {train_loss:.4f}/{val_loss:.4f} | "
            f"F1: {metrics['f1']:.3f} Prec: {metrics['precision']:.3f} "
            f"Rec: {metrics['recall']:.3f} Acc: {metrics['accuracy']:.3f} | "
            f"LR: {lr_current:.2e} | {elapsed:.0f}s"
        )

        # 保存 F1 最优模型（而非 val_loss 最低）
        if metrics['f1'] > best_val_f1:
            best_val_f1 = metrics['f1']
            best_epoch = epoch
            torch.save({
                'model_state_dict': model.state_dict(),
                'num_sat_frames': num_sat_frames,
            }, model_path)
            logger.info(
                f"   💾 Best model saved (epoch {epoch}, "
                f"F1={metrics['f1']:.3f}, Prec={metrics['precision']:.3f})"
            )

    total_time = time.time() - start_time
    logger.info(f"✅ Training complete in {total_time:.0f}s")
    logger.info(f"   Best: epoch {best_epoch}, F1={best_val_f1:.3f}")

    # 上传到 S3（默认关闭，需显式 --upload 才推送）
    if no_upload:
        logger.info("   🔒 S3 upload SKIPPED (--no-upload). Model saved locally only.")
        logger.info(f"      Local path: {os.path.abspath(model_path)}")
    else:
        try:
            import boto3
            s3 = boto3.client("s3")
            bucket = os.environ.get("S3_BUCKET", "weather-ai-models-gcc")
            s3.upload_file(model_path, bucket, "models/latest.pth")
            logger.info(f"   ☁️ Uploaded to s3://{bucket}/models/latest.pth")
        except Exception as e:
            logger.warning(f"   ⚠️ S3 upload failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Weather AI V3 Training")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--model-path", default="weather_fusion_model_v3.pth",
                        help="Save path (default: v3 suffix to avoid overwriting V2)")
    parser.add_argument("--focal-alpha", type=float, default=0.75,
                        help="Focal Loss alpha (positive class weight)")
    parser.add_argument("--focal-gamma", type=float, default=2.0,
                        help="Focal Loss gamma (focus parameter)")
    parser.add_argument("--physics-weight", type=float, default=0.1,
                        help="Physics constraint loss weight")
    parser.add_argument("--upload", action="store_true", default=False,
                        help="Upload to S3 after training (default: NO upload)")
    parser.add_argument("--sat-frames", type=int, default=1,
                        help="Number of satellite frames (1=single, 6=temporal)")
    args = parser.parse_args()

    train(args.epochs, args.batch_size, args.lr, args.model_path,
          args.focal_alpha, args.focal_gamma, args.physics_weight,
          no_upload=not args.upload, num_sat_frames=args.sat_frames)
