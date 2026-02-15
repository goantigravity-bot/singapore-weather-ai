#!/usr/bin/env python3
"""
wind_correlation_analysis.py
分析风速/风向与 PSI(PM2.5) 和降雨量的相关性
数据来源：S3 govdata/ 目录下的 JSON 文件
"""

import json
import subprocess
import logging
import math
from datetime import datetime, timedelta
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

S3_BUCKET = "weather-ai-models-de08370c"
GOVDATA_PREFIX = "govdata"
OUTPUT_DIR = "/tmp/wind_analysis"

def s3_download_json(key):
    """从 S3 下载 JSON 文件"""
    try:
        result = subprocess.run(
            ["aws", "s3", "cp", f"s3://{S3_BUCKET}/{key}", "-",
             "--profile", "personal", "--region", "ap-southeast-1"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except Exception as e:
        logger.debug(f"Failed to download {key}: {e}")
    return None


def extract_daily_avg_v1(data, value_key="value"):
    """从 v1 API JSON 中提取所有站点的日均值"""
    if not data:
        return None
    items = data.get("items", [])
    values = []
    for item in items:
        for reading in item.get("readings", []):
            val = reading.get(value_key)
            if val is not None and isinstance(val, (int, float)):
                values.append(val)
    return np.mean(values) if values else None


def extract_pm25_daily_avg(data):
    """从 PM2.5 JSON 中提取日均值"""
    if not data:
        return None
    items = data.get("items", [])
    values = []
    for item in items:
        readings = item.get("readings", {})
        # PM2.5 数据结构不同，按区域存储
        for region, val in readings.items():
            if isinstance(val, (int, float)):
                values.append(val)
            elif isinstance(val, dict):
                # 尝试提取 pm25_one_hourly
                for sub_key, sub_val in val.items():
                    if isinstance(sub_val, (int, float)):
                        values.append(sub_val)
    return np.mean(values) if values else None


def extract_wind_daily_v2(data):
    """从 v2 API JSON 中提取所有站点的日均值"""
    if not data:
        return None
    d = data.get("data", {})
    readings = d.get("readings", [])
    values = []
    for r in readings:
        for item in r.get("data", []):
            val = item.get("value")
            if val is not None and isinstance(val, (int, float)):
                values.append(val)
    return np.mean(values) if values else None


def classify_wind_direction(degrees):
    """将角度转换为 8 方位"""
    if degrees is None:
        return None
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int((degrees + 22.5) / 45) % 8
    return dirs[idx]


def extract_wind_direction_distribution(data):
    """从风向数据中提取方向分布"""
    if not data:
        return None, None
    d = data.get("data", {})
    readings = d.get("readings", [])
    directions = []
    for r in readings:
        for item in r.get("data", []):
            val = item.get("value")
            if val is not None:
                directions.append(val)
    if not directions:
        return None, None
    avg_dir = np.mean(directions)
    # 主导风向
    dominant = classify_wind_direction(avg_dir)
    return avg_dir, dominant


def main():
    import os
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    start = datetime(2025, 10, 1)
    end = datetime(2026, 2, 15)

    records = []
    current = start

    logger.info(f"Analyzing {(end - start).days} days of data...")

    while current <= end:
        date_str = current.strftime("%Y-%m-%d")

        # 下载各类数据
        rainfall = s3_download_json(f"{GOVDATA_PREFIX}/rainfall_{date_str}.json")
        pm25 = s3_download_json(f"{GOVDATA_PREFIX}/pm25_{date_str}.json")
        wind_speed = s3_download_json(f"{GOVDATA_PREFIX}/wind-speed_{date_str}.json")
        wind_dir = s3_download_json(f"{GOVDATA_PREFIX}/wind-direction_{date_str}.json")

        # 提取日均值
        rain_avg = extract_daily_avg_v1(rainfall)
        pm25_avg = extract_pm25_daily_avg(pm25)
        ws_avg = extract_wind_daily_v2(wind_speed)
        wd_avg, wd_dominant = extract_wind_direction_distribution(wind_dir)

        if all(v is not None for v in [rain_avg, pm25_avg, ws_avg, wd_avg]):
            records.append({
                "date": date_str,
                "rainfall": rain_avg,
                "pm25": pm25_avg,
                "wind_speed": ws_avg,
                "wind_direction": wd_avg,
                "wind_dominant": wd_dominant,
            })
            logger.info(f"  {date_str}: rain={rain_avg:.2f} pm25={pm25_avg:.1f} ws={ws_avg:.1f}kn wd={wd_avg:.0f}°({wd_dominant})")
        else:
            logger.warning(f"  {date_str}: incomplete data (rain={rain_avg}, pm25={pm25_avg}, ws={ws_avg}, wd={wd_avg})")

        current += timedelta(days=1)

    if len(records) < 10:
        logger.error(f"Only {len(records)} complete records, not enough for analysis")
        return

    logger.info(f"\n✅ {len(records)} days of complete data collected. Generating charts...")

    # 转为 numpy 数组
    dates = [r["date"] for r in records]
    rainfall = np.array([r["rainfall"] for r in records])
    pm25 = np.array([r["pm25"] for r in records])
    wind_speed = np.array([r["wind_speed"] for r in records])
    wind_dir = np.array([r["wind_direction"] for r in records])
    dominants = [r["wind_dominant"] for r in records]

    # --- 图1: 风向 vs PM2.5 (按风向分组的箱线图) ---
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Wind vs Rainfall & PSI Correlation Analysis\n(Singapore, Oct 2025 - Feb 2026)", fontsize=14, fontweight='bold')

    # 1a: 风向 vs PM2.5 箱线图
    ax = axes[0, 0]
    dir_groups = defaultdict(list)
    for i, d in enumerate(dominants):
        dir_groups[d].append(pm25[i])
    dir_order = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    box_data = [dir_groups.get(d, []) for d in dir_order]
    box_labels = [f"{d}\n(n={len(dir_groups.get(d, []))})" for d in dir_order]
    bp = ax.boxplot(box_data, labels=box_labels, patch_artist=True)
    # 南/西南风染红色（烟雾高风险方向）
    colors = ['#3498db', '#3498db', '#3498db', '#e74c3c', '#e74c3c', '#e74c3c', '#3498db', '#3498db']
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    ax.set_ylabel("PM2.5 (μg/m³)")
    ax.set_title("Wind Direction vs PM2.5")
    ax.axhline(y=55, color='r', linestyle='--', alpha=0.5, label='Unhealthy threshold')
    ax.legend(fontsize=8)

    # 1b: 风向 vs 降雨箱线图
    ax = axes[0, 1]
    rain_groups = defaultdict(list)
    for i, d in enumerate(dominants):
        rain_groups[d].append(rainfall[i])
    box_data = [rain_groups.get(d, []) for d in dir_order]
    box_labels = [f"{d}\n(n={len(rain_groups.get(d, []))})" for d in dir_order]
    bp = ax.boxplot(box_data, labels=box_labels, patch_artist=True)
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    ax.set_ylabel("Rainfall (mm)")
    ax.set_title("Wind Direction vs Rainfall")

    # 2a: 风速 vs 降雨散点图
    ax = axes[1, 0]
    ax.scatter(wind_speed, rainfall, alpha=0.5, s=30, c='#2ecc71')
    # 拟合线
    if len(wind_speed) > 2:
        z = np.polyfit(wind_speed, rainfall, 1)
        p = np.poly1d(z)
        x_line = np.linspace(wind_speed.min(), wind_speed.max(), 100)
        ax.plot(x_line, p(x_line), "r--", alpha=0.7, label=f"trend: {z[0]:.3f}x + {z[1]:.2f}")
    corr = np.corrcoef(wind_speed, rainfall)[0, 1]
    ax.set_xlabel("Wind Speed (knots)")
    ax.set_ylabel("Rainfall (mm)")
    ax.set_title(f"Wind Speed vs Rainfall (r = {corr:.3f})")
    ax.legend(fontsize=8)

    # 2b: 风速 vs PM2.5 散点图
    ax = axes[1, 1]
    ax.scatter(wind_speed, pm25, alpha=0.5, s=30, c='#e67e22')
    if len(wind_speed) > 2:
        z = np.polyfit(wind_speed, pm25, 1)
        p = np.poly1d(z)
        x_line = np.linspace(wind_speed.min(), wind_speed.max(), 100)
        ax.plot(x_line, p(x_line), "r--", alpha=0.7, label=f"trend: {z[0]:.2f}x + {z[1]:.1f}")
    corr = np.corrcoef(wind_speed, pm25)[0, 1]
    ax.set_xlabel("Wind Speed (knots)")
    ax.set_ylabel("PM2.5 (μg/m³)")
    ax.set_title(f"Wind Speed vs PM2.5 (r = {corr:.3f})")
    ax.legend(fontsize=8)

    plt.tight_layout()
    chart_path = f"{OUTPUT_DIR}/wind_correlation_analysis.png"
    plt.savefig(chart_path, dpi=150, bbox_inches='tight')
    logger.info(f"📊 Chart saved to {chart_path}")

    # --- 统计摘要 ---
    print("\n" + "=" * 60)
    print("📊 CORRELATION SUMMARY")
    print("=" * 60)

    r_ws_rain = np.corrcoef(wind_speed, rainfall)[0, 1]
    r_ws_pm25 = np.corrcoef(wind_speed, pm25)[0, 1]
    print(f"\n  Wind Speed ↔ Rainfall:  r = {r_ws_rain:+.3f}")
    print(f"  Wind Speed ↔ PM2.5:    r = {r_ws_pm25:+.3f}")

    # 风向分组的均值
    print(f"\n  PM2.5 by Wind Direction:")
    for d in dir_order:
        vals = dir_groups.get(d, [])
        if vals:
            print(f"    {d:2s}: mean={np.mean(vals):.1f}, max={np.max(vals):.1f}, n={len(vals)}")

    print(f"\n  Rainfall by Wind Direction:")
    for d in dir_order:
        vals = rain_groups.get(d, [])
        if vals:
            print(f"    {d:2s}: mean={np.mean(vals):.2f}, max={np.max(vals):.2f}, n={len(vals)}")

    print(f"\n  Total days analyzed: {len(records)}")
    print(f"  Date range: {dates[0]} → {dates[-1]}")
    print("=" * 60)


if __name__ == "__main__":
    main()
