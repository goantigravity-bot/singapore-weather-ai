"""
从 data.gov.sg 下载历史 NEA 传感器数据并上传到 S3 govdata/{year}/ 目录。

覆盖范围：2020-01-01 → 2024-02-14（约 1505 天）
数据类型：temperature, rainfall, humidity, pm25, wind-speed, wind-direction
S3 路径：govdata/{year}/{type}_{date}.json

支持环境变量覆盖日期范围：
  FETCH_START_DATE=2020-01-01
  FETCH_END_DATE=2024-02-14
"""
import boto3
import requests
import json
import logging
import os
import datetime
import time
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.expanduser("~/download/govdata_download.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("govdata_fetcher")

# --- 配置 ---
S3_BUCKET = "weather-ai-models-de08370c"
GOVDATA_PREFIX = "govdata"
BASE_URL = "https://api.data.gov.sg/v1/environment"

# 6 种传感器类型
DATA_TYPES = [
    "temperature",
    "rainfall",
    "humidity",
    "pm25",
    "wind-speed",
    "wind-direction",
]

API_ENDPOINTS = {
    "temperature": "air-temperature",
    "rainfall": "rainfall",
    "humidity": "relative-humidity",
    "pm25": "pm25",
    "wind-speed": "wind-speed",
    "wind-direction": "wind-direction",
}

# 默认日期范围（可通过环境变量覆盖）
DEFAULT_START = datetime.date(2020, 1, 1)
DEFAULT_END = datetime.date(2024, 2, 14)

# API 调用间隔（防止限流）
API_DELAY_SEC = 0.5


def get_s3_client():
    return boto3.client("s3")


def s3_key_exists(s3, key: str) -> bool:
    """检查 S3 key 是否已存在，用于跳过已下载的文件。"""
    try:
        s3.head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise


def fetch_data(date_str: str, type_key: str) -> dict | None:
    """从 data.gov.sg 获取单天单类型数据，返回原始 JSON 或 None。"""
    endpoint = API_ENDPOINTS[type_key]
    url = f"{BASE_URL}/{endpoint}"
    try:
        resp = requests.get(url, params={"date": date_str}, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"  [{type_key}] {date_str} 获取失败: {e}")
        return None


def upload_to_s3(s3, data: dict, s3_key: str) -> bool:
    """将 JSON 数据上传到 S3。"""
    try:
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=json.dumps(data, ensure_ascii=False),
            ContentType="application/json",
        )
        return True
    except ClientError as e:
        logger.error(f"  上传失败 {s3_key}: {e}")
        return False


def process_date(s3, date_obj: datetime.date) -> tuple[int, int]:
    """处理单天的所有数据类型，返回 (success, skip) 计数。"""
    date_str = date_obj.strftime("%Y-%m-%d")
    year = date_obj.strftime("%Y")
    success = 0
    skip = 0

    for type_key in DATA_TYPES:
        s3_key = f"{GOVDATA_PREFIX}/{year}/{type_key}_{date_str}.json"

        # 跳过已存在的文件
        if s3_key_exists(s3, s3_key):
            logger.debug(f"  ⏭ cached: {s3_key}")
            skip += 1
            continue

        # 拉取数据
        data = fetch_data(date_str, type_key)
        if data is None:
            continue

        # 上传
        if upload_to_s3(s3, data, s3_key):
            logger.debug(f"  ✅ {s3_key}")
            success += 1

        time.sleep(API_DELAY_SEC)

    return success, skip


def build_date_range(start: datetime.date, end: datetime.date) -> list[datetime.date]:
    dates = []
    current = start
    while current <= end:
        dates.append(current)
        current += datetime.timedelta(days=1)
    return dates


def main():
    # 支持环境变量覆盖
    start_str = os.environ.get("FETCH_START_DATE")
    end_str = os.environ.get("FETCH_END_DATE")
    start = datetime.date.fromisoformat(start_str) if start_str else DEFAULT_START
    end = datetime.date.fromisoformat(end_str) if end_str else DEFAULT_END

    logger.info(f"开始下载 NEA 历史传感器数据: {start} → {end}")
    logger.info(f"数据类型: {', '.join(DATA_TYPES)}")

    s3 = get_s3_client()
    date_list = build_date_range(start, end)
    total_days = len(date_list)

    total_success = 0
    total_skip = 0

    for i, date_obj in enumerate(date_list, 1):
        success, skip = process_date(s3, date_obj)
        total_success += success
        total_skip += skip

        # 每 50 天打印进度
        if i % 50 == 0 or i == total_days:
            logger.info(
                f"进度: {i}/{total_days} 天 | "
                f"已上传 {total_success} 个文件 | "
                f"已跳过 {total_skip} 个文件"
            )

    logger.info(
        f"✅ 完成！共处理 {total_days} 天，"
        f"上传 {total_success} 个文件，跳过 {total_skip} 个已存在文件。"
    )


if __name__ == "__main__":
    main()
