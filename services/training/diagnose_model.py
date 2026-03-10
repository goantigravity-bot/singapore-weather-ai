"""
模型诊断脚本：分析二分类模型输出的分布，验证降雨预测能力。
用法: WORK_DIR=$PWD python3 diagnose_model.py

核心目的：模型输出 logits → sigmoid 转概率，评估二分类性能。
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

    # 加载模型（支持旧 state_dict 和新 dict 格式）
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    checkpoint = torch.load(MODEL_PATH, map_location=device, weights_only=False)
    if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
        num_sat_frames = checkpoint.get('num_sat_frames', 1)
        state_dict = checkpoint['model_state_dict']
    else:
        num_sat_frames = 1
        state_dict = checkpoint

    model = WeatherFusionNet(
        sat_channels=3, sensor_features=13, coord_dim=2,
        num_sat_frames=num_sat_frames, use_cross_attention=True
    )
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    logger.info(f"✅ 模型已加载: {MODEL_PATH} (num_sat_frames={num_sat_frames})")
    logger.info(f"   设备: {device}")

    # 加载数据（用验证集）
    _, val_loader = get_dataloaders(CSV_PATH, SAT_DIR, batch_size=32, num_sat_frames=num_sat_frames)
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
            logits = model(sat, sensor, coord)
            # 模型输出 logits，转概率用于评估
            probs = torch.sigmoid(logits)
            all_preds.append(probs.cpu().numpy().flatten())
            all_targets.append(target.cpu().numpy().flatten())

    preds = np.concatenate(all_preds)
    targets = np.concatenate(all_targets)

    logger.info(f"\n{'='*60}")
    logger.info(f"📊 模型输出概率分布 (共 {len(preds)} 个样本)")
    logger.info(f"{'='*60}")

    # 1. 基本统计
    logger.info(f"\n--- 模型预测概率 (sigmoid outputs) ---")
    logger.info(f"  Min:    {preds.min():.4f}")
    logger.info(f"  Max:    {preds.max():.4f}")
    logger.info(f"  Mean:   {preds.mean():.4f}")
    logger.info(f"  Median: {np.median(preds):.4f}")
    logger.info(f"  Std:    {preds.std():.4f}")

    logger.info(f"\n--- 真实标签 (targets: 0=无雨, 1=有雨) ---")
    logger.info(f"  Min:    {targets.min():.4f}")
    logger.info(f"  Max:    {targets.max():.4f}")
    logger.info(f"  Mean:   {targets.mean():.4f}")
    logger.info(f"  Median: {np.median(targets):.4f}")
    logger.info(f"  Std:    {targets.std():.4f}")

    # 2. 标签分布（已二值化）
    actual_rain_count = (targets == 1).sum()
    actual_dry_count = (targets == 0).sum()
    rain_ratio = actual_rain_count / len(targets)

    logger.info(f"\n--- 类别分布 ---")
    logger.info(f"  有雨样本 (target=1): {actual_rain_count} ({rain_ratio*100:.1f}%)")
    logger.info(f"  无雨样本 (target=0): {actual_dry_count} ({(1-rain_ratio)*100:.1f}%)")

    # 3. 二分类评估（概率 > 0.5 判定有雨）
    THRESHOLD = 0.5
    pred_rain = preds > THRESHOLD
    actual_rain = targets == 1

    tp = ((pred_rain == True) & (actual_rain == True)).sum()
    fp = ((pred_rain == True) & (actual_rain == False)).sum()
    tn = ((pred_rain == False) & (actual_rain == False)).sum()
    fn = ((pred_rain == False) & (actual_rain == True)).sum()

    current_acc = (tp + tn) / len(preds)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    logger.info(f"\n{'='*60}")
    logger.info(f"📐 二分类评估结果 (阈值={THRESHOLD})")
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

    # 4. 概率分布诊断
    pred_above_threshold = (preds > THRESHOLD).sum() / len(preds)
    logger.info(f"\n--- 概率分布诊断 ---")
    logger.info(f"  模型输出 > {THRESHOLD} 的比例: {pred_above_threshold*100:.1f}%")
    logger.info(f"  实际有雨比例: {rain_ratio*100:.1f}%")
    logger.info(f"  如果两者接近，说明模型学到了有意义的分类能力")

    # 5. 尝试不同阈值，找最优
    logger.info(f"\n{'='*60}")
    logger.info(f"🔍 最优阈值搜索")
    logger.info(f"{'='*60}")
    logger.info(f"  {'阈值':>8s}  {'Acc':>8s}  {'Prec':>8s}  {'Recall':>8s}  {'F1':>8s}")

    best_f1 = 0
    best_threshold = 0

    for t in np.arange(0.05, 0.95, 0.05):
        p_rain = preds > t
        a_rain = targets == 1  # 二值标签

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
        if t_acc > 0.5 or abs(t - rain_ratio) < 0.01:
            logger.info(f"  {t:>8.3f}  {t_acc*100:>7.1f}%  {t_prec*100:>7.1f}%  {t_rec*100:>7.1f}%  {t_f1*100:>7.1f}%")

    logger.info(f"\n  ✅ 最优阈值: {best_threshold:.3f} (F1={best_f1*100:.2f}%)")

    # 6. 结论
    logger.info(f"\n{'='*60}")
    logger.info(f"📋 诊断结论")
    logger.info(f"{'='*60}")

    if best_f1 > 0.5:
        logger.info(f"  ✅ 模型具有良好的降雨判别能力 (best F1={best_f1*100:.1f}%)")
        logger.info(f"     最优阈值: {best_threshold:.3f}")
    elif best_f1 > 0.3:
        logger.info(f"  ⚠️ 模型有一定判别能力，最优 F1={best_f1*100:.1f}%")
        logger.info(f"     建议使用阈值 {best_threshold:.3f}")
    else:
        logger.info(f"  ❌ 模型降雨判别能力不足 (best F1={best_f1*100:.1f}%)")
        logger.info(f"     建议增加训练数据或调整模型结构")

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
