"""
download_aws_satellite.py — 从 AWS Open Data 下载 Himawari L1b HSD 并提取多通道 .npy

数据源:
  s3://noaa-himawari8/AHI-L1b-FLDK/  (2015-2022, 2025)
  s3://noaa-himawari9/AHI-L1b-FLDK/  (2022-2026)

输出（每个时间戳 3 个文件，原始分辨率裁剪）:
  processed_data_3ch/SAT_B08_YYYYMMDD_HHMM.npy  (水汽 6.2μm)
  processed_data_3ch/SAT_B13_YYYYMMDD_HHMM.npy  (红外 10.4μm)
  processed_data_3ch/SAT_B14_YYYYMMDD_HHMM.npy  (红外 11.2μm)

用法:
  python3 download_aws_satellite.py --start 2023-01-01 --end 2023-01-31
  python3 download_aws_satellite.py --start 2020-01-01 --end 2026-02-16
"""

import argparse
import logging
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import boto3
import numpy as np
from botocore import UNSIGNED
from botocore.config import Config

from hsd_parser import SG_CROP_BOUNDS, parse_hsd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("aws_satellite")

# ── 常量 ──
BANDS = ["B08", "B11", "B13"]
# 新加坡仅在 segment 5（12°N ~ 0°N 附近）
SEGMENT = "S0510"

# Himawari-8 → -9 切换时间（2022-12-13 UTC）
H8_END = datetime(2022, 12, 13)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 输出目录：与训练脚本同级（可通过环境变量覆盖）
OUTPUT_DIR = os.environ.get(
    "SAT_3CH_DIR",
    os.path.join(os.path.dirname(SCRIPT_DIR), "training", "processed_data_3ch"),
)

# S3 上传配置（处理完上传到私有 bucket 并删本地）
UPLOAD_BUCKET = os.environ.get("S3_BUCKET", "weather-ai-models-de08370c")
UPLOAD_PREFIX = "processed/satellite-3ch"

# completed days 缓存文件路径
COMPLETED_FILE = os.path.join(OUTPUT_DIR, ".completed_days")


def _load_completed() -> set:
    """加载已完成的日期列表，重启时跳过这些日期（零 S3 请求）"""
    if os.path.exists(COMPLETED_FILE):
        return set(open(COMPLETED_FILE).read().splitlines())
    return set()


def _mark_completed(date_str: str):
    """标记一天为已完成，追加写入避免丢失"""
    with open(COMPLETED_FILE, "a") as f:
        f.write(date_str + "\n")


def _get_bucket(dt: datetime) -> str:
    """根据日期选择 Himawari-8 或 -9 的 bucket"""
    return "noaa-himawari8" if dt < H8_END else "noaa-himawari9"


def _get_sat_prefix(dt: datetime) -> str:
    """H08 or H09"""
    return "H08" if dt < H8_END else "H09"


def _s3_key(dt: datetime, band: str) -> str:
    """构造 S3 key — 只下载包含新加坡的 segment 5"""
    prefix = _get_sat_prefix(dt)
    date_str = dt.strftime("%Y%m%d")
    time_str = dt.strftime("%H%M")
    # 文件名格式: HS_H09_20251001_0000_B13_FLDK_R20_S0510.DAT.bz2
    filename = f"HS_{prefix}_{date_str}_{time_str}_{band}_FLDK_R20_{SEGMENT}.DAT.bz2"
    return f"AHI-L1b-FLDK/{dt.year}/{dt.month:02d}/{dt.day:02d}/{time_str}/{filename}"


def _s3_upload_key(band: str, dt: datetime) -> str:
    """S3 上传路径"""
    date_str = dt.strftime("%Y%m%d")
    time_str = dt.strftime("%H%M")
    return f"{UPLOAD_PREFIX}/SAT_{band}_{date_str}_{time_str}.npy"


def _all_outputs_exist(dt: datetime, s3_client) -> bool:
    """检查 S3 上是否已有该时间戳的 3 个文件（避免重复处理）"""
    for band in BANDS:
        try:
            s3_client.head_object(Bucket=UPLOAD_BUCKET, Key=_s3_upload_key(band, dt))
        except Exception:
            return False
    return True


def process_slot(dt: datetime, s3_client, upload_s3) -> str:
    """处理一个 10 分钟时间戳：下载 3 个 segment → HSD 解析 → 像素切片 → 上传 S3

    Args:
        s3_client: 无认证 S3 client（读 AWS Open Data 公开 bucket）
        upload_s3: 带认证 S3 client（写私有 bucket）
    Returns: 'done' | 'skipped' | 'missing' | 'failed'
    """
    if _all_outputs_exist(dt, upload_s3):
        return "skipped"

    bucket = _get_bucket(dt)
    tmp_dir = tempfile.mkdtemp(prefix="hsd_")

    try:
        # 1. 下载 3 个波段的 segment 文件
        for band in BANDS:
            key = _s3_key(dt, band)
            local_path = os.path.join(tmp_dir, os.path.basename(key))
            try:
                s3_client.download_file(bucket, key, local_path)
            except Exception:
                # 该时间戳在 S3 上可能不存在
                return "missing"

            # 2. 直接解析 HSD 并裁剪新加坡区域 (替代 satpy)
            bt = parse_hsd(local_path, crop_bounds=SG_CROP_BOUNDS)

            # 3. 保存 → 上传 S3 → 删本地
            out_path = os.path.join(tmp_dir, f"SAT_{band}_{dt.strftime('%Y%m%d_%H%M')}.npy")
            np.save(out_path, bt)
            upload_s3.upload_file(out_path, UPLOAD_BUCKET, _s3_upload_key(band, dt))
            os.remove(out_path)
            # 删已下载的 HSD 文件释放磁盘
            os.remove(local_path)

        return "done"

    except Exception as e:
        logger.error(f"Failed {dt}: {e}")
        return "failed"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

# 进程级 S3 client 缓存 — 每个子进程只创建一次，后续复用
_worker_dl_client = None
_worker_ul_client = None


def _process_slot_worker(dt: datetime) -> str:
    """多进程 worker: 在子进程内创建/复用 S3 client"""
    global _worker_dl_client, _worker_ul_client
    if _worker_dl_client is None:
        _worker_dl_client = boto3.client("s3", config=Config(signature_version=UNSIGNED), region_name="us-east-1")
        _worker_ul_client = boto3.client("s3")
    return process_slot(dt, _worker_dl_client, _worker_ul_client)


def process_day(date: datetime, s3_client, workers: int = 1) -> dict:
    """处理一天的所有 10 分钟 slot（144 个/天），支持并行"""
    stats = {"done": 0, "skipped": 0, "missing": 0, "failed": 0}

    slots = []
    for slot_min in range(0, 1440, 10):
        dt = date.replace(hour=slot_min // 60, minute=slot_min % 60, second=0)
        slots.append(dt)

    if workers <= 1:
        upload_s3 = boto3.client("s3")
        for dt in slots:
            result = process_slot(dt, s3_client, upload_s3)
            stats[result] += 1
    else:
        from concurrent.futures import ProcessPoolExecutor, as_completed

        # 多进程: 每个子进程内创建自己的 S3 client
        # (boto3 client 不可跨进程序列化，且多进程天然无 GIL 竞争)
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_process_slot_worker, dt): dt for dt in slots}
            for future in as_completed(futures):
                result = future.result()
                stats[result] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="Download Himawari multi-band from AWS Open Data")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--workers", type=int, default=12, help="Parallel slots (default 12)")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d")
    end = datetime.strptime(args.end, "%Y-%m-%d")
    total_days = (end - start).days + 1

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    logger.info(f"📡 AWS Himawari multi-channel download")
    logger.info(f"   Date range: {args.start} ~ {args.end} ({total_days} days)")
    logger.info(f"   Bands: {BANDS}")
    logger.info(f"   Workers: {args.workers}")
    logger.info(f"   Output: {OUTPUT_DIR}")

    # 加载已完成日期缓存 — 重启时跳过已处理天，零 S3 请求
    completed = _load_completed()
    if completed:
        logger.info(f"   📋 Skipping {len(completed)} completed days from cache")

    # 主线程 S3 客户端（单线程模式使用）
    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED), region_name="us-east-1")

    current = start
    day_num = 0
    while current <= end:
        day_num += 1
        date_str = current.strftime("%Y-%m-%d")

        # 已完成的日期直接跳过
        if date_str in completed:
            logger.info(f"[{day_num}/{total_days}] {date_str} ⏭ cached skip")
            current += timedelta(days=1)
            continue

        bucket = _get_bucket(current)
        logger.info(f"[{day_num}/{total_days}] {date_str} (bucket: {bucket})")

        stats = process_day(current, s3, workers=args.workers)
        logger.info(
            f"  ✅ done={stats['done']}, skipped={stats['skipped']}, "
            f"missing={stats['missing']}, failed={stats['failed']}"
        )

        # 无失败的天标记为完成
        if stats["failed"] == 0:
            _mark_completed(date_str)

        current += timedelta(days=1)

    logger.info("🏁 All done!")


if __name__ == "__main__":
    main()
