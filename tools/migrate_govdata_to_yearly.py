"""
将 S3 govdata/ 下的平铺 JSON 文件迁移到年份子目录。

迁移规则：
  govdata/rainfall_2024-02-15.json  →  govdata/2024/rainfall_2024-02-15.json

只处理文件名中含日期格式 YYYY-MM-DD 的平铺文件，跳过已在子目录的文件。
"""
import boto3
import logging
import re
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("migrate_govdata")

S3_BUCKET = "weather-ai-models-de08370c"
GOVDATA_PREFIX = "govdata/"
# 匹配平铺文件：govdata/xxx_YYYY-MM-DD.json（直接在 govdata/ 下，不含子目录斜杠）
FLAT_FILE_PATTERN = re.compile(r"^govdata/[^/]+_(\d{4})-\d{2}-\d{2}\.json$")


def get_s3_client():
    session = boto3.Session(profile_name="personal")
    return session.client("s3")


def list_flat_files(s3) -> list[str]:
    """列出 govdata/ 下所有平铺 JSON 文件（不包括子目录中的文件）。"""
    flat_files = []
    paginator = s3.get_paginator("list_objects_v2")
    logger.info("列举 govdata/ 下所有文件...")

    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=GOVDATA_PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if FLAT_FILE_PATTERN.match(key):
                flat_files.append(key)

    logger.info(f"发现 {len(flat_files)} 个需要迁移的平铺文件")
    return flat_files


def migrate_file(s3, src_key: str) -> bool:
    """将单个文件 copy 到年份子目录后 delete 原文件。"""
    match = FLAT_FILE_PATTERN.match(src_key)
    if not match:
        return False

    year = match.group(1)
    filename = src_key.split("/")[-1]
    dest_key = f"{GOVDATA_PREFIX}{year}/{filename}"

    # 若目标已存在则跳过，避免重复工作
    try:
        s3.head_object(Bucket=S3_BUCKET, Key=dest_key)
        logger.debug(f"⏭ 已存在，跳过：{dest_key}")
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] != "404":
            logger.error(f"检查目标文件时出错 {dest_key}: {e}")
            return False

    # Copy
    try:
        s3.copy_object(
            CopySource={"Bucket": S3_BUCKET, "Key": src_key},
            Bucket=S3_BUCKET,
            Key=dest_key,
        )
    except ClientError as e:
        logger.error(f"Copy 失败 {src_key} → {dest_key}: {e}")
        return False

    # Delete 原文件
    try:
        s3.delete_object(Bucket=S3_BUCKET, Key=src_key)
    except ClientError as e:
        logger.warning(f"Copy 成功但删除原文件失败 {src_key}: {e}")
        return False

    logger.debug(f"✅ {src_key} → {dest_key}")
    return True


def main():
    s3 = get_s3_client()
    flat_files = list_flat_files(s3)

    if not flat_files:
        logger.info("没有需要迁移的文件，退出。")
        return

    success = 0
    failed = 0

    for i, key in enumerate(flat_files, 1):
        if migrate_file(s3, key):
            success += 1
        else:
            failed += 1

        # 每 200 个文件打印一次进度
        if i % 200 == 0:
            logger.info(f"进度: {i}/{len(flat_files)} （成功 {success}，失败 {failed}）")

    logger.info(f"✅ 迁移完成：{success} 成功，{failed} 失败，共 {len(flat_files)} 个文件")


if __name__ == "__main__":
    main()
