"""
模型评估脚本 — 用验证集评估训练好的 WeatherFusionNet

用法: cd services/training && python3 ../../tools/evaluate.py
或:   在 services/training 目录下直接 python3 ../../tools/evaluate.py

输出:
  - evaluation_results.json (指标)
  - evaluation_plot.png (时序 + 散点图)
"""
import sys
import os

# 确保 services/training 在 Python 搜索路径中
TRAINING_DIR = os.path.join(os.path.dirname(__file__), "..", "services", "training")
sys.path.insert(0, os.path.abspath(TRAINING_DIR))
os.chdir(os.path.abspath(TRAINING_DIR))

import torch
import numpy as np
import json
import logging
from weather_fusion_model import WeatherFusionNet
from weather_dataset import get_dataloaders

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Config ---
MODEL_PATH = "weather_fusion_model.pth"
CSV_PATH = "real_sensor_data.csv"
SAT_DIR = "satellite_data"
DEVICE = torch.device("cpu")
RAIN_THRESHOLD = 1.0  # mm，区分有雨/无雨的阈值（1mm/10min ≈ 小到中雨）


def evaluate_model():
    torch.manual_seed(42)

    # 1. 加载验证集（batch_size=32 提升推理速度）
    logger.info("Loading validation dataset...")
    _, val_loader = get_dataloaders(CSV_PATH, SAT_DIR, batch_size=32, split=0.8)
    logger.info(f"Val batches: {len(val_loader)}")

    # 2. 加载模型 — sensor_features=7 (temp, rain, humidity, pm25, wind_speed, wind_sin, wind_cos)
    model = WeatherFusionNet(sat_channels=1, sensor_features=7, prediction_dim=1)
    if not os.path.exists(MODEL_PATH):
        logger.error(f"Model file not found: {MODEL_PATH}")
        return None

    model.load_state_dict(torch.load(MODEL_PATH, map_location=DEVICE, weights_only=True))
    model.to(DEVICE)
    model.eval()
    logger.info(f"Loaded model from {MODEL_PATH}")

    # 3. 推理
    predictions = []
    actuals = []

    with torch.no_grad():
        for sat, sensor, coord, target in val_loader:
            sat, sensor, coord = sat.to(DEVICE), sensor.to(DEVICE), coord.to(DEVICE)
            output = model(sat, sensor, coord)
            # clamp 避免负降雨量
            preds = torch.clamp(output, min=0.0).cpu().numpy().flatten()
            predictions.extend(preds)
            actuals.extend(target.numpy().flatten())

    predictions = np.array(predictions)
    actuals = np.array(actuals)

    # 4. 回归指标
    mae = np.mean(np.abs(predictions - actuals))
    rmse = np.sqrt(np.mean((predictions - actuals) ** 2))

    # 5. 分类指标（有雨 vs 无雨）
    pred_rain = predictions > RAIN_THRESHOLD
    true_rain = actuals > RAIN_THRESHOLD
    accuracy = np.mean(pred_rain == true_rain)

    tp = int(np.sum(pred_rain & true_rain))
    tn = int(np.sum(~pred_rain & ~true_rain))
    fp = int(np.sum(pred_rain & ~true_rain))
    fn = int(np.sum(~pred_rain & true_rain))
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-8)

    # 输出结果
    print("\n" + "=" * 50)
    print("模型评估结果")
    print("=" * 50)
    print(f"样本数:        {len(predictions)}")
    print(f"MAE:           {mae:.4f} mm")
    print(f"RMSE:          {rmse:.4f} mm")
    print(f"Rain Acc:      {accuracy * 100:.2f}% (threshold={RAIN_THRESHOLD}mm)")
    print(f"Precision:     {precision * 100:.2f}%")
    print(f"Recall:        {recall * 100:.2f}%")
    print(f"F1 Score:      {f1 * 100:.2f}%")
    print(f"TP={tp}  TN={tn}  FP={fp}  FN={fn}")
    print(f"Actual rain:   {np.sum(true_rain)}/{len(actuals)} ({np.sum(true_rain) / len(actuals) * 100:.1f}%)")
    print(f"Pred range:    [{predictions.min():.4f}, {predictions.max():.4f}]")
    print(f"Actual range:  [{actuals.min():.4f}, {actuals.max():.4f}]")
    print("=" * 50)

    # 6. 绘图
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # 左: 时序对比（前 200 个样本）
    n_show = min(200, len(predictions))
    axes[0].plot(actuals[:n_show], label="Actual", color='#2196F3', alpha=0.7, linewidth=1)
    axes[0].plot(predictions[:n_show], label="Predicted", color='#FF9800', alpha=0.7, linewidth=1, linestyle='--')
    axes[0].set_title(f"Time Series (first {n_show} samples)")
    axes[0].set_xlabel("Sample Index")
    axes[0].set_ylabel("Rainfall (mm)")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    # 右: 散点图（Pred vs Actual）
    axes[1].scatter(actuals, predictions, alpha=0.3, s=8, c='#4CAF50')
    max_val = max(np.max(actuals), np.max(predictions), 1.0)
    axes[1].plot([0, max_val], [0, max_val], 'r--', linewidth=1, label="Ideal (y=x)")
    axes[1].set_title("Predicted vs Actual")
    axes[1].set_xlabel("Actual Rain (mm)")
    axes[1].set_ylabel("Predicted Rain (mm)")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    axes[1].set_xlim(0, max_val * 1.05)
    axes[1].set_ylim(0, max_val * 1.05)

    plt.tight_layout()
    plot_path = "evaluation_plot.png"
    plt.savefig(plot_path, dpi=150)
    logger.info(f"Plot saved: {plot_path}")

    # 7. 保存 JSON
    results = {
        'mae': float(mae),
        'rmse': float(rmse),
        'accuracy': float(accuracy),
        'precision': float(precision),
        'recall': float(recall),
        'f1': float(f1),
        'threshold': float(RAIN_THRESHOLD),
        'num_samples': len(predictions),
        'confusion_matrix': {'tp': tp, 'tn': tn, 'fp': fp, 'fn': fn},
        'rain_ratio': float(np.sum(true_rain) / len(actuals)),
    }

    results_file = "evaluation_results.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    logger.info(f"Results saved: {results_file}")

    return results


if __name__ == "__main__":
    evaluate_model()
