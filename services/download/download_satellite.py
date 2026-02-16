"""
日常卫星数据下载+预处理模块

流程：JAXA FTP → 本地 .nc → crop 新加坡区域 64×64 .npy → 上传 S3 → 删除 .nc
供 download_manager.py 的 realtime/backfill thread 调用。

用法:
    # 作为模块
    from download_satellite import process_day

    # 命令行（处理指定日期范围）
    python3 download_satellite.py --start 2024-01-01 --end 2024-01-31
"""
import argparse
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import boto3
import numpy as np
import xarray as xr
import torch
import torch.nn.functional as F
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("download_satellite")

# ── JAXA FTP 配置（从环境变量或 .env 读取）──
JAXA_USER = os.environ.get("JAXA_USER", "")
JAXA_PASS = os.environ.get("JAXA_PASS", "")
FTP_BASE = "ftp://ftp.ptree.jaxa.jp"
PARALLEL_JOBS = int(os.environ.get("PARALLEL_JOBS", "12"))

# ── S3 配置 ──
S3_BUCKET = os.environ.get("S3_BUCKET", "weather-ai-models-de08370c")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", None)
S3_PROCESSED_PREFIX = "processed/satellite"
S3_RAW_PREFIX = "satellite"

# ── Himawari EQR 投影常量（60N~60S, 70E~150W, 0.02° 分辨率）──
LAT_MAX = 60.0
LON_MIN = 70.0
RES = 0.02

# 新加坡裁剪框
SG_LAT_MAX, SG_LON_MIN = 1.50, 103.6
SG_LAT_MIN, SG_LON_MAX = 1.15, 104.1
TARGET_SIZE = (64, 64)


def _latlon2xy(lat: float, lon: float) -> tuple[int, int]:
    """经纬度 → 像素坐标（EQR L3 投影）。"""
    y = int(round((LAT_MAX - lat) / RES))
    x = int(round((lon - LON_MIN) / RES))
    return x, y


# 预计算裁剪像素坐标
_C1, _L1 = _latlon2xy(SG_LAT_MAX, SG_LON_MIN)
_C2, _L2 = _latlon2xy(SG_LAT_MIN, SG_LON_MAX)
_R_MIN, _R_MAX = min(_L1, _L2), max(_L1, _L2)
_C_MIN, _C_MAX = min(_C1, _C2), max(_C1, _C2)


def load_env():
    """从同目录 .env 加载 JAXA 凭证。"""
    global JAXA_USER, JAXA_PASS
    if JAXA_USER:
        return
    env_candidates = [
        Path(__file__).parent / ".env",
        Path.home() / "weather-ai" / ".env",
    ]
    for env_path in env_candidates:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("export JAXA_USER="):
                    JAXA_USER = line.split("=", 1)[1].strip('"')
                elif line.startswith("export JAXA_PASS="):
                    JAXA_PASS = line.split("=", 1)[1].strip('"')
                elif line.startswith("export PARALLEL_JOBS="):
                    global PARALLEL_JOBS
                    PARALLEL_JOBS = int(line.split("=", 1)[1].strip('"'))
            break


def get_s3_client():
    return boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)


def crop_nc_to_npy(nc_path: str) -> np.ndarray | None:
    """
    将 Himawari .nc 裁剪为新加坡区域 64×64 numpy 数组。
    兼容 tbb / tbb_13 变量名，Full Disk（>1000行）和已裁剪两种格式。
    """
    try:
        ds = xr.open_dataset(nc_path, decode_timedelta=False)

        var_name = 'tbb'
        if 'tbb_13' in ds:
            var_name = 'tbb_13'
        if var_name not in ds:
            ds.close()
            return None

        # Full Disk → 裁剪新加坡区域
        if ds[var_name].shape[0] > 1000:
            data = ds[var_name][_R_MIN:_R_MAX, _C_MIN:_C_MAX].values
        else:
            data = ds[var_name].values

        tensor = torch.tensor(data, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
        resized = F.interpolate(tensor, size=TARGET_SIZE, mode='bilinear', align_corners=False)
        result = resized.squeeze().numpy()

        ds.close()
        return result
    except Exception as e:
        logger.error(f"Crop failed for {nc_path}: {e}")
        return None


def check_s3_npy_exists(s3, date_compact: str, filename_hint: str) -> bool:
    """检查 S3 是否已有该文件的 .npy。"""
    npy_name = filename_hint.replace(".nc", ".npy")
    s3_key = f"{S3_PROCESSED_PREFIX}/{date_compact}/{npy_name}"
    try:
        s3.head_object(Bucket=S3_BUCKET, Key=s3_key)
        return True
    except ClientError:
        return False


def list_s3_raw_files(s3, date_compact: str) -> list[str]:
    """列出 S3 satellite/{date}/ 中的 raw .nc 文件 key。"""
    prefix = f"{S3_RAW_PREFIX}/{date_compact}/"
    keys = []
    try:
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
            for obj in page.get('Contents', []):
                if obj['Key'].endswith('.nc'):
                    keys.append(obj['Key'])
    except Exception as e:
        logger.warning(f"Failed to list S3 raw files for {date_compact}: {e}")
    return keys


def list_ftp_files(date_compact: str) -> list[str]:
    """列出 JAXA FTP 指定日期的所有卫星文件名。"""
    year_month = date_compact[:6]
    day = date_compact[6:8]
    ftp_dir = f"{FTP_BASE}/jma/netcdf/{year_month}/{day}/"

    result = subprocess.run(
        ["curl", "-s", "--ftp-ssl", "-l",
         "--user", f"{JAXA_USER}:{JAXA_PASS}", ftp_dir],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []

    # 筛选 07001_06001 (优先) 和 06001_06001 文件
    files = result.stdout.strip().splitlines()
    primary = [f for f in files if "FLDK.07001_06001.nc" in f]
    fallback = [f for f in files if "FLDK.06001_06001.nc" in f]

    # 对每个时间戳，优先取 07001，没有则取 06001
    selected = {}
    for f in primary:
        parts = f.split("_")
        if len(parts) >= 4:
            ts = parts[3]  # HHMM
            selected[ts] = f
    for f in fallback:
        parts = f.split("_")
        if len(parts) >= 4:
            ts = parts[3]
            if ts not in selected:
                selected[ts] = f

    return list(selected.values())


def _crop_and_upload(local_nc: str, filename: str, date_compact: str,
                     s3, tmp_dir: str, source: str = "FTP") -> str:
    """对本地 .nc 文件执行 crop → upload .npy → 清理。"""
    npy_data = crop_nc_to_npy(local_nc)
    if npy_data is None:
        return "failed"

    npy_name = filename.replace(".nc", ".npy")
    local_npy = os.path.join(tmp_dir, npy_name)
    np.save(local_npy, npy_data)

    s3_key = f"{S3_PROCESSED_PREFIX}/{date_compact}/{npy_name}"
    s3.upload_file(local_npy, S3_BUCKET, s3_key)
    logger.info(f"📤 [{source}] {npy_name} → s3://{S3_BUCKET}/{s3_key}")

    os.remove(local_npy)
    return "uploaded"


def download_crop_upload(filename: str, date_compact: str, s3, tmp_dir: str,
                         s3_raw_key: str | None = None) -> str:
    """
    单文件处理：download .nc → crop → upload .npy → delete .nc
    优先从 S3 raw 下载（同区域快），回退到 JAXA FTP。
    返回: 'uploaded' | 'skipped' | 'failed'
    """
    if check_s3_npy_exists(s3, date_compact, filename):
        return "skipped"

    local_nc = os.path.join(tmp_dir, filename)

    try:
        # 优先从 S3 下载已有的 raw .nc（同区域，速度快）
        if s3_raw_key:
            try:
                s3.download_file(S3_BUCKET, s3_raw_key, local_nc)
                if os.path.getsize(local_nc) > 1_000_000:
                    return _crop_and_upload(local_nc, filename, date_compact, s3, tmp_dir, source="S3")
            except Exception as e:
                logger.warning(f"S3 raw download failed, trying FTP: {e}")
                if os.path.exists(local_nc):
                    os.remove(local_nc)

        # 回退到 JAXA FTP 下载
        year_month = date_compact[:6]
        day = date_compact[6:8]
        ftp_url = f"{FTP_BASE}/jma/netcdf/{year_month}/{day}/{filename}"

        result = subprocess.run(
            ["curl", "-s", "--ftp-ssl",
             "--user", f"{JAXA_USER}:{JAXA_PASS}",
             "-o", local_nc, ftp_url],
            capture_output=True, timeout=300
        )

        if result.returncode != 0 or not os.path.exists(local_nc):
            return "failed"
        if os.path.getsize(local_nc) < 1_000_000:
            return "failed"

        return _crop_and_upload(local_nc, filename, date_compact, s3, tmp_dir, source="FTP")

    except Exception as e:
        logger.error(f"❌ {filename}: {e}")
        return "failed"
    finally:
        if os.path.exists(local_nc):
            os.remove(local_nc)


def process_day(date_str: str, s3=None) -> dict:
    """
    处理一天的所有卫星文件。
    优先从 S3 已有的 raw .nc crop，没有的再从 JAXA FTP 下载。

    Args:
        date_str: 'YYYY-MM-DD' 格式日期
        s3: 可选 S3 client

    Returns:
        {'date': str, 'total': int, 'uploaded': int, 'skipped': int, 'failed': int}
    """
    date_compact = date_str.replace("-", "")
    if s3 is None:
        s3 = get_s3_client()

    # 先检查 S3 是否有已有的 raw .nc（backfill 场景，避免重新从 FTP 下载）
    s3_raw_keys = list_s3_raw_files(s3, date_compact)
    # 建立 filename → s3_key 映射
    s3_raw_map = {key.split("/")[-1]: key for key in s3_raw_keys}

    files = list_ftp_files(date_compact)
    result = {"date": date_str, "total": len(files), "uploaded": 0, "skipped": 0, "failed": 0}

    if not files and not s3_raw_map:
        logger.warning(f"⚠️ {date_str}: no files found on FTP or S3")
        return result

    # 如果 FTP 为空但 S3 有 raw，用 S3 的文件名列表
    if not files and s3_raw_map:
        files = list(s3_raw_map.keys())
        result["total"] = len(files)

    with tempfile.TemporaryDirectory(prefix="sat_") as tmp_dir:
        for filename in files:
            s3_key = s3_raw_map.get(filename)
            status = download_crop_upload(filename, date_compact, s3, tmp_dir, s3_raw_key=s3_key)
            result[status] += 1

    source = "S3" if s3_raw_map else "FTP"
    icon = "✅" if result["failed"] == 0 else "⚠️"
    logger.info(
        f"{icon} {date_str} [{source}]: {result['uploaded']}↑ {result['skipped']}⏭ "
        f"{result['failed']}❌ ({result['total']} files)"
    )
    return result


def main():
    """命令行入口：处理指定日期范围的所有卫星数据。"""
    parser = argparse.ArgumentParser(description="日常卫星下载+预处理")
    parser.add_argument("--start", required=True, help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="结束日期 YYYY-MM-DD")
    args = parser.parse_args()

    load_env()
    if not JAXA_USER or not JAXA_PASS:
        logger.error("❌ JAXA 凭证未设置，请配置 services/download/.env")
        return

    s3 = get_s3_client()
    current = datetime.strptime(args.start, "%Y-%m-%d")
    end = datetime.strptime(args.end, "%Y-%m-%d")

    stats = {"uploaded": 0, "skipped": 0, "failed": 0, "days": 0}

    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        result = process_day(date_str, s3)
        stats["uploaded"] += result["uploaded"]
        stats["skipped"] += result["skipped"]
        stats["failed"] += result["failed"]
        stats["days"] += 1
        current += timedelta(days=1)

    logger.info(f"\n{'='*60}")
    logger.info(f"COMPLETE - {stats['days']} days")
    logger.info(f"  Uploaded: {stats['uploaded']}")
    logger.info(f"  Skipped:  {stats['skipped']}")
    logger.info(f"  Failed:   {stats['failed']}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
