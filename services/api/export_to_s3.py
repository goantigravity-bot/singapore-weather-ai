"""
Export incremental SQLite data to S3 for Snowflake ingestion.

S3 structure:
  s3://{bucket}/2snowflake/{YYYY-MM-DD_HH-MM}/forecast_result.csv
  s3://{bucket}/2snowflake/{YYYY-MM-DD_HH-MM}/actual_result.csv
  s3://{bucket}/2snowflake/{YYYY-MM-DD_HH-MM}/user_activity.csv
  s3://{bucket}/2snowflake/{YYYY-MM-DD_HH-MM}/location.csv
  s3://{bucket}/2snowflake/{YYYY-MM-DD_HH-MM}/place.csv
  s3://{bucket}/2snowflake/stations.csv  (--init only)

Usage:
  # Normal 5-minute incremental run (called by cron):
  python3 export_to_s3.py

  # One-time station coordinate export:
  python3 export_to_s3.py --init
"""
import argparse
import csv
import hashlib
import io
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import boto3
import requests
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("export_to_s3")

# ── Config ─────────────────────────────────────────────────────────────────
S3_BUCKET = os.environ.get("S3_BUCKET", "weather-ai-models-de08370c")
S3_PREFIX = "2snowflake"
DB_PATH = os.environ.get("DB_PATH", "weather.db")
WINDOW_MINUTES = 5  # export window size

SGT = timezone(timedelta(hours=8))

NEA_RAINFALL_URL = "https://api.data.gov.sg/v1/environment/rainfall"


# ── Helpers ─────────────────────────────────────────────────────────────────

def get_s3():
    return boto3.client("s3")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_ip(ip: str | None) -> str | None:
    """SHA-256 hash of IP address for PII masking."""
    if not ip:
        return None
    return hashlib.sha256(ip.encode()).hexdigest()


def rows_to_csv(rows: list[sqlite3.Row], fieldnames: list[str]) -> str:
    """Serialise sqlite3.Row list to CSV string."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row[k] for k in fieldnames})
    return buf.getvalue()


def upload_csv(s3, key: str, content: str) -> None:
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=content.encode("utf-8"),
        ContentType="text/csv",
    )
    logger.info(f"Uploaded s3://{S3_BUCKET}/{key}")


# ── Window helpers ───────────────────────────────────────────────────────────

def current_window() -> tuple[datetime, datetime, str]:
    """
    Return (window_start, window_end, folder_name) for the last complete
    5-minute window, aligned to clock boundaries (00, 05, 10, ...).

    e.g. if now is 12:07 SGT → window 12:00 – 12:05, folder 2026-02-21_12-00
    """
    now = datetime.now(SGT)
    # floor to last completed window boundary
    floored_min = (now.minute // WINDOW_MINUTES) * WINDOW_MINUTES
    window_end = now.replace(minute=floored_min, second=0, microsecond=0)
    window_start = window_end - timedelta(minutes=WINDOW_MINUTES)
    folder = window_start.strftime("%Y-%m-%d_%H-%M")
    return window_start, window_end, folder


# ── Table exporters ──────────────────────────────────────────────────────────

def export_forecast_result(conn, window_start: datetime, window_end: datetime) -> str:
    """Export backtest forecast_result records in the window."""
    rows = conn.execute(
        """
        SELECT forecast_id, loc_id, rainfall_mm, status, confidence,
               is_risky, forecast_time, created_at
        FROM forecast_result
        WHERE source = 'backtest'
          AND created_at >= ?
          AND created_at < ?
        ORDER BY forecast_id
        """,
        (window_start.strftime("%Y-%m-%d %H:%M:%S"),
         window_end.strftime("%Y-%m-%d %H:%M:%S")),
    ).fetchall()
    return rows_to_csv(rows, [
        "forecast_id", "loc_id", "rainfall_mm", "status",
        "confidence", "is_risky", "forecast_time", "created_at",
    ])


def export_actual_result(conn, window_start: datetime, window_end: datetime) -> str:
    rows = conn.execute(
        """
        SELECT actual_id, loc_id, actual_rainfall_mm, station_id,
               match_distance_km, observation_time, created_at
        FROM actual_result
        WHERE created_at >= ?
          AND created_at < ?
        ORDER BY actual_id
        """,
        (window_start.strftime("%Y-%m-%d %H:%M:%S"),
         window_end.strftime("%Y-%m-%d %H:%M:%S")),
    ).fetchall()
    return rows_to_csv(rows, [
        "actual_id", "loc_id", "actual_rainfall_mm", "station_id",
        "match_distance_km", "observation_time", "created_at",
    ])


def export_user_activity(conn, window_start: datetime, window_end: datetime) -> str:
    rows = conn.execute(
        """
        SELECT query_id, query, response_time_ms, forecast_outcome,
               ip_address, created_at
        FROM user_activity
        WHERE created_at >= ?
          AND created_at < ?
        ORDER BY query_id
        """,
        (window_start.strftime("%Y-%m-%d %H:%M:%S"),
         window_end.strftime("%Y-%m-%d %H:%M:%S")),
    ).fetchall()

    # Write with hashed IP
    buf = io.StringIO()
    fields = ["query_id", "query", "response_time_ms",
              "forecast_outcome", "ip_address", "created_at"]
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({
            "query_id":        row["query_id"],
            "query":           row["query"],
            "response_time_ms": row["response_time_ms"],
            "forecast_outcome": row["forecast_outcome"],
            "ip_address":      hash_ip(row["ip_address"]),
            "created_at":      row["created_at"],
        })
    return buf.getvalue()


def export_location(conn) -> str:
    """Full export of location dimension table (slow-changing)."""
    rows = conn.execute(
        "SELECT loc_id, place_id, lat, lon FROM location ORDER BY loc_id"
    ).fetchall()
    return rows_to_csv(rows, ["loc_id", "place_id", "lat", "lon"])


def export_place(conn) -> str:
    """Full export of place dimension table (slow-changing)."""
    rows = conn.execute(
        "SELECT place_id, place_name, center_lat, center_lon FROM place ORDER BY place_id"
    ).fetchall()
    return rows_to_csv(rows, ["place_id", "place_name", "center_lat", "center_lon"])


# ── One-time station export ───────────────────────────────────────────────────

def export_stations(s3) -> None:
    """
    Fetch NEA station metadata from data.gov.sg and upload to
    s3://{bucket}/2snowflake/stations.csv (one-time, static).
    """
    logger.info("Fetching NEA station metadata...")
    try:
        resp = requests.get(NEA_RAINFALL_URL, timeout=10)
        resp.raise_for_status()
        stations = resp.json().get("metadata", {}).get("stations", [])
    except Exception as e:
        logger.error(f"Failed to fetch station metadata: {e}")
        sys.exit(1)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["station_id", "station_name", "lat", "lon"])
    writer.writeheader()
    for s in stations:
        writer.writerow({
            "station_id":   s["id"],
            "station_name": s["name"],
            "lat":          s["location"]["latitude"],
            "lon":          s["location"]["longitude"],
        })

    key = f"{S3_PREFIX}/stations.csv"
    upload_csv(s3, key, buf.getvalue())
    logger.info(f"Exported {len(stations)} stations → s3://{S3_BUCKET}/{key}")


# ── Main ──────────────────────────────────────────────────────────────────────

def run_incremental() -> None:
    window_start, window_end, folder = current_window()
    logger.info(
        f"Export window: {window_start.strftime('%Y-%m-%d %H:%M')} – "
        f"{window_end.strftime('%H:%M')} SGT → folder: {folder}"
    )

    s3 = get_s3()
    conn = get_db()

    exports = {
        "forecast_result": export_forecast_result(conn, window_start, window_end),
        "actual_result":   export_actual_result(conn, window_start, window_end),
        "user_activity":   export_user_activity(conn, window_start, window_end),
        "location":        export_location(conn),   # full dump (small, slow-changing)
        "place":           export_place(conn),       # full dump (small, slow-changing)
    }
    conn.close()

    base = f"{S3_PREFIX}/{folder}"
    total_rows = 0
    for table, csv_content in exports.items():
        lines = csv_content.count("\n") - 1  # exclude header
        if lines == 0:
            logger.info(f"  {table}: 0 new rows, skipping upload")
            continue
        upload_csv(s3, f"{base}/{table}.csv", csv_content)
        total_rows += lines
        logger.info(f"  {table}: {lines} rows")

    logger.info(f"Done. {total_rows} total rows exported to s3://{S3_BUCKET}/{base}/")


def main():
    parser = argparse.ArgumentParser(description="Export SQLite data to S3 for Snowflake")
    parser.add_argument(
        "--init",
        action="store_true",
        help="One-time export of NEA station coordinates to stations.csv",
    )
    args = parser.parse_args()

    if args.init:
        export_stations(get_s3())
    else:
        run_incremental()


if __name__ == "__main__":
    main()
