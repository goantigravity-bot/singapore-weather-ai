"""
migrate_s3_structure.py — 下载平铺的 satellite-3ch npy 到本地，按日期整理后上传回 S3

流程：逐日期处理 → 下载 → 上传到新路径 → 写 .complete → 删旧文件
404 视为"已迁移"跳过。支持断点续传。

用法:
  python3 migrate_s3_structure.py              # dry-run
  python3 migrate_s3_structure.py --execute    # 实际执行
"""

import argparse
import logging
import os
import shutil
from collections import defaultdict

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("migrate")

BUCKET = "weather-ai-models-de08370c"
PREFIX = "processed/satellite-3ch/"
LOCAL_DIR = "/tmp/satellite-3ch-migrate"


def extract_date(filename: str) -> str | None:
    """SAT_B08_20200101_0000.npy → 20200101"""
    if not filename.startswith("SAT_"):
        return None
    parts = filename.split("_")
    return parts[2] if len(parts) >= 4 else None


def check_complete(s3, date: str) -> bool:
    """检查该天是否已有 .complete 标记"""
    try:
        s3.head_object(Bucket=BUCKET, Key=f"{PREFIX}{date}/.complete")
        return True
    except ClientError:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    s3 = boto3.client("s3")

    # ── Step 1: 找出 S3 上所有平铺文件 ──
    logger.info("📋 Listing flat files on S3...")
    flat_keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX):
        for obj in page.get("Contents", []):
            rel = obj["Key"][len(PREFIX):]
            if "/" not in rel and rel.startswith("SAT_"):
                flat_keys.append(obj["Key"])

    logger.info(f"   Found {len(flat_keys)} flat files in listing")

    if not flat_keys:
        logger.info("✅ No flat files remaining. Migration complete!")
        return

    # 按日期分组
    date_groups = defaultdict(list)
    for key in flat_keys:
        filename = key.rsplit("/", 1)[-1]
        date = extract_date(filename)
        if date:
            date_groups[date].append(key)

    # 过滤掉已有 .complete 的日期
    skip_count = 0
    dates_to_process = {}
    for date in sorted(date_groups):
        if check_complete(s3, date):
            skip_count += 1
        else:
            dates_to_process[date] = date_groups[date]

    logger.info(f"   {len(date_groups)} unique dates, {skip_count} already complete")
    logger.info(f"   {len(dates_to_process)} dates to process")

    if not args.execute:
        for date in sorted(dates_to_process)[:5]:
            logger.info(f"  DRY-RUN: {date} → {len(dates_to_process[date])} files")
        logger.info("🔍 DRY-RUN complete. Use --execute to run.")
        return

    # ── Step 2: 逐日期处理 ──
    total_dates = len(dates_to_process)
    total_moved = 0

    for idx, (date, keys) in enumerate(sorted(dates_to_process.items()), 1):
        local_dir = os.path.join(LOCAL_DIR, date)
        os.makedirs(local_dir, exist_ok=True)

        # 2a. 下载（404 = 已被之前的迁移移走，跳过）
        downloaded = []
        already_moved = 0
        errors = 0
        for key in keys:
            filename = key.rsplit("/", 1)[-1]
            local_path = os.path.join(local_dir, filename)
            try:
                s3.download_file(BUCKET, key, local_path)
                downloaded.append((key, local_path, filename))
            except ClientError as e:
                code = e.response["Error"].get("Code", "")
                if code in ("404", "NoSuchKey"):
                    already_moved += 1
                else:
                    logger.error(f"  ❌ Download error: {key}: {e}")
                    errors += 1

        # 2b. 上传到新路径
        uploaded = 0
        for old_key, local_path, filename in downloaded:
            new_key = f"{PREFIX}{date}/{filename}"
            try:
                s3.upload_file(local_path, BUCKET, new_key)
                uploaded += 1
            except Exception as e:
                logger.error(f"  ❌ Upload failed: {new_key}: {e}")
                errors += 1

        # 2c. 全部成功 → 写 .complete → 删旧平铺文件
        if errors == 0 and uploaded == len(downloaded):
            s3.put_object(Bucket=BUCKET, Key=f"{PREFIX}{date}/.complete", Body=b"")

            for old_key, _, _ in downloaded:
                s3.delete_object(Bucket=BUCKET, Key=old_key)

            total_moved += uploaded
            logger.info(
                f"[{idx}/{total_dates}] {date}: ✅ {uploaded} moved, "
                f"{already_moved} already migrated"
            )
        else:
            logger.warning(
                f"[{idx}/{total_dates}] {date}: ⚠️ {errors} errors, "
                f"skipping .complete (downloaded={len(downloaded)}, uploaded={uploaded})"
            )

        shutil.rmtree(local_dir, ignore_errors=True)

    shutil.rmtree(LOCAL_DIR, ignore_errors=True)
    logger.info(f"🏁 Done: {total_moved} files migrated across {total_dates} dates")


if __name__ == "__main__":
    main()
