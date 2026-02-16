"""
Step 3: 只为雨天时段下载卫星数据 → 预处理 .npy → 上传 S3
从 NOAA AWS Open Data (noaa-himawari9) 下载 ISatSS C13 tile，裁剪为 128×128 .npy。

用法:
    python3 process_satellite_rainy.py [--workers 8] [--timestamps data/rainy_timestamps.json]
"""
import argparse
import json
import logging
import os
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from noaa_satellite import download_and_crop, make_npy_filename
from satellite_preprocessor import (
    upload_npy_to_s3,
    check_s3_processed_exists,
    get_s3_client,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_TIMESTAMPS = Path(__file__).parent / "data" / "rainy_timestamps.json"
NPY_OUTPUT_DIR = Path(__file__).parent / "data" / "satellite"
STATE_FILE = Path(__file__).parent / "data" / "satellite_process_state.json"


def process_single_slot(date_compact: str, slot: str, tmp_dir: str) -> dict:
    """
    处理单个雨时段：从 NOAA S3 下载 tile → 裁剪 128×128 → 上传 .npy
    """
    result = {"date": date_compact, "slot": slot, "status": "unknown"}

    # 每个进程独立创建 S3 client（ProcessPoolExecutor 不能共享）
    s3 = get_s3_client()

    # 检查 S3 是否已有 processed .npy
    slot_prefix = f"_{slot}"
    if check_s3_processed_exists(s3, date_compact, slot_prefix):
        result["status"] = "skipped"
        return result

    # rainy_timestamps.json 里的 slot 是 SGT (UTC+8)
    # download_and_crop 内部会自动转 UTC 查找 S3 文件
    try:
        dt_sgt = datetime.strptime(f"{date_compact}_{slot}", "%Y%m%d_%H%M")
    except ValueError:
        result["status"] = "invalid_timestamp"
        return result

    try:
        arr, npy_name = download_and_crop(dt_sgt, tmp_dir)
        if arr is None:
            result["status"] = "download_failed"
            return result

        # 保存 .npy 到本地
        local_npy = NPY_OUTPUT_DIR / npy_name
        np.save(str(local_npy), arr)

        # 上传 .npy 到 S3
        success = upload_npy_to_s3(str(local_npy), date_compact, s3=s3)
        result["status"] = "uploaded" if success else "upload_failed"

    except Exception as e:
        result["status"] = f"error: {e}"

    return result


def process_day(day_info: dict, tmp_dir: str) -> dict:
    """处理单日所有雨时段。"""
    date = day_info["date"]
    date_compact = day_info["date_compact"]
    slots = day_info["rainy_slots"]

    day_result = {
        "date": date,
        "total_slots": len(slots),
        "skipped": 0, "uploaded": 0, "failed": 0,
    }

    for slot in slots:
        r = process_single_slot(date_compact, slot, tmp_dir)
        if r["status"] == "skipped":
            day_result["skipped"] += 1
        elif r["status"] == "uploaded":
            day_result["uploaded"] += 1
        else:
            day_result["failed"] += 1
            logger.warning(f"  ❌ {date} {slot}: {r['status']}")

    return day_result


def save_state(state: dict):
    """保存处理进度（支持断点续传）。"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_state() -> dict:
    """加载已完成的日期集合。"""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"completed_dates": [], "stats": {"uploaded": 0, "skipped": 0, "failed": 0}}


def main():
    parser = argparse.ArgumentParser(description="雨天卫星数据定向下载+预处理 (NOAA)")
    parser.add_argument("--workers", type=int, default=8,
                        help="并行下载线程数（默认 8）")
    parser.add_argument("--timestamps", type=str, default=str(DEFAULT_TIMESTAMPS),
                        help="rainy_timestamps.json 路径")
    args = parser.parse_args()

    # 加载雨天清单
    with open(args.timestamps) as f:
        timestamps = json.load(f)

    all_days = timestamps["days"]
    logger.info(f"Loaded {len(all_days)} rain days, {timestamps['total_rainy_slots']} slots")
    logger.info(f"Workers: {args.workers}")
    logger.info(f"Data source: NOAA AWS Open Data (noaa-himawari9)")

    # 加载断点续传状态
    state = load_state()
    completed = set(state["completed_dates"])
    days_to_process = [d for d in all_days if d["date"] not in completed]
    logger.info(f"Already completed: {len(completed)}, remaining: {len(days_to_process)}")

    NPY_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    s3 = get_s3_client()

    # 使用临时目录存放下载的 tile .nc
    with tempfile.TemporaryDirectory(prefix="noaa_") as tmp_dir:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(process_day, day, tmp_dir): day
                for day in days_to_process
            }

            for i, future in enumerate(as_completed(futures), 1):
                day_info = futures[future]
                try:
                    result = future.result()
                    state["completed_dates"].append(result["date"])
                    state["stats"]["uploaded"] += result["uploaded"]
                    state["stats"]["skipped"] += result["skipped"]
                    state["stats"]["failed"] += result["failed"]

                    status_icon = "✅" if result["failed"] == 0 else "⚠️"
                    logger.info(
                        f"  [{i}/{len(days_to_process)}] {result['date']}: "
                        f"{status_icon} {result['uploaded']}↑ {result['skipped']}⏭ {result['failed']}❌ "
                        f"({result['total_slots']} slots)"
                    )

                    if i % 10 == 0:
                        save_state(state)

                except Exception as e:
                    logger.error(f"  ❌ {day_info['date']}: {e}")

    save_state(state)

    logger.info(f"\n{'='*60}")
    logger.info(f"COMPLETE")
    logger.info(f"  Uploaded: {state['stats']['uploaded']}")
    logger.info(f"  Skipped:  {state['stats']['skipped']}")
    logger.info(f"  Failed:   {state['stats']['failed']}")
    logger.info(f"  State:    {STATE_FILE}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
