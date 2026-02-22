"""
模型诊断脚本：分析模型输出的分布，验证评估器是否正确。
用法: WORK_DIR=$PWD python3 diagnose_model.py

核心目的：搞清楚模型到底在输出什么值，然后判断"是否降雨"的评估逻辑对不对。
"""
import os
import sys
import json
import logging
import numpy as np
import torch

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

WORK_DIR = os.environ.get("WORK_DIR", os.path.dirname(os.path.abspath(__file__)))
os.chdir(WORK_DIR)

# 复用训练代码的 dataloader
sys.path.insert(0, WORK_DIR)
from weather_dataset import get_dataloaders
from weather_fusion_model import WeatherFusionNet


def diagnose():
    MODEL_PATH = os.path.join(WORK_DIR, "weather_fusion_model.pth")
    CSV_PATH = os.path.join(WORK_DIR, "real_sensor_data.csv")
    SAT_DIR = os.path.join(WORK_DIR, "processed_data")

    if not os.path.exists(MODEL_PATH):
        logger.error(f"❌ 模型不存在: {MODEL_PATH}")
        return

    # 加载模型
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = WeatherFusionNet(sat_channels=3, sensor_features=7, coord_dim=2, prediction_dim=1)
    model.load_state_dict(torch.load(MODEL_PATH, map_location=device, weights_only=True))
    model.to(device)
    model.eval()
    logger.info(f"✅ 模型已加载: {MODEL_PATH}")
    logger.info(f"   设备: {device}")

    # 加载数据（用验证集）
    _, val_loader = get_dataloaders(CSV_PATH, SAT_DIR, batch_size=32)
    logger.info(f"✅ 验证集: {len(val_loader)} batches")

    # 收集所有预测值和真实值
    all_preds = []
    all_targets = []

    with torch.no_grad():
        for sat, sensor, coord, target in val_loader:
            sat, sensor, coord, target = (
                sat.to(device), sensor.to(device),
                coord.to(device), target.to(device)
            )
            outputs = model(sat, sensor, coord)
            all_preds.append(outputs.cpu().numpy().flatten())
            all_targets.append(target.cpu().numpy().flatten())

    preds = np.concatenate(all_preds)
    targets = np.concatenate(all_targets)

    logger.info(f"\n{'='*60}")
    logger.info(f"📊 模型输出分布 (共 {len(preds)} 个样本)")
    logger.info(f"{'='*60}")

    # 1. 基本统计
    logger.info(f"\n--- 模型预测值 (outputs) ---")
    logger.info(f"  Min:    {preds.min():.4f}")
    logger.info(f"  Max:    {preds.max():.4f}")
    logger.info(f"  Mean:   {preds.mean():.4f}")
    logger.info(f"  Median: {np.median(preds):.4f}")
    logger.info(f"  Std:    {preds.std():.4f}")

    logger.info(f"\n--- 真实值 (targets) ---")
    logger.info(f"  Min:    {targets.min():.4f}")
    logger.info(f"  Max:    {targets.max():.4f}")
    logger.info(f"  Mean:   {targets.mean():.4f}")
    logger.info(f"  Median: {np.median(targets):.4f}")
    logger.info(f"  Std:    {targets.std():.4f}")

    # 2. 降雨分布
    rain_threshold = 0.1
    actual_rain_count = (targets > rain_threshold).sum()
    actual_dry_count = (targets <= rain_threshold).sum()
    rain_ratio = actual_rain_count / len(targets)

    logger.info(f"\n--- 类别分布 (阈值={rain_threshold}mm) ---")
    logger.info(f"  有雨样本: {actual_rain_count} ({rain_ratio*100:.1f}%)")
    logger.info(f"  无雨样本: {actual_dry_count} ({(1-rain_ratio)*100:.1f}%)")

    # 3. 模型输出 vs 阈值 — 这就是当前评估器在做的事
    pred_rain = preds > rain_threshold
    actual_rain = targets > rain_threshold

    tp = ((pred_rain == True) & (actual_rain == True)).sum()
    fp = ((pred_rain == True) & (actual_rain == False)).sum()
    tn = ((pred_rain == False) & (actual_rain == False)).sum()
    fn = ((pred_rain == False) & (actual_rain == True)).sum()

    current_acc = (tp + tn) / len(preds)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    logger.info(f"\n{'='*60}")
    logger.info(f"📐 当前评估器结果 (阈值={rain_threshold}mm)")
    logger.info(f"{'='*60}")
    logger.info(f"  混淆矩阵:")
    logger.info(f"              预测有雨  预测无雨")
    logger.info(f"  实际有雨     {tp:>7d}   {fn:>7d}")
    logger.info(f"  实际无雨     {fp:>7d}   {tn:>7d}")
    logger.info(f"")
    logger.info(f"  Accuracy:  {current_acc*100:.2f}%")
    logger.info(f"  Precision: {precision*100:.2f}% (预测有雨时，真的有雨的比例)")
    logger.info(f"  Recall:    {recall*100:.2f}% (实际有雨时，被模型找到的比例)")
    logger.info(f"  F1 Score:  {f1*100:.2f}%")

    # 4. 预测值 > 0.1 的比例 — 检验我们的假设
    pred_above_threshold = (preds > rain_threshold).sum() / len(preds)
    logger.info(f"\n--- 假设验证 ---")
    logger.info(f"  模型输出 > 0.1 的比例: {pred_above_threshold*100:.1f}%")
    logger.info(f"  如果接近 100%，说明评估器 bug 已确认 ✅")
    logger.info(f"  如果接近实际下雨比例 ({rain_ratio*100:.1f}%)，说明模型已学到有意义的信号")

    # 5. 尝试不同阈值，找最优
    logger.info(f"\n{'='*60}")
    logger.info(f"🔍 最优阈值搜索")
    logger.info(f"{'='*60}")
    logger.info(f"  {'阈值':>8s}  {'Acc':>8s}  {'Prec':>8s}  {'Recall':>8s}  {'F1':>8s}")

    best_f1 = 0
    best_threshold = 0

    for t in np.arange(preds.min() - 0.1, preds.max() + 0.1, 0.05):
        p_rain = preds > t
        a_rain = targets > rain_threshold  # 实际降雨始终用 0.1mm

        t_tp = ((p_rain) & (a_rain)).sum()
        t_fp = ((p_rain) & (~a_rain)).sum()
        t_tn = ((~p_rain) & (~a_rain)).sum()
        t_fn = ((~p_rain) & (a_rain)).sum()

        t_acc = (t_tp + t_tn) / len(preds)
        t_prec = t_tp / (t_tp + t_fp) if (t_tp + t_fp) > 0 else 0
        t_rec = t_tp / (t_tp + t_fn) if (t_tp + t_fn) > 0 else 0
        t_f1 = 2 * t_prec * t_rec / (t_prec + t_rec) if (t_prec + t_rec) > 0 else 0

        if t_f1 > best_f1:
            best_f1 = t_f1
            best_threshold = t

        # 只打印有意义的范围
        if t_acc > 0.5 or abs(t - rain_threshold) < 0.01:
            logger.info(f"  {t:>8.3f}  {t_acc*100:>7.1f}%  {t_prec*100:>7.1f}%  {t_rec*100:>7.1f}%  {t_f1*100:>7.1f}%")

    logger.info(f"\n  ✅ 最优阈值: {best_threshold:.3f} (F1={best_f1*100:.2f}%)")

    # 6. 结论
    logger.info(f"\n{'='*60}")
    logger.info(f"📋 诊断结论")
    logger.info(f"{'='*60}")

    if pred_above_threshold > 0.9:
        logger.info(f"  ❌ 评估器 BUG 已确认：模型输出 {pred_above_threshold*100:.0f}% > 0.1")
        logger.info(f"     当前 5% 准确率是因为 pred_rain 永远=1，与实际无雨冲突")
        logger.info(f"     修复方法: 使用最优阈值 {best_threshold:.3f} 或改用分类模型")
    elif best_f1 > 0.3:
        logger.info(f"  ⚠️ 模型有一定判别能力，最优 F1={best_f1*100:.1f}%")
        logger.info(f"     建议使用阈值 {best_threshold:.3f} 替换当前 0.1")
    else:
        logger.info(f"  ❌ 模型对降雨几乎没有判别能力 (best F1={best_f1*100:.1f}%)")
        logger.info(f"     需要改用分类模型 (BCELoss + Sigmoid)")

    # 保存结果
    results = {
        "pred_stats": {"min": float(preds.min()), "max": float(preds.max()),
                       "mean": float(preds.mean()), "std": float(preds.std())},
        "target_stats": {"min": float(targets.min()), "max": float(targets.max()),
                         "mean": float(targets.mean()), "std": float(targets.std())},
        "rain_ratio": float(rain_ratio),
        "current_accuracy": float(current_acc),
        "confusion_matrix": {"tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn)},
        "best_threshold": float(best_threshold),
        "best_f1": float(best_f1),
    }
    out_path = os.path.join(WORK_DIR, "diagnosis_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"\n  💾 结果保存到: {out_path}")


if __name__ == "__main__":
    diagnose()
