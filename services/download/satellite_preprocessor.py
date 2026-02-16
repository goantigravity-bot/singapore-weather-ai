"""
卫星数据预处理模块 — 独立可复用

职责：
  1. 将 Himawari .nc 裁剪为新加坡区域 64×64 .npy
  2. 上传/检查 S3 processed/ 目录
  3. 提取文件名中的日期/时间元数据

被以下程序复用：
  - preprocess_images.py（训练预处理入口）
  - process_and_train_daily.py（逐日训练管线）
  - reprocess-missing-satellite.py（补处理脚本）
"""
import os
import logging
import numpy as np
import xarray as xr
import torch
import torch.nn.functional as F
import boto3
from botocore.exceptions import ClientError
from weather_dataset import latlon2xy

logger = logging.getLogger(__name__)

# ── 裁剪参数 ──
TARGET_SIZE = (64, 64)

# 新加坡裁剪框（与 weather_dataset.py 保持一致）
SG_LAT_MAX, SG_LON_MIN = 1.50, 103.6
C1, L1 = latlon2xy(SG_LAT_MAX, SG_LON_MIN)
SG_LAT_MIN, SG_LON_MAX = 1.15, 104.1
C2, L2 = latlon2xy(SG_LAT_MIN, SG_LON_MAX)

# ── S3 配置 ──
S3_BUCKET = os.environ.get("S3_BUCKET", "weather-ai-models-de08370c")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", None)
S3_PROCESSED_PREFIX = "processed/satellite"


def get_s3_client():
    """获取 S3 client，统一复用。"""
    return boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)


def extract_date_from_filename(fname: str) -> str | None:
    """从文件名 NC_H0x_YYYYMMDD_HHMM_... 提取日期字符串 YYYYMMDD。"""
    parts = fname.split("_")
    if len(parts) >= 3:
        return parts[2]
    return None


def crop_nc_to_npy(nc_path: str) -> np.ndarray | None:
    """
    将单个 .nc 文件裁剪为新加坡区域 64×64 numpy 数组。

    处理 Full Disk（>1000 行）和已裁剪两种格式，
    兼容 tbb / tbb_13 变量名。
    返回 float32 数组（原始 Kelvin 值），归一化由 Dataset 运行时处理。
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
            r_min, r_max = min(L1, L2), max(L1, L2)
            c_min, c_max = min(C1, C2), max(C1, C2)
            data = ds[var_name][r_min:r_max, c_min:c_max].values
        else:
            data = ds[var_name].values

        # 缩放到 64×64
        tensor = torch.tensor(data, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
        resized = F.interpolate(tensor, size=TARGET_SIZE, mode='bilinear', align_corners=False)
        final_arr = resized.squeeze().numpy()

        ds.close()
        return final_arr
    except Exception as e:
        logger.error(f"Error processing {nc_path}: {e}")
        return None


def upload_npy_to_s3(local_path: str, date_compact: str,
                     s3=None, skip_if_exists: bool = True) -> bool:
    """
    上传 .npy 到 S3 processed/satellite/{date}/ 目录。

    Args:
        local_path: 本地 .npy 文件路径
        date_compact: YYYYMMDD 格式日期
        s3: 可选已有 S3 client（避免重复创建）
        skip_if_exists: 为 True 时先 head_object 检查是否已存在

    Returns:
        True 表示上传成功或已存在，False 表示失败
    """
    if s3 is None:
        s3 = get_s3_client()

    npy_fname = os.path.basename(local_path)
    s3_key = f"{S3_PROCESSED_PREFIX}/{date_compact}/{npy_fname}"

    try:
        if skip_if_exists:
            try:
                s3.head_object(Bucket=S3_BUCKET, Key=s3_key)
                return True  # 已存在
            except ClientError:
                pass

        s3.upload_file(local_path, S3_BUCKET, s3_key)
        logger.info(f"📤 Uploaded {npy_fname} → s3://{S3_BUCKET}/{s3_key}")
        return True
    except Exception as e:
        logger.warning(f"S3 upload failed for {npy_fname}: {e}")
        return False


def check_s3_processed_exists(s3, date_compact: str, slot_prefix: str) -> bool:
    """检查 S3 processed/ 目录中是否已有该时间片的 .npy。"""
    proc_prefix = f"{S3_PROCESSED_PREFIX}/{date_compact}/"
    resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=proc_prefix)
    existing = [o['Key'] for o in resp.get('Contents', []) if slot_prefix in o['Key']]
    return len(existing) > 0


def list_raw_nc_keys(s3, date_compact: str, slot_prefix: str) -> list[str]:
    """列出 S3 satellite/{date}/ 中匹配指定时间片的 raw .nc 文件 key。"""
    raw_prefix = f"satellite/{date_compact}/"
    resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=raw_prefix)
    return [
        obj['Key'] for obj in resp.get('Contents', [])
        if obj['Key'].endswith('.nc') and slot_prefix in obj['Key']
    ]


def ensure_h09_symlinks(sat_dir: str) -> int:
    """
    WeatherDataset 硬编码 NC_H09_ 前缀加载 .npy 文件。
    为较旧的 Himawari-8 (NC_H08_) 文件创建 H09 符号链接。

    Returns:
        创建的符号链接数量
    """
    from pathlib import Path
    sat_path = Path(sat_dir)
    created = 0
    for f in sat_path.glob("NC_H08_*.npy"):
        h09_name = f.name.replace("NC_H08_", "NC_H09_")
        h09_path = sat_path / h09_name
        if not h09_path.exists():
            h09_path.symlink_to(f)
            created += 1
    if created > 0:
        logger.info(f"Created {created} H09 symlinks for H08 files")
    return created
