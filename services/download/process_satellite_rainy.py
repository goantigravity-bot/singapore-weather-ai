"""
Step 3: 只为雨天时段下载卫星 .nc → 预处理 .npy → 上传 S3
从 JAXA FTP 直接下载到本地，预处理后只上传 .npy，不保留原始 .nc

用法:
    python3 process_satellite_rainy.py [--workers 4] [--timestamps data/rainy_timestamps.json]
"""
import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# satellite_preprocessor 在同目录，直接 import

from satellite_preprocessor import (
    crop_nc_to_npy,
    upload_npy_to_s3,
    check_s3_processed_exists,
    get_s3_client,
    extract_date_from_filename,
)
import numpy as np

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# JAXA FTP 配置（从环境变量或 .env 读取）
JAXA_USER = os.environ.get("JAXA_USER", "")
JAXA_PASS = os.environ.get("JAXA_PASS", "")
FTP_BASE = "ftp://ftp.ptree.jaxa.jp"

# 卫星文件命名：NC_H09_YYYYMMDD_HHMM_R21_FLDK.07001_06001.nc
FILE_PATTERN_07 = "NC_H09_{date}_{slot}_R21_FLDK.07001_06001.nc"
FILE_PATTERN_06 = "NC_H09_{date}_{slot}_R21_FLDK.06001_06001.nc"
# Himawari-8 fallback
FILE_PATTERN_H08_07 = "NC_H08_{date}_{slot}_R21_FLDK.07001_06001.nc"
FILE_PATTERN_H08_06 = "NC_H08_{date}_{slot}_R21_FLDK.06001_06001.nc"

DEFAULT_TIMESTAMPS = Path(__file__).parent / "data" / "rainy_timestamps.json"
NPY_OUTPUT_DIR = Path(__file__).parent / "data" / "satellite"
STATE_FILE = Path(__file__).parent / "data" / "satellite_process_state.json"


def load_env():
    """从同目录 .env 加载 JAXA 凭证。"""
    global JAXA_USER, JAXA_PASS
    # 优先同目录 .env，fallback 到 ~/weather-ai/.env
    env_candidates = [
        Path(__file__).parent / ".env",
        Path.home() / "weather-ai" / ".env",
    ]
    for env_path in env_candidates:
        if env_path.exists() and not JAXA_USER:
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("export JAXA_USER="):
                    JAXA_USER = line.split("=", 1)[1].strip('"')
                elif line.startswith("export JAXA_PASS="):
                    JAXA_PASS = line.split("=", 1)[1].strip('"')
            break


def download_nc_from_ftp(date_compact: str, slot: str, tmp_dir: str) -> str | None:
    """
    从 JAXA FTP 下载单个 .nc 文件到本地临时目录。
    尝试 H09 07001 → H09 06001 → H08 07001 → H08 06001 的 fallback 顺序。
    返回本地文件路径，失败返回 None。
    """
    year_month = date_compact[:6]
    day = date_compact[6:8]
    remote_dir = f"/jma/netcdf/{year_month}/{day}"

    # 按优先级尝试不同文件名模式
    patterns = [
        FILE_PATTERN_07, FILE_PATTERN_06,
        FILE_PATTERN_H08_07, FILE_PATTERN_H08_06,
    ]

    for pattern in patterns:
        filename = pattern.format(date=date_compact, slot=slot)
        ftp_url = f"{FTP_BASE}{remote_dir}/{filename}"
        local_path = os.path.join(tmp_dir, filename)

        result = subprocess.run(
            ["curl", "-s", "--ftp-ssl", "--user", f"{JAXA_USER}:{JAXA_PASS}",
             "-o", local_path, ftp_url],
            capture_output=True, timeout=300
        )

        # 检查下载是否成功且文件大小合理 (> 1MB)
        if result.returncode == 0 and os.path.exists(local_path):
            size = os.path.getsize(local_path)
            if size > 1_000_000:
                return local_path
            else:
                os.remove(local_path)

    return None


def process_single_slot(date_compact: str, slot: str, s3, tmp_dir: str) -> dict:
    """
    处理单个雨时段：下载 .nc → crop → 上传 .npy → 删除 .nc
    返回处理结果 dict。
    """
    result = {"date": date_compact, "slot": slot, "status": "unknown"}

    # 检查 S3 是否已有 processed .npy
    slot_prefix = f"_{slot}_"
    if check_s3_processed_exists(s3, date_compact, slot_prefix):
        result["status"] = "skipped"
        return result

    # 下载 .nc
    nc_path = download_nc_from_ftp(date_compact, slot, tmp_dir)
    if not nc_path:
        result["status"] = "ftp_failed"
        return result

    try:
        # 预处理 crop
        npy_data = crop_nc_to_npy(nc_path)
        if npy_data is None:
            result["status"] = "crop_failed"
            return result

        # 保存 .npy 到本地
        npy_filename = os.path.basename(nc_path).replace(".nc", ".npy")
        local_npy = NPY_OUTPUT_DIR / npy_filename
        np.save(str(local_npy), npy_data)

        # 上传 .npy 到 S3
        success = upload_npy_to_s3(str(local_npy), date_compact, s3=s3)
        result["status"] = "uploaded" if success else "upload_failed"

    except Exception as e:
        result["status"] = f"error: {e}"
    finally:
        # 立即删除本地 .nc
        if os.path.exists(nc_path):
            os.remove(nc_path)

    return result


def process_day(day_info: dict, s3, tmp_dir: str) -> dict:
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
        r = process_single_slot(date_compact, slot, s3, tmp_dir)
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
    parser = argparse.ArgumentParser(description="雨天卫星数据定向下载+预处理")
    parser.add_argument("--workers", type=int, default=8,
                        help="并行下载线程数（默认 8）")
    parser.add_argument("--timestamps", type=str, default=str(DEFAULT_TIMESTAMPS),
                        help="rainy_timestamps.json 路径")
    args = parser.parse_args()

    load_env()
    if not JAXA_USER or not JAXA_PASS:
        logger.error("❌ JAXA 凭证未设置，请设置 JAXA_USER/JAXA_PASS 或确认 services/download/.env")
        sys.exit(1)

    # 加载雨天清单
    with open(args.timestamps) as f:
        timestamps = json.load(f)

    all_days = timestamps["days"]
    logger.info(f"Loaded {len(all_days)} rain days, {timestamps['total_rainy_slots']} slots")
    logger.info(f"Workers: {args.workers}")

    # 加载断点续传状态
    state = load_state()
    completed = set(state["completed_dates"])
    days_to_process = [d for d in all_days if d["date"] not in completed]
    logger.info(f"Already completed: {len(completed)}, remaining: {len(days_to_process)}")

    NPY_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    s3 = get_s3_client()

    # 使用临时目录存放 .nc 文件
    with tempfile.TemporaryDirectory(prefix="sat_") as tmp_dir:
        # 多线程处理（每个线程处理一天的所有 slots）
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(process_day, day, s3, tmp_dir): day
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

                    # 每 10 天保存一次状态
                    if i % 10 == 0:
                        save_state(state)

                except Exception as e:
                    logger.error(f"  ❌ {day_info['date']}: {e}")

    # 最终保存
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
