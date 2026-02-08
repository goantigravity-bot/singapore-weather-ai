import os
import glob
import logging
import numpy as np
import xarray as xr
import torch
import torch.nn.functional as F
import boto3
from botocore.exceptions import ClientError
from weather_dataset import latlon2xy

logger = logging.getLogger(__name__)

# Config
RAW_DIR = "satellite_data"
PROCESSED_DIR = "processed_data"
TARGET_SIZE = (64, 64)

# S3 配置（复用训练服务器的环境变量）
S3_BUCKET = os.environ.get("S3_BUCKET", "weather-ai-models-de08370c")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", None)
S3_PROCESSED_PREFIX = "processed/satellite"

# Singapore Crop Box (Must match weather_dataset.py)
SG_LAT_MAX, SG_LON_MIN = 1.50, 103.6
C1, L1 = latlon2xy(SG_LAT_MAX, SG_LON_MIN) 
SG_LAT_MIN, SG_LON_MAX = 1.15, 104.1
C2, L2 = latlon2xy(SG_LAT_MIN, SG_LON_MAX)


def _get_s3_client():
    return boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)


def _extract_date_from_filename(fname):
    """从文件名 NC_H09_YYYYMMDD_HHMM_... 提取日期字符串"""
    parts = fname.split("_")
    if len(parts) >= 3:
        return parts[2]  # YYYYMMDD
    return None


def upload_to_s3(local_path, fname):
    """
    将处理后的 .npy 上传到 S3，按日期分目录存储。
    上传失败仅记录 WARNING，不阻塞训练流程。
    """
    date_str = _extract_date_from_filename(fname)
    if not date_str:
        return

    npy_name = fname.replace(".nc", ".npy")
    s3_key = f"{S3_PROCESSED_PREFIX}/{date_str}/{npy_name}"

    try:
        s3 = _get_s3_client()

        # 检查 S3 是否已存在，避免重复上传
        try:
            s3.head_object(Bucket=S3_BUCKET, Key=s3_key)
            return  # 已存在则跳过
        except ClientError:
            pass  # 不存在，继续上传

        s3.upload_file(local_path, S3_BUCKET, s3_key)
        logger.info(f"📤 Uploaded {npy_name} → s3://{S3_BUCKET}/{s3_key}")

    except Exception as e:
        logger.warning(f"S3 upload failed for {npy_name}: {e}")


def preprocess(input_dirs):
    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR)
        
    all_files = []
    
    logger.info(f"Scanning directories: {input_dirs}")
    
    for d in input_dirs:
        if not os.path.exists(d):
            logger.warning(f"Directory '{d}' not found. Skipping.")
            continue
            
        found_files = glob.glob(os.path.join(d, "NC_H09_*.nc"))
        logger.info(f"Found {len(found_files)} satellite files in '{d}'.")
        all_files.extend(found_files)
        
    if not all_files:
        logger.info("No files found in any of the specified directories.")
        return

    logger.info(f"Total files to process: {len(all_files)}")
    uploaded_count = 0
    
    for i, fpath in enumerate(all_files):
        fname = os.path.basename(fpath)
        out_name = fname.replace(".nc", ".npy")
        out_path = os.path.join(PROCESSED_DIR, out_name)
        
        if os.path.exists(out_path):
            # 本地已有，但仍尝试上传到 S3（幂等操作）
            upload_to_s3(out_path, fname)
            continue
            
        try:
            ds = xr.open_dataset(fpath, decode_timedelta=False)
            
            var_name = 'tbb'
            if 'tbb_13' in ds:
                var_name = 'tbb_13'
                
            if var_name not in ds:
                logger.warning(f"Skipping {fname}: Variable not found.")
                continue

            # Full Disk → 裁剪新加坡区域并缩放到 64x64
            if ds[var_name].shape[0] > 1000:
                r_min, r_max = min(L1, L2), max(L1, L2)
                c_min, c_max = min(C1, C2), max(C1, C2)
                
                data = ds[var_name][r_min:r_max, c_min:c_max].values
                
                tensor = torch.tensor(data, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
                resized = F.interpolate(tensor, size=TARGET_SIZE, mode='bilinear', align_corners=False)
                final_arr = resized.squeeze().numpy()
                
            else:
                data = ds[var_name].values
                if data.shape != TARGET_SIZE:
                     tensor = torch.tensor(data, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
                     resized = F.interpolate(tensor, size=TARGET_SIZE, mode='bilinear', align_corners=False)
                     final_arr = resized.squeeze().numpy()
                else:
                     final_arr = data

            # 保存原始 Kelvin 值（float32），归一化在运行时由 Dataset 处理
            np.save(out_path, final_arr)
            
            # 上传到 S3（不阻塞训练）
            upload_to_s3(out_path, fname)
            uploaded_count += 1
            
            ds.close()
            
        except Exception as e:
            logger.error(f"Error processing {fname}: {e}")

    logger.info(f"Preprocessing Complete! {uploaded_count} new files processed and uploaded.")

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    parser = argparse.ArgumentParser(description="Preprocess Satellite Data")
    parser.add_argument("--dirs", nargs='+', default=[RAW_DIR], help="List of folders containing satellite .nc files")
    args = parser.parse_args()
    
    preprocess(args.dirs)
