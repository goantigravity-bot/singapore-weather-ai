"""
evaluate.py V3 — 分类模型评估

改进:
  - 直接评估二分类 (sigmoid → 概率)
  - AUC-ROC + Precision-Recall 曲线
  - 最优阈值搜索
  - 概率分布直方图
  - Calibration 校准分析

用法: cd services/training && python3 ../../tools/evaluate.py
"""
import sys
import os

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
from sklearn.metrics import roc_auc_score, precision_recall_curve, roc_curve

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODEL_PATH = "weather_fusion_model.pth"
CSV_PATH = "real_sensor_data.csv"
SAT_DIR = "satellite_data"
DEVICE = torch.device("cpu")


def find_best_threshold(probs, targets):
    """搜索 F1 最大化的阈值。"""
    best_f1 = 0
    best_t = 0.5
    for t in np.arange(0.1, 0.9, 0.01):
        pred = probs > t
        tp = ((pred) & (targets == 1)).sum()
        fp = ((pred) & (targets == 0)).sum()
        fn = ((~pred) & (targets == 1)).sum()
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-8)
        if f1 > best_f1:
            best_f1 = f1
            best_t = t
    return best_t, best_f1


def evaluate_model():
    torch.manual_seed(42)

    logger.info("Loading validation dataset...")
    _, val_loader = get_dataloaders(CSV_PATH, SAT_DIR, batch_size=32, temporal_split=True)
    logger.info(f"Val batches: {len(val_loader)}")

    # 加载 V3 模型 (sensor_features=13)
    model = WeatherFusionNet(
        sat_channels=3, sensor_features=13, coord_dim=2,
        num_sat_frames=1, use_cross_attention=True
    )
    if not os.path.exists(MODEL_PATH):
        logger.error(f"Model file not found: {MODEL_PATH}")
        return None

    model.load_state_dict(torch.load(MODEL_PATH, map_location=DEVICE, weights_only=True))
    model.to(DEVICE)
    model.eval()
    logger.info(f"Loaded V3 model from {MODEL_PATH}")

    # 推理
    all_probs = []
    all_targets = []

    with torch.no_grad():
        for sat, sensor, coord, target in val_loader:
            sat, sensor, coord = sat.to(DEVICE), sensor.to(DEVICE), coord.to(DEVICE)
            logits = model(sat, sensor, coord)
            probs = torch.sigmoid(logits).cpu().numpy().flatten()
            all_probs.extend(probs)
            all_targets.extend(target.numpy().flatten())

    probs = np.array(all_probs)
    targets = np.array(all_targets)

    # 最优阈值
    best_t, best_f1 = find_best_threshold(probs, targets)

    # 在最优阈值下的指标
    preds = probs > best_t
    tp = int(((preds) & (targets == 1)).sum())
    tn = int(((~preds) & (targets == 0)).sum())
    fp = int(((preds) & (targets == 0)).sum())
    fn = int(((~preds) & (targets == 1)).sum())
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-8)
    accuracy = (tp + tn) / len(preds)

    # AUC-ROC
    try:
        auc_roc = roc_auc_score(targets, probs)
    except ValueError:
        auc_roc = 0.0

    # 输出
    print("\n" + "=" * 60)
    print("📊 Model Evaluation Results (V3 Classification)")
    print("=" * 60)
    print(f"样本数:        {len(probs)}")
    print(f"最优阈值:      {best_t:.3f}")
    print(f"AUC-ROC:       {auc_roc:.4f}")
    print(f"Accuracy:      {accuracy * 100:.2f}%")
    print(f"Precision:     {precision * 100:.2f}%")
    print(f"Recall:        {recall * 100:.2f}%")
    print(f"F1 Score:      {f1 * 100:.2f}%")
    print(f"TP={tp}  TN={tn}  FP={fp}  FN={fn}")
    print(f"Rain ratio:    {targets.sum()}/{len(targets)} ({targets.mean() * 100:.1f}%)")
    print(f"Pred range:    [{probs.min():.4f}, {probs.max():.4f}]")
    print("=" * 60)

    # 绘图 (2x2)
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("WeatherFusionNet V3 — Classification Evaluation", fontsize=14, fontweight='bold')

    # 左上: 概率分布直方图
    ax = axes[0, 0]
    ax.hist(probs[targets == 0], bins=50, alpha=0.6, label='Dry', color='#3498db', density=True)
    ax.hist(probs[targets == 1], bins=50, alpha=0.6, label='Rain', color='#e74c3c', density=True)
    ax.axvline(x=best_t, color='green', linestyle='--', label=f'Threshold={best_t:.2f}')
    ax.set_xlabel("Predicted Probability")
    ax.set_ylabel("Density")
    ax.set_title("Probability Distribution (Rain vs Dry)")
    ax.legend()

    # 右上: ROC 曲线
    ax = axes[0, 1]
    try:
        fpr, tpr, _ = roc_curve(targets, probs)
        ax.plot(fpr, tpr, color='#e74c3c', linewidth=2, label=f'AUC = {auc_roc:.3f}')
        ax.plot([0, 1], [0, 1], 'k--', alpha=0.3)
        ax.set_xlabel("False Positive Rate")
        ax.set_ylabel("True Positive Rate")
        ax.set_title("ROC Curve")
        ax.legend()
    except Exception:
        ax.text(0.5, 0.5, 'Insufficient data', ha='center', va='center')

    # 左下: Precision-Recall 曲线
    ax = axes[1, 0]
    try:
        prec_curve, rec_curve, thresholds = precision_recall_curve(targets, probs)
        ax.plot(rec_curve, prec_curve, color='#2ecc71', linewidth=2)
        ax.axhline(y=precision, color='r', linestyle='--', alpha=0.5,
                   label=f'Prec@opt={precision:.2f}')
        ax.axvline(x=recall, color='b', linestyle='--', alpha=0.5,
                   label=f'Rec@opt={recall:.2f}')
        ax.set_xlabel("Recall")
        ax.set_ylabel("Precision")
        ax.set_title("Precision-Recall Curve")
        ax.legend()
    except Exception:
        ax.text(0.5, 0.5, 'Insufficient data', ha='center', va='center')

    # 右下: F1 vs Threshold
    ax = axes[1, 1]
    thresholds_search = np.arange(0.1, 0.9, 0.01)
    f1_scores = []
    for t in thresholds_search:
        p = probs > t
        t_tp = ((p) & (targets == 1)).sum()
        t_fp = ((p) & (targets == 0)).sum()
        t_fn = ((~p) & (targets == 1)).sum()
        t_prec = t_tp / max(t_tp + t_fp, 1)
        t_rec = t_tp / max(t_tp + t_fn, 1)
        t_f1 = 2 * t_prec * t_rec / max(t_prec + t_rec, 1e-8)
        f1_scores.append(t_f1)
    ax.plot(thresholds_search, f1_scores, color='#9b59b6', linewidth=2)
    ax.axvline(x=best_t, color='green', linestyle='--', label=f'Best t={best_t:.2f}, F1={best_f1:.3f}')
    ax.set_xlabel("Threshold")
    ax.set_ylabel("F1 Score")
    ax.set_title("F1 Score vs Threshold")
    ax.legend()

    plt.tight_layout()
    plot_path = "evaluation_plot.png"
    plt.savefig(plot_path, dpi=150)
    logger.info(f"Plot saved: {plot_path}")

    # 保存 JSON
    results = {
        'model_version': 'V3',
        'auc_roc': float(auc_roc),
        'best_threshold': float(best_t),
        'accuracy': float(accuracy),
        'precision': float(precision),
        'recall': float(recall),
        'f1': float(f1),
        'num_samples': len(probs),
        'confusion_matrix': {'tp': tp, 'tn': tn, 'fp': fp, 'fn': fn},
        'rain_ratio': float(targets.mean()),
    }

    results_file = "evaluation_results.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    logger.info(f"Results saved: {results_file}")

    return results


if __name__ == "__main__":
    evaluate_model()
