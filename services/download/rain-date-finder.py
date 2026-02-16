"""
rain-date-finder.py — 从 data.gov.sg 拉取历史降雨数据，识别雨天时间窗口

输出: rain-dates-{year}.csv，列: date,start_sgt,end_sgt,total_rainfall_mm,rain_hours

用法: python3 rain-date-finder.py --start 2024-02-15 --end 2026-02-15 --output-dir ./processed
"""

import argparse
import csv
import json
import logging
import os
import time
from datetime import datetime, timedelta
from urllib.request import urlopen
from urllib.error import URLError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

API_URL = "https://api.data.gov.sg/v1/environment/rainfall"
# 判定"有雨"的阈值: 任意站点 5 分钟累积 > 0
RAIN_THRESHOLD = 0.0


def fetch_rainfall_for_date(date_str: str, max_retries: int = 3) -> list[dict]:
    """拉取某天所有 5 分钟粒度的降雨数据"""
    url = f"{API_URL}?date={date_str}"
    for attempt in range(max_retries):
        try:
            with urlopen(url, timeout=30) as resp:
                data = json.loads(resp.read())
            return data.get("items", [])
        except (URLError, json.JSONDecodeError, TimeoutError) as e:
            logger.warning(f"Retry {attempt+1}/{max_retries} for {date_str}: {e}")
            time.sleep(2 ** attempt)
    logger.error(f"Failed to fetch {date_str} after {max_retries} retries")
    return []


def find_rain_windows(items: list[dict], buffer_hours: int = 1) -> list[dict]:
    """
    从 5 分钟粒度的降雨 items 中识别连续雨段，
    每段前后各扩展 buffer_hours 小时

    返回合并后的雨窗口列表，每个窗口含 start/end/total_rainfall
    """
    # 找出所有有雨的时间戳（只要有一个站降雨 > 0 就算）
    rain_timestamps = []
    for item in items:
        ts_str = item.get("timestamp", "")
        readings = item.get("readings", [])
        total = sum(r.get("value", 0) for r in readings)
        if total > RAIN_THRESHOLD:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                rain_timestamps.append((ts, total))
            except (ValueError, AttributeError):
                continue

    if not rain_timestamps:
        return []

    rain_timestamps.sort(key=lambda x: x[0])

    # 合并相邻的雨窗口（加上 buffer 后有重叠就合并）
    buf = timedelta(hours=buffer_hours)
    windows = []
    cur_start = rain_timestamps[0][0] - buf
    cur_end = rain_timestamps[0][0] + buf
    cur_total = rain_timestamps[0][1]

    for ts, total in rain_timestamps[1:]:
        extended_start = ts - buf
        if extended_start <= cur_end:
            # 重叠，扩展当前窗口
            cur_end = max(cur_end, ts + buf)
            cur_total += total
        else:
            # 新窗口
            windows.append({
                "start": cur_start,
                "end": cur_end,
                "total_rainfall": round(cur_total, 2),
            })
            cur_start = extended_start
            cur_end = ts + buf
            cur_total = total

    windows.append({
        "start": cur_start,
        "end": cur_end,
        "total_rainfall": round(cur_total, 2),
    })

    return windows


def main():
    parser = argparse.ArgumentParser(description="Find rain dates from data.gov.sg")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--output-dir", default="./processed", help="Output directory")
    parser.add_argument("--buffer-hours", type=int, default=1, help="Hours to extend before/after rain")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d")
    end = datetime.strptime(args.end, "%Y-%m-%d")
    os.makedirs(args.output_dir, exist_ok=True)

    # 按年分组收集结果
    yearly_windows: dict[int, list] = {}
    total_days = (end - start).days + 1
    rain_days_count = 0

    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        year = current.year

        if year not in yearly_windows:
            yearly_windows[year] = []

        # 每 50 天输出进度
        day_idx = (current - start).days + 1
        if day_idx % 50 == 0 or day_idx == 1:
            logger.info(f"Progress: {day_idx}/{total_days} ({date_str})")

        items = fetch_rainfall_for_date(date_str)
        windows = find_rain_windows(items, buffer_hours=args.buffer_hours)

        if windows:
            rain_days_count += 1
            for w in windows:
                yearly_windows[year].append({
                    "date": date_str,
                    "start_sgt": w["start"].strftime("%Y-%m-%d %H:%M"),
                    "end_sgt": w["end"].strftime("%Y-%m-%d %H:%M"),
                    "total_rainfall_mm": w["total_rainfall"],
                    "rain_hours": round((w["end"] - w["start"]).total_seconds() / 3600, 1),
                })

        current += timedelta(days=1)
        # data.gov.sg 的速率限制较宽松，但仍适当节流
        time.sleep(0.2)

    # 写入 CSV
    for year, windows in sorted(yearly_windows.items()):
        csv_path = os.path.join(args.output_dir, f"rain-dates-{year}.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "date", "start_sgt", "end_sgt", "total_rainfall_mm", "rain_hours"
            ])
            writer.writeheader()
            writer.writerows(windows)
        logger.info(f"  📁 {csv_path}: {len(windows)} rain windows")

    logger.info(f"✅ Done: {rain_days_count}/{total_days} days had rain")


if __name__ == "__main__":
    main()
