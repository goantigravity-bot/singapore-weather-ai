"""
train_single_station.py — 单站两阶段训练

用法:
  # Phase 1: 雨天训练（4 站依次）
  python3 train_single_station.py --phase rain --stations S66 S60 S24 S44

  # Phase 2: 干天 fine-tune（加载 Phase 1 模型）
  python3 train_single_station.py --phase dry --stations S66 S60 S24 S44
"""

import argparse
import json
import logging
import os
import time

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, random_split

from weather_fusion_model import WeatherFusionNet

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATION_DATA_DIR = os.path.join(SCRIPT_DIR, "station_data")
MODEL_DIR = os.path.join(SCRIPT_DIR, "station_models")

RAIN_MODEL_PATH = os.path.join(MODEL_DIR, "model_rain.pth")
FULL_MODEL_PATH = os.path.join(MODEL_DIR, "model_full.pth")


def load_station_npz(station_id, phase):
    """加载某站的 rain 或 dry .npz 数据"""
    filename = "rain_samples.npz" if phase == "rain" else "dry_samples.npz"
    path = os.path.join(STATION_DATA_DIR, station_id, filename)
    if not os.path.exists(path):
        logger.warning(f"  {path} not found, skipping")
        return None
    data = np.load(path)
    logger.info(f"  Loaded {path}: {len(data['label'])} samples")
    return data


def merge_datasets(station_ids, phase):
    """合并多站数据为一个 TensorDataset"""
    all_sat, all_sensor, all_coord, all_label = [], [], [], []

    for sid in station_ids:
        data = load_station_npz(sid, phase)
        if data is None:
            continue
        all_sat.append(data["sat"])
        all_sensor.append(data["sensor"])
        all_coord.append(data["coord"])
        all_label.append(data["label"])

    if not all_sat:
        raise ValueError("No data loaded from any station")

    sat = np.concatenate(all_sat)
    sensor = np.concatenate(all_sensor)
    coord = np.concatenate(all_coord)
    label = np.concatenate(all_label)

    logger.info(f"📊 Merged: {len(label)} total samples from {len(station_ids)} stations")
    logger.info(f"   Rain (>0): {np.sum(label > 0)}, Dry (=0): {np.sum(label == 0)}")
    logger.info(f"   Label range: [{label.min():.2f}, {label.max():.2f}] mm")

    dataset = TensorDataset(
        torch.FloatTensor(sat),
        torch.FloatTensor(sensor),
        torch.FloatTensor(coord),
        torch.FloatTensor(label).unsqueeze(1),  # (N,) → (N, 1)
    )
    return dataset


def evaluate(model, val_loader, device, threshold=5.0):
    """评估模型：MAE / RMSE / 分类指标"""
    model.eval()
    preds, actuals = [], []

    with torch.no_grad():
        for sat, sensor, coord, target in val_loader:
            sat, sensor, coord = sat.to(device), sensor.to(device), coord.to(device)
            output = model(sat, sensor, coord)
            output = torch.clamp(output, min=0.0)
            preds.extend(output.cpu().numpy().flatten())
            actuals.extend(target.numpy().flatten())

    preds = np.array(preds)
    actuals = np.array(actuals)

    mae = np.mean(np.abs(preds - actuals))
    rmse = np.sqrt(np.mean((preds - actuals) ** 2))

    # 分类指标（有雨 vs 无雨）
    pred_rain = preds > threshold
    true_rain = actuals > threshold

    tp = int(np.sum(pred_rain & true_rain))
    tn = int(np.sum(~pred_rain & ~true_rain))
    fp = int(np.sum(pred_rain & ~true_rain))
    fn = int(np.sum(~pred_rain & true_rain))
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-8)

    results = {
        "mae": mae, "rmse": rmse,
        "precision": precision, "recall": recall, "f1": f1,
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "n_samples": len(preds),
        "pred_range": [float(preds.min()), float(preds.max())],
        "actual_range": [float(actuals.min()), float(actuals.max())],
    }

    logger.info("\n" + "=" * 50)
    logger.info("📊 Evaluation Results")
    logger.info("=" * 50)
    logger.info(f"  Samples:     {len(preds)}")
    logger.info(f"  MAE:         {mae:.4f} mm")
    logger.info(f"  RMSE:        {rmse:.4f} mm")
    logger.info(f"  Precision:   {precision * 100:.1f}%")
    logger.info(f"  Recall:      {recall * 100:.1f}%")
    logger.info(f"  F1:          {f1 * 100:.1f}%")
    logger.info(f"  TP={tp}  TN={tn}  FP={fp}  FN={fn}")
    logger.info(f"  Pred range:  [{preds.min():.3f}, {preds.max():.3f}]")
    logger.info(f"  Actual range:[{actuals.min():.3f}, {actuals.max():.3f}]")
    logger.info("=" * 50)

    return results


def train_phase(model, dataset, epochs, lr, device, model_save_path):
    """训练一个 phase"""
    # 80/20 分割
    n_total = len(dataset)
    n_train = int(0.8 * n_total)
    n_val = n_total - n_train
    if n_train == 0:
        n_train = 1
        n_val = n_total - 1

    train_ds, val_ds = random_split(
        dataset, [n_train, n_val],
        generator=torch.Generator().manual_seed(42)
    )

    train_loader = DataLoader(train_ds, batch_size=16, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=32, shuffle=False)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    best_val_loss = float("inf")
    start_time = time.time()

    for epoch in range(1, epochs + 1):
        # Train
        model.train()
        train_loss_sum, train_count = 0.0, 0
        for sat, sensor, coord, target in train_loader:
            sat = sat.to(device)
            sensor = sensor.to(device)
            coord = coord.to(device)
            target = target.to(device)

            optimizer.zero_grad()
            output = model(sat, sensor, coord)
            loss = criterion(output, target)
            loss.backward()
            # 梯度裁剪防止 LSTM 梯度爆炸
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            train_loss_sum += loss.item() * sat.size(0)
            train_count += sat.size(0)

        train_loss = train_loss_sum / max(train_count, 1)

        # Validate
        model.eval()
        val_loss_sum, val_count = 0.0, 0
        with torch.no_grad():
            for sat, sensor, coord, target in val_loader:
                sat = sat.to(device)
                sensor = sensor.to(device)
                coord = coord.to(device)
                target = target.to(device)
                output = model(sat, sensor, coord)
                loss = criterion(output, target)
                val_loss_sum += loss.item() * sat.size(0)
                val_count += sat.size(0)

        val_loss = val_loss_sum / max(val_count, 1)

        if epoch % 10 == 0 or epoch == 1:
            elapsed = time.time() - start_time
            pct = epoch / epochs * 100
            # 基于已完成 epoch 的平均耗时估算剩余时间
            eta = (elapsed / epoch) * (epochs - epoch)
            logger.info(
                f"[Epoch {epoch:3d}/{epochs} ({pct:.0f}%)] | "
                f"Train: {train_loss:.5f} | Val: {val_loss:.5f} | "
                f"Elapsed: {elapsed:.0f}s | ETA: {eta:.0f}s"
            )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), model_save_path)

    total_time = time.time() - start_time
    logger.info(f"✅ Training done in {total_time:.0f}s, best val_loss={best_val_loss:.5f}")
    logger.info(f"💾 Model saved: {model_save_path}")

    # 评估
    # 重新加载最佳模型
    model.load_state_dict(torch.load(model_save_path, map_location=device, weights_only=True))
    results = evaluate(model, val_loader, device)
    return results


def main():
    parser = argparse.ArgumentParser(description="Single-station two-phase training")
    parser.add_argument("--phase", choices=["rain", "dry"], required=True)
    parser.add_argument("--stations", nargs="+", default=["S66", "S60", "S24", "S44"])
    parser.add_argument("--epochs", type=int, default=50)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"🔧 Device: {device}")

    os.makedirs(MODEL_DIR, exist_ok=True)

    # 合并数据
    dataset = merge_datasets(args.stations, args.phase)

    if args.phase == "rain":
        # Phase 1: 从零训练
        logger.info("🌧️  Phase 1: Rain-only training")
        model = WeatherFusionNet(sat_channels=1, sensor_features=7, prediction_dim=1)
        model.to(device)
        lr = 1e-3
        save_path = RAIN_MODEL_PATH

    else:
        # Phase 2: 加载 Phase 1 模型，fine-tune
        logger.info("☀️  Phase 2: Dry fine-tune (loading rain model)")
        if not os.path.exists(RAIN_MODEL_PATH):
            logger.error(f"Rain model not found: {RAIN_MODEL_PATH}")
            logger.error("Run Phase 1 first: --phase rain")
            return

        model = WeatherFusionNet(sat_channels=1, sensor_features=7, prediction_dim=1)
        model.load_state_dict(torch.load(RAIN_MODEL_PATH, map_location=device, weights_only=True))
        model.to(device)
        lr = 1e-4  # 降低学习率，避免遗忘雨天知识
        save_path = FULL_MODEL_PATH

    total_params = sum(p.numel() for p in model.parameters())
    logger.info(f"🧠 Model: WeatherFusionNet ({total_params:,} params)")
    logger.info(f"📋 Config: stations={args.stations}, epochs={args.epochs}, lr={lr}, batch=16")
    logger.info(f"📦 Dataset: {len(dataset)} samples")

    results = train_phase(model, dataset, args.epochs, lr, device, save_path)

    # 保存结果 JSON
    results_path = os.path.join(MODEL_DIR, f"results_{args.phase}.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"📄 Results saved: {results_path}")


if __name__ == "__main__":
    main()
