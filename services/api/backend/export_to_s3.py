"""
Dashboard 数据导出脚本：将 SQLite 数据库中的表导出为 CSV 并上传到 S3。
路径格式: s3://weather-ai-models-gcc/2snowflake/<YYYY-MM-DD_HH-MM>/

用法: python3 export_to_s3.py
"""
import os
import csv
import sqlite3
import logging
import boto3
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "/home/ubuntu/weather-ai/services/api/weather.db")
S3_BUCKET = os.environ.get("S3_BUCKET", "weather-ai-models-gcc")
EXPORT_DIR = "/tmp/snowflake_export"

# 每张表独立导出，表名即文件名
TABLES = [
    "user_activity",
    "place",
    "location",
    "activity",
    "forecast_result",
    "actual_result",
    "health_check",
]


def export_table_to_csv(db_path, table_name, output_path):
    """将单张表导出为 CSV，返回行数。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    rows = cursor.execute(f"SELECT * FROM {table_name}").fetchall()
    if not rows:
        logger.warning(f"  ⚠️ {table_name}: 空表，跳过")
        conn.close()
        return 0

    columns = rows[0].keys()
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(list(row))

    conn.close()
    return len(rows)


def upload_to_s3(local_path, s3_key):
    """上传文件到 S3。"""
    s3 = boto3.client("s3")
    s3.upload_file(local_path, S3_BUCKET, s3_key)


def main():
    # 时间戳目录名与已有格式保持一致: YYYY-MM-DD_HH-MM
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    s3_prefix = f"2snowflake/{ts}"

    os.makedirs(EXPORT_DIR, exist_ok=True)

    if not os.path.exists(DB_PATH):
        logger.error(f"❌ 数据库不存在: {DB_PATH}")
        return

    logger.info(f"📦 开始导出 → s3://{S3_BUCKET}/{s3_prefix}/")
    logger.info(f"   数据库: {DB_PATH}")

    total_rows = 0
    exported_files = []

    for table in TABLES:
        csv_filename = f"{table}.csv"
        local_path = os.path.join(EXPORT_DIR, csv_filename)
        s3_key = f"{s3_prefix}/{csv_filename}"

        row_count = export_table_to_csv(DB_PATH, table, local_path)
        if row_count == 0:
            continue

        file_size = os.path.getsize(local_path)
        upload_to_s3(local_path, s3_key)

        total_rows += row_count
        exported_files.append(csv_filename)
        logger.info(f"  ✅ {table}: {row_count} rows ({file_size/1024:.1f} KB) → {s3_key}")

    # stations.csv 更新到顶层（不变）
    stations_path = os.path.join(EXPORT_DIR, "stations.csv")
    try:
        import requests
        url = "https://api.data.gov.sg/v1/environment/rainfall"
        resp = requests.get(url, timeout=10, verify=False)
        stations = resp.json().get("metadata", {}).get("stations", [])
        if stations:
            with open(stations_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["station_id", "station_name", "lat", "lon"])
                for s in stations:
                    writer.writerow([
                        s["id"], s["name"],
                        s["location"]["latitude"], s["location"]["longitude"]
                    ])
            upload_to_s3(stations_path, "2snowflake/stations.csv")
            logger.info(f"  ✅ stations: {len(stations)} stations → 2snowflake/stations.csv")
    except Exception as e:
        logger.warning(f"  ⚠️ stations.csv 更新失败: {e}")

    logger.info(f"\n🎉 导出完成: {len(exported_files)} 文件, {total_rows} 总行数")
    logger.info(f"   S3 路径: s3://{S3_BUCKET}/{s3_prefix}/")


if __name__ == "__main__":
    main()
