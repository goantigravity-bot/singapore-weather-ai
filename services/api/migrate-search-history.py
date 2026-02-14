#!/usr/bin/env python3
"""
迁移脚本：将 search_history 中的历史数据迁移到新的 user_activity 表。
一次性运行。
"""
import sqlite3
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "weather.db"


def migrate():
    # 确保新表已创建
    import db as weather_db
    weather_db.DB_PATH = DB_PATH
    weather_db.create_tables()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 读取旧数据
    rows = c.execute("SELECT * FROM search_history ORDER BY id").fetchall()
    logger.info(f"Found {len(rows)} records in search_history")

    migrated = 0
    for row in rows:
        query = row["query"]
        ip_address = row["ip_address"]
        timestamp = row["timestamp"]
        response_time_ms = row["response_time_ms"] if "response_time_ms" in row.keys() else None
        response_result = row["response_result"] if "response_result" in row.keys() else None

        # 解析 response_result JSON 获取 forecast_outcome
        forecast_outcome = None
        if response_result:
            try:
                data = json.loads(response_result)
                forecast_outcome = data.get("recommendation") or data.get("advice") or data.get("overall_risk")
            except (json.JSONDecodeError, TypeError):
                pass

        # 检查是否已迁移（避免重复）
        existing = c.execute(
            "SELECT 1 FROM user_activity WHERE query = ? AND created_at = ?",
            (query, timestamp)
        ).fetchone()

        if existing:
            continue

        c.execute(
            "INSERT INTO user_activity (query, response_time_ms, forecast_outcome, ip_address, created_at) VALUES (?, ?, ?, ?, ?)",
            (query, response_time_ms, forecast_outcome, ip_address, timestamp)
        )
        migrated += 1

    conn.commit()
    conn.close()
    logger.info(f"Migrated {migrated} records to user_activity")


if __name__ == "__main__":
    migrate()
