"""
训练预处理入口 — 批量扫描目录并处理所有 .nc 文件

复用 satellite_preprocessor 模块的裁剪和上传逻辑。
"""
import os
import glob
import logging

from satellite_preprocessor import (
    crop_nc_to_npy,
    upload_npy_to_s3,
    extract_date_from_filename,
)

logger = logging.getLogger(__name__)

# Config
RAW_DIR = "satellite_data"
PROCESSED_DIR = "processed_data"


def preprocess(input_dirs):
    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR)

    all_files = []

    logger.info(f"Scanning directories: {input_dirs}")

    for d in input_dirs:
        if not os.path.exists(d):
            logger.warning(f"Directory '{d}' not found. Skipping.")
            continue

        # 兼容 Himawari-8 (H08) 和 Himawari-9 (H09) 两种前缀
        for prefix in ["NC_H08_", "NC_H09_"]:
            found_files = glob.glob(os.path.join(d, f"{prefix}*.nc"))
            if found_files:
                logger.info(f"Found {len(found_files)} {prefix} files in '{d}'.")
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
            date_str = extract_date_from_filename(fname)
            if date_str:
                upload_npy_to_s3(out_path, date_str)
            continue

        # 裁剪 .nc → .npy
        final_arr = crop_nc_to_npy(fpath)
        if final_arr is None:
            logger.warning(f"Skipping {fname}: crop failed.")
            continue

        import numpy as np
        np.save(out_path, final_arr)

        # 上传到 S3
        date_str = extract_date_from_filename(fname)
        if date_str:
            upload_npy_to_s3(out_path, date_str)
        uploaded_count += 1

    logger.info(f"Preprocessing Complete! {uploaded_count} new files processed and uploaded.")


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    parser = argparse.ArgumentParser(description="Preprocess Satellite Data")
    parser.add_argument("--dirs", nargs='+', default=[RAW_DIR],
                        help="List of folders containing satellite .nc files")
    args = parser.parse_args()

    preprocess(args.dirs)
