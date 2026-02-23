"""
Forecast vs Actual 闭环 — 后台采集模块

两个职责：
1. 主动巡检（Backtest）：每 10 分钟对 10 个固定测试点做预测，生成 forecast_result
2. Actual 采集：扫描未配对的 forecast，调 NEA API 回采真实降雨值，写入 actual_result

设计原则：
- 后台线程运行，不阻塞 API 响应
- NEA API 每轮只调一次（批量获取所有站点数据）
- 站点匹配距离上限 2km，优先保证数据准确性
"""
import math
import time
import random
import logging
import threading
import requests
from datetime import datetime, timedelta, timezone

import db as weather_db

logger = logging.getLogger(__name__)

# ── 配置 ──

MAX_MATCH_DISTANCE_KM = 2.0
BACKTEST_INTERVAL_SEC = 600   # 10 分钟
COLLECT_INTERVAL_SEC = 300    # 5 分钟

# 10 个固定测试点：均在 NEA 站点 2km 内，地理分布覆盖全新加坡
BENCHMARK_LOCATIONS = [
    {"name": "Newton",         "lat": 1.31055, "lon": 103.8365,  "station_id": "S111"},
    {"name": "Changi Airport", "lat": 1.3678,  "lon": 103.9826,  "station_id": "S24"},
    {"name": "West Coast",     "lat": 1.281,   "lon": 103.754,   "station_id": "S116"},
    {"name": "Woodlands",      "lat": 1.44387, "lon": 103.78538, "station_id": "S104"},
    {"name": "Ang Mo Kio",     "lat": 1.3764,  "lon": 103.8492,  "station_id": "S109"},
    {"name": "Tuas South",     "lat": 1.2937,  "lon": 103.6182,  "station_id": "S115"},
    {"name": "Sentosa",        "lat": 1.25,    "lon": 103.8279,  "station_id": "S60"},
    {"name": "Choa Chu Kang",  "lat": 1.37288, "lon": 103.72244, "station_id": "S121"},
    {"name": "East Coast Park","lat": 1.3135,  "lon": 103.9625,  "station_id": "S107"},
    {"name": "Clementi",       "lat": 1.3337,  "lon": 103.7768,  "station_id": "S50"},
]


# ── 工具函数 ──

def haversine(lat1, lon1, lat2, lon2):
    """两点间的地表距离（km），Haversine 公式"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def random_offset(lat, lon, max_km=2.0):
    """在基准点周围随机偏移 0-max_km，模拟真实用户查询位置"""
    # sqrt 保证面积均匀分布
    dist_km = max_km * math.sqrt(random.random())
    bearing = random.uniform(0, 2 * math.pi)
    dlat = (dist_km * math.cos(bearing)) / 111.0
    dlon = (dist_km * math.sin(bearing)) / (111.0 * math.cos(math.radians(lat)))
    return round(lat + dlat, 6), round(lon + dlon, 6)


def fetch_nea_rainfall():
    """
    调用 NEA 实时降雨 API，返回 {station_id: rainfall_mm} 和站点元数据。
    单次调用即可获取全部 60+ 站点的最新读数。
    """
    url = "https://api.data.gov.sg/v1/environment/rainfall"
    try:
        resp = requests.get(url, timeout=10, verify=False)
        data = resp.json()

        stations_meta = data.get("metadata", {}).get("stations", [])
        items = data.get("items", [])
        if not items:
            return {}, stations_meta, None

        # 取最新一组读数
        latest = items[0]
        raw_ts = latest.get("timestamp", None)

        # NEA returns SGT with tz offset e.g. "2026-02-21T12:28:40+08:00".
        # SQLite julianday() cannot parse tz offsets, so we normalise to
        # a plain UTC isoformat string (the same format forecast_time uses).
        if raw_ts:
            try:
                from datetime import timezone as _tz
                import re as _re
                # Parse ISO 8601 with offset using datetime.fromisoformat (Py 3.11+)
                # or fallback regex strip for Py 3.10
                try:
                    parsed = datetime.fromisoformat(raw_ts)
                except ValueError:
                    # Strip timezone suffix and treat as SGT (+08:00)
                    clean = _re.sub(r'[+-]\d{2}:\d{2}$', '', raw_ts)
                    parsed = datetime.fromisoformat(clean).replace(
                        tzinfo=timezone(timedelta(hours=8))
                    )
                obs_time = parsed.astimezone(_tz.utc).replace(tzinfo=None).isoformat()
            except Exception:
                obs_time = datetime.utcnow().isoformat()
        else:
            obs_time = datetime.utcnow().isoformat()

        readings = {}
        for r in latest.get("readings", []):
            readings[r["station_id"]] = r["value"]

        return readings, stations_meta, obs_time

    except Exception as e:
        logger.error(f"Failed to fetch NEA rainfall: {e}")
        return {}, [], None


def find_nearest_station(lat, lon, stations_meta, max_km=MAX_MATCH_DISTANCE_KM):
    """
    在 NEA 站点列表中找到 max_km 内最近的站点。
    返回 (station_id, distance_km) 或 (None, None)。
    """
    best_id = None
    best_dist = float("inf")

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

    if best_id and best_dist <= max_km:
        return best_id, round(best_dist, 3)

    return None, None


# ── 主动巡检 (Backtest) ──

def run_backtest_cycle(predict_fn, model, df, stations_meta_model):
    """
    对 10 个基准点（含随机偏移）执行预测，写入 forecast_result。
    predict_fn: predict_ensemble 函数引用
    """
    if model is None or df is None or df.empty:
        logger.debug("Backtest skipped: model or data not ready")
        return 0

    target_time = df["timestamp"].max()
    count = 0

    for loc in BENCHMARK_LOCATIONS:
        try:
            # 随机偏移 0-2km
            test_lat, test_lon = random_offset(loc["lat"], loc["lon"], MAX_MATCH_DISTANCE_KM)

            # 执行预测
            raw = predict_fn(
                test_lat, test_lon, target_time,
                model, df, stations_meta_model, ensemble_size=3
            )
            if not raw:
                continue

            # 保存为 place + location + forecast_result
            # forecast_time 用当前时间（而非训练数据时间），确保 actual 匹配窗口正确
            place_name = f"backtest:{loc['name']}"
            place_id = weather_db.get_or_create_place(
                place_name=place_name, place_type="point",
                center_lat=loc["lat"], center_lon=loc["lon"]
            )
            loc_ids = weather_db.save_locations_for_place(
                place_id, [(test_lat, test_lon)]
            )
            weather_db.save_forecast_results(
                query_id=None,
                results=[{
                    "loc_id": loc_ids[0],
                    "rainfall_mm": raw.get("rainfall", 0),
                    "status": raw.get("status", "Unknown"),
                    "confidence": raw.get("confidence", 0.5),
                    "is_risky": raw.get("rainfall", 0) >= 2.0,
                    "response_time_ms": None,
                    "forecast_time": datetime.utcnow().isoformat(),
                }],
                source="backtest"
            )
            count += 1

        except Exception as e:
            logger.warning(f"Backtest failed for {loc['name']}: {e}")

    logger.info(f"Backtest cycle complete: {count}/{len(BENCHMARK_LOCATIONS)} points")
    return count


# ── Actual 采集 ──

def collect_actuals():
    """
    扫描未配对的 forecast，调 NEA API 采集真实降雨值。
    每轮只调一次 NEA API（批量获取所有站点），然后逐条匹配。
    """
    unmatched = weather_db.get_unmatched_forecasts(hours=2)
    if not unmatched:
        return 0

    readings, stations_meta, obs_time = fetch_nea_rainfall()
    if not readings or not obs_time:
        logger.debug("No NEA data available for matching")
        return 0

    matched = 0
    for forecast in unmatched:
        lat = forecast["lat"]
        lon = forecast["lon"]
        loc_id = forecast["loc_id"]

        station_id, dist_km = find_nearest_station(lat, lon, stations_meta)
        if station_id is None:
            continue

        actual_rainfall = readings.get(station_id)
        if actual_rainfall is None:
            continue

        weather_db.save_actual_result(
            loc_id=loc_id,
            actual_rainfall_mm=actual_rainfall,
            observation_time=obs_time,
            source=f"NEA:{station_id}",
            station_id=station_id,
            match_distance_km=dist_km,
        )
        matched += 1

    logger.info(f"Actual collection: matched {matched}/{len(unmatched)} forecasts")
    return matched


# ── 后台线程 ──

_collector_thread = None
_stop_event = threading.Event()


def start_collector(predict_fn, get_model_fn, get_df_fn, get_stations_fn):
    """
    启动后台采集线程。
    参数都是 callable，延迟获取以避免循环导入。
    """
    global _collector_thread
    if _collector_thread and _collector_thread.is_alive():
        logger.info("Collector thread already running")
        return

    def _loop():
        logger.info("Actual collector thread started")
        backtest_counter = 0

        while not _stop_event.is_set():
            try:
                # 每 5 分钟采集一次 actual
                collect_actuals()

                # 每 10 分钟做一次 backtest（每 2 个 collect 周期做一次）
                backtest_counter += 1
                if backtest_counter % 2 == 0:
                    model = get_model_fn()
                    df = get_df_fn()
                    stations = get_stations_fn()
                    if model and df is not None:
                        run_backtest_cycle(predict_fn, model, df, stations)

            except Exception as e:
                logger.error(f"Collector loop error: {e}")

            _stop_event.wait(COLLECT_INTERVAL_SEC)

    _collector_thread = threading.Thread(target=_loop, daemon=True, name="actual-collector")
    _collector_thread.start()


def stop_collector():
    """优雅停止采集线程"""
    _stop_event.set()
    if _collector_thread:
        _collector_thread.join(timeout=5)
    logger.info("Actual collector thread stopped")
