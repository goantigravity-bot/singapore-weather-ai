"""
API Server 传感器数据管理器 — 从 S3 govdata 同步最近 N 天数据并生成 CSV。

职责:
  1. 从 S3 govdata/ 拉取最近 N 天的 JSON 到本地 govdata/
  2. 合并处理成 processed/real_sensor_data.csv
  3. 清理超过 N 天的旧文件

环境变量:
  SENSOR_DAYS: 保留天数，默认 7
  S3_BUCKET: S3 bucket 名称
"""
import os
import json
import csv
import logging
from datetime import datetime, timedelta, date
from collections import defaultdict
from pathlib import Path

import boto3
import pandas as pd

logger = logging.getLogger("sensor_data_manager")

# 6 种传感器数据类型，key = CSV 列名，value = JSON 文件名前缀
DATA_TYPES = {
    "rainfall": "rainfall",
    "temperature": "temperature",
    "humidity": "humidity",
    "pm25": "pm25",
    "wind_speed": "wind-speed",
    "wind_direction": "wind-direction",
}

CSV_COLUMNS = [
    "timestamp", "sensor_id",
    "humidity", "pm25", "rainfall", "temperature",
    "wind_speed", "wind_direction",
]

REGION_CENTROIDS = {
    "north": {"lat": 1.41803, "lon": 103.8200},
    "south": {"lat": 1.29587, "lon": 103.8200},
    "east": {"lat": 1.35735, "lon": 103.9400},
    "west": {"lat": 1.35735, "lon": 103.7000},
    "central": {"lat": 1.35735, "lon": 103.8200},
}


def _get_region(lat: float, lon: float) -> str:
    """根据经纬度找最近的 PM2.5 区域。"""
    best = "central"
    min_dist = float("inf")
    for region, c in REGION_CENTROIDS.items():
        d = ((lat - c["lat"]) ** 2 + (lon - c["lon"]) ** 2) ** 0.5
        if d < min_dist:
            min_dist = d
            best = region
    return best


def _build_station_region_map(s3, bucket: str, target_dates: list[date]) -> dict:
    """从 temperature JSON 的 metadata 提取 station → region 映射。"""
    # 用最新一天的 temperature 文件获取 station 元信息
    for d in reversed(target_dates):
        key = f"govdata/{d.year}/temperature_{d.isoformat()}.json"
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            data = json.loads(obj["Body"].read().decode("utf-8"))
            mapping = {}
            for s in data.get("metadata", {}).get("stations", []):
                loc = s.get("location", {})
                if "latitude" in loc:
                    mapping[s["id"]] = _get_region(loc["latitude"], loc["longitude"])
            if mapping:
                return mapping
        except Exception:
            continue
    return {}


def _parse_json(data: dict, dtype: str, station_region_map: dict) -> dict:
    """解析单个 JSON 内容，返回 {(timestamp, sensor_id): value}。

    支持两种 NEA API 格式:
      格式 A (rainfall / temperature / humidity): 顶层含 "items" 列表
      格式 B (wind-speed / wind-direction):       顶层含 "data" 字典,
                readings 在 data.readings 内, 站点 key 为 stationId
    """
    if not data:
        return {}

    result = {}

    # --- PM2.5: 区域级数据，映射到各站点 ---
    if dtype == "pm25":
        if "items" not in data:
            return {}
        for item in data["items"]:
            ts = item["timestamp"]
            pm25_data = item.get("readings", {}).get("pm25_one_hourly", {})
            for sid, region_key in station_region_map.items():
                if region_key in pm25_data:
                    result[(ts, sid)] = pm25_data[region_key]
        return result

    # --- 格式 B: wind-speed / wind-direction ---
    # { "code": 0, "data": { "readings": [{"timestamp": "...", "data": [{"stationId": "Sxx", "value": N}]}] } }
    if "data" in data and "items" not in data:
        data_section = data.get("data", {})
        if isinstance(data_section, dict):
            for reading_block in data_section.get("readings", []):
                ts = reading_block.get("timestamp", "")
                for r in reading_block.get("data", []):
                    sid = r.get("stationId")
                    val = r.get("value")
                    if sid and val is not None:
                        result[(ts, sid)] = val
        return result

    # --- 格式 A: rainfall / temperature / humidity ---
    if "items" not in data:
        return {}
    for item in data["items"]:
        ts = item["timestamp"]
        for r in item.get("readings", []):
            val = r.get("value")
            if val is not None:
                result[(ts, r["station_id"])] = val
    return result


def _process_day_from_local(
    govdata_dir: Path, target_date: date, station_region_map: dict
) -> list[dict]:
    """处理本地一天的 6 种 JSON，合并为 10 分钟重采样 CSV 行。"""
    date_str = target_date.isoformat()
    year = target_date.year

    type_data = {}
    for col_name, file_prefix in DATA_TYPES.items():
        json_path = govdata_dir / str(year) / f"{file_prefix}_{date_str}.json"
        if json_path.exists():
            with open(json_path, "r") as f:
                data = json.load(f)
            type_data[col_name] = _parse_json(data, col_name, station_region_map)
        else:
            type_data[col_name] = {}

    # 收集所有 (timestamp, sensor_id) 组合
    all_keys = set()
    for d in type_data.values():
        all_keys.update(d.keys())

    if not all_keys:
        return []

    rows = []
    for ts, sid in sorted(all_keys):
        row = {"timestamp": ts, "sensor_id": sid}
        has_data = False
        for col_name in DATA_TYPES:
            val = type_data[col_name].get((ts, sid))
            if val is not None:
                row[col_name] = val
                has_data = True
            else:
                # Use NaN so resampling mean ignores missing values
                row[col_name] = float("nan")
        if has_data:
            rows.append(row)

    if not rows:
        return []

    # 10 分钟重采样（NaN values are excluded from mean automatically）
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["ts_bucket"] = df["timestamp"].dt.floor("10min")
    agg_dict = {col: ("sum" if col == "rainfall" else "mean") for col in DATA_TYPES}
    resampled = df.groupby(["ts_bucket", "sensor_id"]).agg(agg_dict).reset_index()
    resampled.rename(columns={"ts_bucket": "timestamp"}, inplace=True)
    resampled["timestamp"] = resampled["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")

    # Only fill rainfall NaN → 0 (cumulative: no rain = 0 is semantically correct).
    # All other metrics keep NaN — the CSV writer converts them to empty string,
    # which Snowflake loads as NULL rather than 0.
    resampled["rainfall"] = resampled["rainfall"].fillna(0.0)

    return resampled.to_dict("records")


class SensorDataManager:
    """管理 API Server 的传感器数据同步、合并、清理。"""

    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir or os.getcwd())
        self.govdata_dir = self.base_dir / "govdata"
        self.processed_dir = self.base_dir / "processed"
        self.csv_path = self.processed_dir / "real_sensor_data.csv"

        self.sensor_days = int(os.environ.get("SENSOR_DAYS", "14"))
        self.bucket = os.environ.get("S3_BUCKET", "weather-ai-models-gcc")

        self.govdata_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        self._s3 = None

    @property
    def s3(self):
        if self._s3 is None:
            self._s3 = boto3.client("s3")
        return self._s3

    def get_target_dates(self) -> list[date]:
        """计算需要同步的日期列表（今天 + 前 N-1 天）。"""
        today = date.today()
        return [today - timedelta(days=i) for i in range(self.sensor_days)]

    def sync_from_s3(self) -> dict:
        """步骤 1: 从 S3 govdata/ 下载最近 N 天的 JSON 到本地。"""
        target_dates = self.get_target_dates()
        stats = {"downloaded": 0, "skipped": 0, "failed": 0}

        for d in target_dates:
            year_dir = self.govdata_dir / str(d.year)
            year_dir.mkdir(parents=True, exist_ok=True)

            for col_name, file_prefix in DATA_TYPES.items():
                filename = f"{file_prefix}_{d.isoformat()}.json"
                s3_key = f"govdata/{d.year}/{filename}"
                local_path = year_dir / filename

                # 跳过今天以外的已存在文件（今天的文件可能还在更新）
                if local_path.exists() and d != date.today():
                    stats["skipped"] += 1
                    continue

                try:
                    self.s3.download_file(self.bucket, s3_key, str(local_path))
                    stats["downloaded"] += 1
                except Exception as e:
                    # 今天的文件可能还没有上传
                    if d == date.today():
                        logger.debug(f"Today's file not yet available: {s3_key}")
                    else:
                        logger.warning(f"Failed to download {s3_key}: {e}")
                    stats["failed"] += 1

        logger.info(
            f"📥 S3 sync: downloaded={stats['downloaded']}, "
            f"skipped={stats['skipped']}, failed={stats['failed']}"
        )
        return stats

    def build_csv(self) -> Path:
        """步骤 2: 合并本地 govdata JSON 为 processed/real_sensor_data.csv。"""
        target_dates = self.get_target_dates()
        station_region_map = _build_station_region_map(
            self.s3, self.bucket, target_dates
        )

        all_rows = []
        for d in sorted(target_dates):
            rows = _process_day_from_local(
                self.govdata_dir, d, station_region_map
            )
            if rows:
                all_rows.extend(rows)
                logger.info(f"  {d.isoformat()}: {len(rows)} rows")
            else:
                logger.warning(f"  {d.isoformat()}: no data")

        if not all_rows:
            logger.error("No sensor data found for any day!")
            return self.csv_path

        # 写入 CSV — NaN 转为空字符串，Snowflake 加载时识别为 NULL
        with open(self.csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            for row in all_rows:
                clean_row = {
                    k: ("" if isinstance(v, float) and v != v  # NaN → NULL
                        else round(v, 2) if isinstance(v, float)  # round to 2dp
                        else v)
                    for k, v in row.items()
                }
                writer.writerow(clean_row)

        logger.info(f"✅ CSV generated: {self.csv_path} ({len(all_rows)} rows)")
        return self.csv_path

    def housekeep(self) -> dict:
        """步骤 3: 清理超过 N 天的本地 govdata 文件。"""
        cutoff = date.today() - timedelta(days=self.sensor_days)
        stats = {"deleted": 0}

        for year_dir in self.govdata_dir.iterdir():
            if not year_dir.is_dir():
                continue
            for json_file in year_dir.glob("*.json"):
                # 从文件名提取日期: rainfall_2026-02-17.json → 2026-02-17
                parts = json_file.stem.rsplit("_", 1)
                if len(parts) != 2:
                    continue
                try:
                    file_date = date.fromisoformat(parts[1])
                    if file_date < cutoff:
                        json_file.unlink()
                        stats["deleted"] += 1
                except ValueError:
                    continue

            # 删除空的年份目录
            if year_dir.is_dir() and not list(year_dir.iterdir()):
                year_dir.rmdir()

        if stats["deleted"] > 0:
            logger.info(f"🧹 Housekeep: deleted {stats['deleted']} old files")
        return stats

    def run(self) -> Path:
        """完整流程: sync → build CSV → housekeep。"""
        logger.info(
            f"🔄 Sensor data refresh: last {self.sensor_days} days, "
            f"bucket={self.bucket}"
        )
        self.sync_from_s3()
        csv_path = self.build_csv()
        self.housekeep()
        return csv_path


# 供命令行直接运行
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Sync sensor data from S3 and generate CSV"
    )
    parser.add_argument(
        "--days", type=int, default=None,
        help="Override SENSOR_DAYS env var"
    )
    parser.add_argument(
        "--base-dir", type=str, default=None,
        help="Base directory (default: current directory)"
    )
    args = parser.parse_args()

    if args.days:
        os.environ["SENSOR_DAYS"] = str(args.days)

    manager = SensorDataManager(base_dir=args.base_dir)
    csv_path = manager.run()
    print(f"\n📄 Output: {csv_path}")
