"""
Accuracy Backfill Test — 准确度验证工具

同一时刻获取模型预测值和 NEA 真实降雨值，配对写入 DB，
验证 forecast vs actual 闭环管道和 5 个 accuracy 端点。

用法:
    python3 accuracy-backfill-test.py                          # 执行回填 + 验证
    python3 accuracy-backfill-test.py --verify-only            # 仅验证端点
    python3 accuracy-backfill-test.py --cleanup                # 清除旧数据后重新回填
    python3 accuracy-backfill-test.py --rounds 3 --interval 60 # 3 轮，每轮间隔 60 秒
    python3 accuracy-backfill-test.py --api-url http://3.0.28.161:8000
"""
import argparse
import json
import logging
import math
import sys
import time
import urllib.request
import urllib.error
import ssl
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("accuracy-test")

# 跳过 SSL 验证（NEA API 有时证书有问题）
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# 10 个基准测试点（与 actual_collector.py 一致）
BENCHMARK_LOCATIONS = [
    {"name": "Newton",          "lat": 1.31055, "lon": 103.8365,  "station_id": "S111"},
    {"name": "Changi Airport",  "lat": 1.3678,  "lon": 103.9826,  "station_id": "S24"},
    {"name": "West Coast",      "lat": 1.281,   "lon": 103.754,   "station_id": "S116"},
    {"name": "Woodlands",       "lat": 1.44387, "lon": 103.78538, "station_id": "S104"},
    {"name": "Ang Mo Kio",      "lat": 1.3764,  "lon": 103.8492,  "station_id": "S109"},
    {"name": "Tuas South",      "lat": 1.2937,  "lon": 103.6182,  "station_id": "S115"},
    {"name": "Sentosa",         "lat": 1.25,    "lon": 103.8279,  "station_id": "S60"},
    {"name": "Choa Chu Kang",   "lat": 1.37288, "lon": 103.72244, "station_id": "S121"},
    {"name": "East Coast Park", "lat": 1.3135,  "lon": 103.9625,  "station_id": "S107"},
    {"name": "Clementi",        "lat": 1.3337,  "lon": 103.7768,  "station_id": "S50"},
]

MAX_MATCH_DISTANCE_KM = 2.0


def _normalize_timestamp(ts):
    """将带时区的 ISO 时间字符串转为 SQLite 兼容的 'YYYY-MM-DD HH:MM:SS' 格式"""
    if ts is None:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 尝试解析带时区的格式（如 2026-02-14T21:15:00+08:00）
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(ts, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    # 如果都解析不了，截断到前 19 字符（YYYY-MM-DDTHH:MM:SS）
    return ts[:19].replace("T", " ")


# ── HTTP helpers ──

def http_get(url, timeout=15):
    """简单的 GET 请求，返回 parsed JSON"""
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX)
    return json.loads(resp.read().decode())


# ── NEA 真实数据采集 ──

def fetch_nea_rainfall():
    """从 NEA API 获取最新降雨读数，返回 (readings_dict, stations_meta, obs_time)"""
    url = "https://api.data.gov.sg/v1/environment/rainfall"
    try:
        data = http_get(url)
        stations_meta = data.get("metadata", {}).get("stations", [])
        items = data.get("items", [])
        if not items:
            return {}, stations_meta, None

        latest = items[0]
        obs_time = latest.get("timestamp", datetime.utcnow().isoformat())
        readings = {}
        for r in latest.get("readings", []):
            readings[r["station_id"]] = r["value"]

        return readings, stations_meta, obs_time
    except Exception as e:
        logger.error("NEA API failed: %s", e)
        return {}, [], None


def haversine(lat1, lon1, lat2, lon2):
    """两点距离（km）"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearest_station(lat, lon, stations_meta):
    """找到 2km 内最近的 NEA 站点"""
    best_id, best_dist = None, float("inf")
    for s in stations_meta:
        try:
            slat = s["location"]["latitude"]
            slon = s["location"]["longitude"]
            dist = haversine(lat, lon, slat, slon)
            if dist < best_dist:
                best_dist = dist
                best_id = s["id"]
        except (KeyError, TypeError):
            continue
    if best_id and best_dist <= MAX_MATCH_DISTANCE_KM:
        return best_id, round(best_dist, 3)
    return None, None


# ── Predict API 调用 ──

def call_predict(api_url, lat, lon):
    """调用 /predict API 获取模型预测"""
    url = f"{api_url}/predict?lat={lat}&lon={lon}"
    try:
        return http_get(url)
    except Exception as e:
        logger.warning("Predict failed for (%.4f, %.4f): %s", lat, lon, e)
        return None


# ── DB 操作（直接 sqlite，脚本运行在 API 服务器上）──

def get_db_connection(db_path):
    """延迟导入 sqlite3，返回连接"""
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def cleanup_test_data(db_path):
    """清除之前的模拟/测试数据"""
    conn = get_db_connection(db_path)
    c = conn.cursor()

    # 清除所有 actual_result（测试数据和真实采集的都清）
    c.execute("DELETE FROM actual_result")
    actual_deleted = c.rowcount

    # 仅清除 backtest 来源的 forecast
    c.execute("DELETE FROM forecast_result WHERE source = 'backtest'")
    forecast_deleted = c.rowcount

    conn.commit()
    conn.close()
    logger.info("Cleanup: deleted %d actual_result, %d backtest forecast_result",
                actual_deleted, forecast_deleted)


def save_paired_result(db_path, loc, predicted, actual_rain, obs_time,
                       station_id, match_dist):
    """写入配对的 forecast_result + actual_result"""
    conn = get_db_connection(db_path)
    c = conn.cursor()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    place_name = f"backtest:{loc['name']}"

    # get_or_create place
    row = c.execute("SELECT place_id FROM place WHERE place_name = ?",
                    (place_name,)).fetchone()
    if row:
        place_id = row[0]
    else:
        c.execute("INSERT INTO place (place_name, place_type, center_lat, center_lon) "
                  "VALUES (?, 'point', ?, ?)",
                  (place_name, loc["lat"], loc["lon"]))
        place_id = c.lastrowid

    # get_or_create location
    row = c.execute("SELECT loc_id FROM location WHERE place_id = ? AND lat = ? AND lon = ?",
                    (place_id, loc["lat"], loc["lon"])).fetchone()
    if row:
        loc_id = row[0]
    else:
        c.execute("INSERT INTO location (place_id, lat, lon, point_index) VALUES (?, ?, ?, 1)",
                  (place_id, loc["lat"], loc["lon"]))
        loc_id = c.lastrowid

    # 写 forecast_result
    rainfall = predicted.get("rainfall", 0)
    status = predicted.get("status", "Unknown")
    confidence = predicted.get("confidence", 0.5)
    c.execute("""INSERT INTO forecast_result
                 (loc_id, rainfall_mm, status, confidence, is_risky, forecast_time, source)
                 VALUES (?, ?, ?, ?, ?, ?, 'backtest')""",
              (loc_id, rainfall, status, confidence,
               1 if rainfall >= 2.0 else 0, now_str))

    # 写 actual_result
    # SQLite julianday() 无法解析带时区的 ISO 格式（如 +08:00），
    # 需要转为 "YYYY-MM-DD HH:MM:SS" 格式才能正确做时间差 JOIN
    obs_time_naive = _normalize_timestamp(obs_time)
    c.execute("""INSERT INTO actual_result
                 (loc_id, actual_rainfall_mm, source, station_id, match_distance_km, observation_time)
                 VALUES (?, ?, ?, ?, ?, ?)""",
              (loc_id, actual_rain, f"NEA:{station_id}", station_id, match_dist, obs_time_naive))

    conn.commit()
    conn.close()
    return loc_id


# ── 验证 accuracy 端点 ──

ACCURACY_ENDPOINTS = [
    "/accuracy/summary",
    "/accuracy/by-hour",
    "/accuracy/by-location",
    "/accuracy/by-rain-level",
    "/accuracy/by-distance",
]


def verify_endpoints(api_url):
    """验证 5 个 accuracy 端点，返回 (pass_count, total)"""
    results = []
    for ep in ACCURACY_ENDPOINTS:
        url = f"{api_url}{ep}"
        try:
            data = http_get(url)
            # summary 返回 dict，其余返回 list
            if isinstance(data, dict):
                ok = data.get("sample_count", 0) > 0
                detail = "sample_count=%d, MAE=%.3f, Bias=%.3f" % (
                    data.get("sample_count", 0),
                    data.get("mae") or 0,
                    data.get("bias") or 0,
                ) if ok else "sample_count=0"
            elif isinstance(data, list):
                ok = len(data) > 0
                detail = "%d groups" % len(data)
            else:
                ok = False
                detail = "unexpected type"

            status = "✅" if ok else "❌"
            results.append((ep, ok, detail))
            logger.info("  %s %s — %s", status, ep, detail)

        except Exception as e:
            results.append((ep, False, str(e)))
            logger.error("  ❌ %s — %s", ep, e)

    passed = sum(1 for _, ok, _ in results if ok)
    return passed, len(results)


# ── 主流程 ──

def run_backfill(api_url, db_path):
    """单轮回填：获取预测 + NEA 真实值 → 配对写入"""
    logger.info("=" * 50)
    logger.info("Step 1: Fetch NEA real-time rainfall")
    readings, stations_meta, obs_time = fetch_nea_rainfall()
    if not readings:
        logger.error("No NEA data available, aborting")
        return 0
    logger.info("  NEA stations: %d, readings: %d, time: %s",
                len(stations_meta), len(readings), obs_time)

    logger.info("Step 2: Call /predict for %d benchmark locations", len(BENCHMARK_LOCATIONS))
    paired = 0

    for loc in BENCHMARK_LOCATIONS:
        # 找到最近的 NEA 站点
        station_id, match_dist = find_nearest_station(
            loc["lat"], loc["lon"], stations_meta)
        if station_id is None:
            logger.warning("  ⏭️ %s — no station within 2km", loc["name"])
            continue

        actual_rain = readings.get(station_id)
        if actual_rain is None:
            # 如果精准的 station_id 没有数据，用预设的 station_id 尝试
            actual_rain = readings.get(loc["station_id"])
        if actual_rain is None:
            logger.warning("  ⏭️ %s — no reading for station %s", loc["name"], station_id)
            continue

        # 调用 predict API
        predicted = call_predict(api_url, loc["lat"], loc["lon"])
        if predicted is None:
            continue

        # 写入配对数据
        save_paired_result(db_path, loc, predicted, actual_rain,
                           obs_time, station_id, match_dist)

        pred_rain = predicted.get("rainfall", 0)
        error = pred_rain - actual_rain
        logger.info("  ✅ %-16s  predicted=%.2f  actual=%.2f  error=%+.2f  station=%s (%.2fkm)",
                    loc["name"], pred_rain, actual_rain, error, station_id, match_dist)
        paired += 1

    logger.info("Step 2 complete: %d/%d locations paired", paired, len(BENCHMARK_LOCATIONS))
    return paired


def main():
    parser = argparse.ArgumentParser(
        description="Accuracy Backfill Test — verify forecast vs actual pipeline")
    parser.add_argument("--api-url", default="http://localhost:8000",
                        help="API server URL (default: http://localhost:8000)")
    parser.add_argument("--db", default="weather.db",
                        help="SQLite DB path (default: weather.db)")
    parser.add_argument("--verify-only", action="store_true",
                        help="Only verify accuracy endpoints, skip data insertion")
    parser.add_argument("--cleanup", action="store_true",
                        help="Clean old test data before backfill")
    parser.add_argument("--rounds", type=int, default=1,
                        help="Number of backfill rounds (default: 1)")
    parser.add_argument("--interval", type=int, default=30,
                        help="Seconds between rounds (default: 30)")

    args = parser.parse_args()

    print("=" * 56)
    print("  Accuracy Backfill Test")
    print(f"  API: {args.api_url}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 56)

    if args.cleanup:
        logger.info("Cleaning up old test data...")
        cleanup_test_data(args.db)

    if not args.verify_only:
        total_paired = 0
        for i in range(args.rounds):
            if i > 0:
                logger.info("Waiting %ds before round %d...", args.interval, i + 1)
                time.sleep(args.interval)
            logger.info("\n--- Round %d/%d ---", i + 1, args.rounds)
            paired = run_backfill(args.api_url, args.db)
            total_paired += paired

        print("\n" + "=" * 56)
        print(f"  Backfill complete: {total_paired} pairs across {args.rounds} round(s)")
        print("=" * 56)

    # 验证端点
    print("\nVerifying accuracy endpoints...")
    passed, total = verify_endpoints(args.api_url)
    print(f"\nResult: {passed}/{total} endpoints passed")

    if passed == total:
        print("✅ All accuracy endpoints working correctly!")
    else:
        print("⚠️  Some endpoints returned empty data")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
