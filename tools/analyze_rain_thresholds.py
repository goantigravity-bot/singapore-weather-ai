"""轻量版：分析不同降雨阈值下 4 个候选基站的样本分布"""
import csv
import os
from collections import defaultdict

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "services", "training", "real_sensor_data.csv")
STATIONS = ["S66", "S60", "S24", "S44"]
THRESHOLDS = [1.0, 2.0, 3.0, 4.0, 5.0, 8.0, 10.0]

# 按基站分组读取 rainfall 值
station_data = defaultdict(list)

with open(CSV_PATH, "r") as f:
    reader = csv.DictReader(f)
    for row in reader:
        sid = row["sensor_id"]
        if sid in STATIONS:
            try:
                rain = float(row["rainfall"])
            except (ValueError, KeyError):
                continue
            station_data[sid].append(rain)

print("=" * 80)
print("降雨阈值 vs 样本量分析报告")
print(f"数据跨度: 2024-02-15 ~ 2026-02-04 (~23 months)")
print("=" * 80)

for sid in STATIONS:
    data = station_data[sid]
    total = len(data)
    dry_0 = sum(1 for r in data if r == 0.0)

    print(f"\n--- {sid} | total={total} rows ---")
    print(f"{'Threshold':>10} {'Rain>=T':>8} {'Rain%':>7} {'1:3 Total':>10} {'Est.Events':>11}")

    for t in THRESHOLDS:
        n_rain = sum(1 for r in data if r >= t)
        pct = n_rain / total * 100 if total > 0 else 0
        # 粗略估算独立事件数：假设每场雨平均持续 3 个 10 分钟时段
        est_events = max(1, n_rain // 3) if n_rain > 0 else 0
        total_13 = n_rain + n_rain * 3
        print(f"{t:>8.1f}mm {n_rain:>8} {pct:>6.1f}% {total_13:>10} {est_events:>11}")

# 汇总
print("\n" + "=" * 80)
print("汇总: 各阈值下 4 站雨样本数")
print("=" * 80)
header = f"{'Threshold':>10}"
for sid in STATIONS:
    header += f" {sid:>8}"
header += f" {'TOTAL':>8} {'1:3 Total':>10}"
print(header)

for t in THRESHOLDS:
    line = f"{t:>8.1f}mm"
    row_total = 0
    for sid in STATIONS:
        n = sum(1 for r in station_data[sid] if r >= t)
        line += f" {n:>8}"
        row_total += n
    line += f" {row_total:>8} {row_total * 4:>10}"
    print(line)

print("\n💡 建议: 选择 TOTAL >= 500 且单站 >= 100 的阈值")
