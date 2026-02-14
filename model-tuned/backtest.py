"""
Step 3: 回测评估 — 用测试集对比模型预测 vs 实际降雨。
"""
import json
import logging
import os
import sys
import numpy as np
import torch
import torch.nn as nn
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
SAT_DIR = DATA_DIR / "satellite"
MODEL_DIR = BASE_DIR / "models"
RESULTS_DIR = BASE_DIR / "results"

PROJECT_ROOT = BASE_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
from weather_fusion_model import WeatherFusionNet
from weather_dataset import WeatherDataset

SEQUENCE_LENGTH = 6
TRAIN_SPLIT = 0.8
# 降雨判断阈值: 预测/实际值 > 此阈值视为"有雨"
RAIN_DETECT_THRESHOLD = 0.5


def main():
    csv_path = DATA_DIR / "real_sensor_data.csv"
    model_path = MODEL_DIR / "weather_fusion_tuned.pth"

    if not csv_path.exists():
        logger.error(f"Missing {csv_path}. Run download_and_train.py first.")
        sys.exit(1)
    if not model_path.exists():
        logger.error(f"Missing {model_path}. Run download_and_train.py first.")
        sys.exit(1)

    # 选择设备
    if torch.backends.mps.is_available():
        device = torch.device("mps")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")
    logger.info(f"Device: {device}")

    # ── 设置 symlink ──
    processed_data_link = PROJECT_ROOT / "processed_data"
    original_processed = None

    if processed_data_link.exists() and not processed_data_link.is_symlink():
        original_processed = PROJECT_ROOT / "processed_data_backup"
        if not original_processed.exists():
            processed_data_link.rename(original_processed)

    if not processed_data_link.exists():
        processed_data_link.symlink_to(SAT_DIR.resolve())

    try:
        old_cwd = os.getcwd()
        os.chdir(PROJECT_ROOT)

        # ── 加载数据集 ──
        dataset = WeatherDataset(
            csv_file=str(csv_path),
            sat_dir=str(SAT_DIR),
            sequence_length=SEQUENCE_LENGTH,
        )

        n_total = len(dataset)
        n_train = int(n_total * TRAIN_SPLIT)
        n_val = n_total - n_train

        val_dataset = torch.utils.data.Subset(dataset, range(n_train, n_total))
        val_loader = torch.utils.data.DataLoader(val_dataset, batch_size=64, shuffle=False)

        logger.info(f"Test set: {n_val} samples")

        # ── 加载模型 ──
        model = WeatherFusionNet(
            sat_channels=1,
            sensor_features=4,
            prediction_dim=1,
        ).to(device)
        model.load_state_dict(torch.load(model_path, map_location=device, weights_only=True))
        model.eval()

        # ── 逐批预测 ──
        all_preds = []
        all_targets = []

        with torch.no_grad():
            for sat, sensor, target in val_loader:
                sat = sat.to(device)
                sensor = sensor.to(device)
                pred = model(sat, sensor)
                all_preds.append(pred.cpu().numpy().flatten())
                all_targets.append(target.numpy().flatten())

        preds = np.concatenate(all_preds)
        targets = np.concatenate(all_targets)

        # ── 计算指标 ──
        mae = np.mean(np.abs(preds - targets))
        rmse = np.sqrt(np.mean((preds - targets) ** 2))

        # 降雨判断: 实际>0.1 且 预测>0.1 视为正确判断
        actual_rain = targets > RAIN_DETECT_THRESHOLD
        pred_rain = preds > RAIN_DETECT_THRESHOLD
        actual_no_rain = ~actual_rain
        pred_no_rain = ~pred_rain

        tp = np.sum(actual_rain & pred_rain)       # 有雨且预测有雨
        tn = np.sum(actual_no_rain & pred_no_rain)  # 无雨且预测无雨
        fp = np.sum(actual_no_rain & pred_rain)      # 无雨但预测有雨（误报）
        fn = np.sum(actual_rain & pred_no_rain)      # 有雨但预测无雨（漏报）

        accuracy = (tp + tn) / len(targets) * 100 if len(targets) > 0 else 0
        precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        # 按降雨量分桶
        bins = [(0, 0.1, "无雨"), (0.1, 2, "小雨"), (2, 10, "中雨"), (10, 100, "大雨")]
        bucket_stats = []
        for low, high, label in bins:
            mask = (targets >= low) & (targets < high)
            n = np.sum(mask)
            if n > 0:
                bucket_mae = np.mean(np.abs(preds[mask] - targets[mask]))
                bucket_stats.append({
                    'label': label,
                    'range': f"{low}-{high}mm",
                    'count': int(n),
                    'mae': round(float(bucket_mae), 4),
                })

        logger.info(f"\n{'='*60}")
        logger.info(f"BACKTEST RESULTS ({n_val} samples)")
        logger.info(f"{'='*60}")
        logger.info(f"  MAE:       {mae:.4f}mm")
        logger.info(f"  RMSE:      {rmse:.4f}mm")
        logger.info(f"  Accuracy:  {accuracy:.1f}%")
        logger.info(f"  Precision: {precision:.1f}%")
        logger.info(f"  Recall:    {recall:.1f}%")
        logger.info(f"  F1 Score:  {f1:.1f}%")
        logger.info(f"\n  Confusion Matrix:")
        logger.info(f"    TP={tp} (rain→rain)  FP={fp} (dry→rain)")
        logger.info(f"    FN={fn} (rain→dry)   TN={tn} (dry→dry)")

        for bs in bucket_stats:
            logger.info(f"\n  {bs['label']} ({bs['range']}): {bs['count']} samples, MAE={bs['mae']}mm")

        # ── 保存结果 ──
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        results = {
            'n_test': n_val,
            'mae': round(float(mae), 4),
            'rmse': round(float(rmse), 4),
            'accuracy': round(accuracy, 1),
            'precision': round(precision, 1),
            'recall': round(recall, 1),
            'f1': round(f1, 1),
            'confusion_matrix': {'TP': int(tp), 'TN': int(tn), 'FP': int(fp), 'FN': int(fn)},
            'bucket_stats': bucket_stats,
        }
        with open(RESULTS_DIR / "backtest_results.json", 'w') as f:
            json.dump(results, f, indent=2)

        # ── 生成对比图 ──
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 3, figsize=(18, 5))

            # 1. 时间序列对比（抽样500个点）
            sample_n = min(500, len(targets))
            idx = np.linspace(0, len(targets) - 1, sample_n).astype(int)
            axes[0].plot(range(sample_n), targets[idx], 'b-', alpha=0.7, label='Actual', linewidth=0.8)
            axes[0].plot(range(sample_n), preds[idx], 'r-', alpha=0.7, label='Predicted', linewidth=0.8)
            axes[0].set_title('Actual vs Predicted (time series)')
            axes[0].set_ylabel('Rainfall (mm)')
            axes[0].legend()

            # 2. Scatter plot
            axes[1].scatter(targets, preds, alpha=0.3, s=5)
            max_val = max(targets.max(), preds.max()) * 1.1
            axes[1].plot([0, max_val], [0, max_val], 'r--', label='Perfect')
            axes[1].set_xlabel('Actual (mm)')
            axes[1].set_ylabel('Predicted (mm)')
            axes[1].set_title('Scatter: Actual vs Predicted')
            axes[1].legend()

            # 3. MAE 分桶
            if bucket_stats:
                labels = [b['label'] for b in bucket_stats]
                maes = [b['mae'] for b in bucket_stats]
                counts = [b['count'] for b in bucket_stats]
                bars = axes[2].bar(labels, maes, color=['green', 'skyblue', 'orange', 'red'][:len(labels)])
                for bar, count in zip(bars, counts):
                    axes[2].text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.01,
                                f'n={count}', ha='center', va='bottom', fontsize=9)
                axes[2].set_title('MAE by Rainfall Intensity')
                axes[2].set_ylabel('MAE (mm)')

            plt.tight_layout()
            plot_path = RESULTS_DIR / "backtest_comparison.png"
            plt.savefig(plot_path, dpi=150)
            logger.info(f"\n📊 Plot saved: {plot_path}")
        except ImportError:
            logger.warning("matplotlib not available, skipping plots")

    finally:
        os.chdir(old_cwd)
        if processed_data_link.is_symlink():
            processed_data_link.unlink()
        if original_processed and original_processed.exists():
            original_processed.rename(processed_data_link)


if __name__ == "__main__":
    main()
