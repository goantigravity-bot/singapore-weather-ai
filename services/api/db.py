"""
Weather AI - Database Module
结构化存储用户查询、地点、预测结果、实际结果。
"""
import json
import sqlite3
import logging
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_PATH = "weather.db"


@contextmanager
def get_db():
    """线程安全的数据库连接上下文管理器"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_tables():
    """创建所有表（幂等，IF NOT EXISTS）"""
    with get_db() as conn:
        c = conn.cursor()

        # 保留原 search_history 表不动，新增以下 5 张表

        c.execute("""
            CREATE TABLE IF NOT EXISTS user_activity (
                query_id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                response_time_ms REAL,
                forecast_outcome TEXT,
                ip_address TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS place (
                place_id INTEGER PRIMARY KEY AUTOINCREMENT,
                place_name TEXT NOT NULL,
                place_type TEXT DEFAULT 'point',
                center_lat REAL,
                center_lon REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(place_name)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS location (
                loc_id INTEGER PRIMARY KEY AUTOINCREMENT,
                place_id INTEGER NOT NULL,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                point_index INTEGER,
                label TEXT,
                FOREIGN KEY (place_id) REFERENCES place(place_id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS activity (
                activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_id INTEGER NOT NULL,
                activity_name TEXT NOT NULL,
                rain_tolerance REAL,
                FOREIGN KEY (query_id) REFERENCES user_activity(query_id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS forecast_result (
                forecast_id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_id INTEGER,
                loc_id INTEGER,
                rainfall_mm REAL,
                status TEXT,
                confidence REAL,
                is_risky INTEGER DEFAULT 0,
                response_time_ms REAL,
                forecast_time DATETIME,
                source TEXT DEFAULT 'user',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (query_id) REFERENCES user_activity(query_id),
                FOREIGN KEY (loc_id) REFERENCES location(loc_id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS actual_result (
                actual_id INTEGER PRIMARY KEY AUTOINCREMENT,
                loc_id INTEGER NOT NULL,
                actual_rainfall_mm REAL,
                source TEXT DEFAULT 'NEA',
                station_id TEXT,
                match_distance_km REAL,
                observation_time DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (loc_id) REFERENCES location(loc_id)
            )
        """)

        # 跨 worker 共享的地理编码缓存，持久化到磁盘避免冷启动
        c.execute("""
            CREATE TABLE IF NOT EXISTS geocode_cache (
                address TEXT PRIMARY KEY,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 跨 worker 共享的 Overpass API 缓存，路径数据以 JSON 存储
        c.execute("""
            CREATE TABLE IF NOT EXISTS overpass_cache (
                query TEXT PRIMARY KEY,
                data_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 查询优化索引
        c.execute("CREATE INDEX IF NOT EXISTS idx_location_place ON location(place_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_forecast_query ON forecast_result(query_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_forecast_loc ON forecast_result(loc_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_actual_loc ON actual_result(loc_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_actual_time ON actual_result(observation_time)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_forecast_time ON forecast_result(forecast_time)")

        # 迁移：为已存在的表添加新列（ALTER TABLE 是幂等安全的，列已存在会忽略）
        for stmt in [
            "ALTER TABLE forecast_result ADD COLUMN source TEXT DEFAULT 'user'",
            "ALTER TABLE actual_result ADD COLUMN station_id TEXT",
            "ALTER TABLE actual_result ADD COLUMN match_distance_km REAL",
        ]:
            try:
                c.execute(stmt)
            except sqlite3.OperationalError:
                pass  # 列已存在，忽略

    logger.info("Database tables initialized")


def get_or_create_place(place_name, place_type="point", center_lat=None, center_lon=None):
    """获取已有 place 或创建新的，返回 place_id"""
    with get_db() as conn:
        c = conn.cursor()
        row = c.execute(
            "SELECT place_id FROM place WHERE place_name = ?",
            (place_name,)
        ).fetchone()

        if row:
            return row["place_id"]

        c.execute(
            "INSERT INTO place (place_name, place_type, center_lat, center_lon) VALUES (?, ?, ?, ?)",
            (place_name, place_type, center_lat, center_lon)
        )
        return c.lastrowid


def save_locations_for_place(place_id, points):
    """
    批量保存路径/区域的坐标点。
    points: list of (lat, lon) 或 list of dict with lat, lon, point_index, label
    返回 loc_id 列表。
    """
    loc_ids = []
    with get_db() as conn:
        c = conn.cursor()
        for i, pt in enumerate(points):
            if isinstance(pt, dict):
                lat, lon = pt["lat"], pt["lon"]
                idx = pt.get("point_index", i + 1)
                label = pt.get("label")
            else:
                lat, lon = pt[0], pt[1]
                idx = i + 1
                label = None

            # 避免重复：同一 place 下相同坐标不重复插入
            existing = c.execute(
                "SELECT loc_id FROM location WHERE place_id = ? AND lat = ? AND lon = ?",
                (place_id, round(lat, 6), round(lon, 6))
            ).fetchone()

            if existing:
                loc_ids.append(existing["loc_id"])
            else:
                c.execute(
                    "INSERT INTO location (place_id, lat, lon, point_index, label) VALUES (?, ?, ?, ?, ?)",
                    (place_id, round(lat, 6), round(lon, 6), idx, label)
                )
                loc_ids.append(c.lastrowid)

    return loc_ids


def save_user_activity(query, response_time_ms, forecast_outcome, ip_address=None):
    """保存用户查询记录，返回 query_id"""
    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO user_activity (query, response_time_ms, forecast_outcome, ip_address) VALUES (?, ?, ?, ?)",
            (query, response_time_ms, forecast_outcome, ip_address)
        )
        return c.lastrowid


def save_activity(query_id, activity_name, rain_tolerance=None):
    """保存活动记录"""
    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO activity (query_id, activity_name, rain_tolerance) VALUES (?, ?, ?)",
            (query_id, activity_name, rain_tolerance)
        )
        return c.lastrowid


def save_forecast_results(query_id, results, source="user"):
    """
    批量保存预测结果。
    results: list of dict with loc_id, rainfall_mm, status, confidence, is_risky, response_time_ms, forecast_time
    source: 'user' (用户查询) 或 'backtest' (主动巡检)
    """
    with get_db() as conn:
        c = conn.cursor()
        for r in results:
            c.execute(
                """INSERT INTO forecast_result
                   (query_id, loc_id, rainfall_mm, status, confidence, is_risky, response_time_ms, forecast_time, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    query_id,
                    r.get("loc_id"),
                    r.get("rainfall_mm"),
                    r.get("status"),
                    r.get("confidence"),
                    1 if r.get("is_risky") else 0,
                    r.get("response_time_ms"),
                    r.get("forecast_time"),
                    source,
                )
            )


def save_actual_result(loc_id, actual_rainfall_mm, observation_time,
                       source="NEA", station_id=None, match_distance_km=None):
    """保存实际观测结果，附带匹配站点信息以追溯数据质量"""
    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            """INSERT INTO actual_result
               (loc_id, actual_rainfall_mm, source, station_id, match_distance_km, observation_time)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (loc_id, actual_rainfall_mm, source, station_id, match_distance_km, observation_time)
        )
        return c.lastrowid


# ── Forecast vs Actual 闭环查询 ──

def get_unmatched_forecasts(hours=2):
    """获取最近 N 小时内尚未配对 actual 的 forecast 记录"""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT f.forecast_id, f.loc_id, f.rainfall_mm, f.forecast_time,
                   f.confidence, f.source,
                   l.lat, l.lon
            FROM forecast_result f
            JOIN location l ON f.loc_id = l.loc_id
            LEFT JOIN actual_result a ON f.loc_id = a.loc_id
                AND ABS(julianday(f.forecast_time) - julianday(a.observation_time)) < 0.021
            WHERE a.actual_id IS NULL
              AND f.forecast_time >= datetime('now', ? || ' hours')
              AND f.forecast_time <= datetime('now')
        """, (f"-{hours}",)).fetchall()
        return [dict(r) for r in rows]


def get_accuracy_summary():
    """总体准确度概览：MAE、bias、样本数、匹配率"""
    with get_db() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*) AS sample_count,
                AVG(ABS(f.rainfall_mm - a.actual_rainfall_mm)) AS mae,
                AVG(f.rainfall_mm - a.actual_rainfall_mm) AS bias,
                AVG(a.match_distance_km) AS avg_match_distance_km
            FROM forecast_result f
            JOIN actual_result a ON f.loc_id = a.loc_id
                AND ABS(julianday(f.forecast_time) - julianday(a.observation_time)) < 0.021
        """).fetchone()
        total = conn.execute("SELECT COUNT(*) AS cnt FROM forecast_result").fetchone()
        result = dict(row)
        result["total_forecasts"] = total["cnt"]
        result["match_rate"] = round(result["sample_count"] / max(total["cnt"], 1), 4)
        return result


def get_accuracy_by_hour():
    """按小时聚合的 MAE 和 bias — 发现哪个时段预测最不准"""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                CAST(strftime('%H', f.forecast_time) AS INTEGER) AS hour,
                COUNT(*) AS count,
                AVG(ABS(f.rainfall_mm - a.actual_rainfall_mm)) AS mae,
                AVG(f.rainfall_mm - a.actual_rainfall_mm) AS bias
            FROM forecast_result f
            JOIN actual_result a ON f.loc_id = a.loc_id
                AND ABS(julianday(f.forecast_time) - julianday(a.observation_time)) < 0.021
            GROUP BY hour
            ORDER BY hour
        """).fetchall()
        return [dict(r) for r in rows]


def get_accuracy_by_location():
    """按地点聚合的 MAE — 发现哪个区域预测最不准"""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                p.place_name,
                COUNT(*) AS count,
                AVG(ABS(f.rainfall_mm - a.actual_rainfall_mm)) AS mae,
                AVG(f.rainfall_mm - a.actual_rainfall_mm) AS bias
            FROM forecast_result f
            JOIN actual_result a ON f.loc_id = a.loc_id
                AND ABS(julianday(f.forecast_time) - julianday(a.observation_time)) < 0.021
            JOIN location l ON f.loc_id = l.loc_id
            JOIN place p ON l.place_id = p.place_id
            GROUP BY p.place_name
            ORDER BY mae DESC
        """).fetchall()
        return [dict(r) for r in rows]


def get_accuracy_by_rain_level():
    """按降雨量级聚合 — 发现模型对哪种雨量预测偏差最大"""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                CASE
                    WHEN a.actual_rainfall_mm < 0.5 THEN 'No Rain'
                    WHEN a.actual_rainfall_mm < 2.0 THEN 'Light'
                    WHEN a.actual_rainfall_mm < 10.0 THEN 'Moderate'
                    ELSE 'Heavy'
                END AS rain_level,
                COUNT(*) AS count,
                AVG(ABS(f.rainfall_mm - a.actual_rainfall_mm)) AS mae,
                AVG(f.rainfall_mm - a.actual_rainfall_mm) AS bias
            FROM forecast_result f
            JOIN actual_result a ON f.loc_id = a.loc_id
                AND ABS(julianday(f.forecast_time) - julianday(a.observation_time)) < 0.021
            GROUP BY rain_level
            ORDER BY mae DESC
        """).fetchall()
        return [dict(r) for r in rows]


def get_accuracy_by_distance():
    """按匹配距离分桶 — 验证 2km 阈值是否合理"""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                CASE
                    WHEN a.match_distance_km < 0.5 THEN '0-0.5km'
                    WHEN a.match_distance_km < 1.0 THEN '0.5-1km'
                    WHEN a.match_distance_km < 1.5 THEN '1-1.5km'
                    ELSE '1.5-2km'
                END AS distance_bin,
                COUNT(*) AS count,
                AVG(ABS(f.rainfall_mm - a.actual_rainfall_mm)) AS mae,
                AVG(f.rainfall_mm - a.actual_rainfall_mm) AS bias
            FROM forecast_result f
            JOIN actual_result a ON f.loc_id = a.loc_id
                AND ABS(julianday(f.forecast_time) - julianday(a.observation_time)) < 0.021
            WHERE a.match_distance_km IS NOT NULL
            GROUP BY distance_bin
            ORDER BY distance_bin
        """).fetchall()
        return [dict(r) for r in rows]


# ── Geocode Cache（跨 worker 共享） ──

def get_geocode_cache(address):
    """查询缓存，命中返回 (lat, lon)，未命中返回 None"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT lat, lon FROM geocode_cache WHERE address = ?",
            (address,)
        ).fetchone()
        if row:
            return row["lat"], row["lon"]
    return None


def set_geocode_cache(address, lat, lon):
    """写入缓存（INSERT OR IGNORE 防止并发冲突）"""
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO geocode_cache (address, lat, lon) VALUES (?, ?, ?)",
            (address, lat, lon)
        )


# ── Overpass Cache（跨 worker 共享） ──

def get_overpass_cache(query):
    """查询缓存，命中返回 dict，未命中返回 None"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT data_json FROM overpass_cache WHERE query = ?",
            (query,)
        ).fetchone()
        if row:
            return json.loads(row["data_json"])
    return None


def set_overpass_cache(query, data):
    """写入缓存（INSERT OR IGNORE 防止并发冲突）"""
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO overpass_cache (query, data_json) VALUES (?, ?)",
            (query, json.dumps(data))
        )
