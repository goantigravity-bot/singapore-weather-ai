"""
Performance test script for Singapore Weather AI API.

Simulates realistic user traffic to generate dashboard data:
- Forecast Performance (rainfall distribution across locations)
- Service Availability (health check success rates)
- Popular Places (weighted search distribution)
- Response Time (p50/p95/p99 percentiles)

Supports two modes:
  --requests N     : run exactly N requests then stop
  --duration M     : run continuously for M minutes

Loads locations from external JSON data file for reusability.

Usage:
    # Duration-based (10 minutes)
    python3 perf-test.py --duration 10

    # Request-count based
    python3 perf-test.py --requests 200

    # Custom data file
    python3 perf-test.py --duration 10 --data my-locations.json
"""

import argparse
import json
import logging
import os
import random
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests


class SystemMetricsCollector:
    """后台线程采集 CPU/内存/磁盘/网络指标，通过 /proc 直接读取避免外部依赖"""

    def __init__(self, interval: int = 15):
        self.interval = interval
        self.samples: list[dict] = []
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # 网络基线（用于计算增量）
        self._prev_net = self._read_net_bytes()
        self._prev_time = time.time()

    def start(self):
        self._thread = threading.Thread(target=self._collect_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _collect_loop(self):
        while not self._stop_event.is_set():
            try:
                sample = self._take_sample()
                self.samples.append(sample)
            except Exception as e:
                logger.warning(f"Metrics collection error: {e}")
            self._stop_event.wait(self.interval)

    def _take_sample(self) -> dict:
        now = time.time()
        sample = {"timestamp": datetime.now().strftime("%H:%M:%S")}

        # CPU: 从 /proc/stat 计算利用率
        try:
            cpu1 = self._read_cpu_times()
            time.sleep(0.5)
            cpu2 = self._read_cpu_times()
            idle_delta = cpu2["idle"] - cpu1["idle"]
            total_delta = cpu2["total"] - cpu1["total"]
            sample["cpu_pct"] = round((1 - idle_delta / total_delta) * 100, 1) if total_delta > 0 else 0
        except Exception:
            sample["cpu_pct"] = None

        # Memory: 从 /proc/meminfo 读取
        try:
            meminfo = self._read_meminfo()
            total = meminfo.get("MemTotal", 0)
            available = meminfo.get("MemAvailable", 0)
            used = total - available
            sample["mem_total_mb"] = round(total / 1024, 0)
            sample["mem_used_mb"] = round(used / 1024, 0)
            sample["mem_pct"] = round(used / total * 100, 1) if total > 0 else 0
        except Exception:
            sample["mem_total_mb"] = None
            sample["mem_used_mb"] = None
            sample["mem_pct"] = None

        # Disk: 使用 os.statvfs
        try:
            st = os.statvfs("/")
            total_bytes = st.f_blocks * st.f_frsize
            free_bytes = st.f_bfree * st.f_frsize
            used_bytes = total_bytes - free_bytes
            sample["disk_total_gb"] = round(total_bytes / (1024**3), 1)
            sample["disk_used_gb"] = round(used_bytes / (1024**3), 1)
            sample["disk_pct"] = round(used_bytes / total_bytes * 100, 1) if total_bytes > 0 else 0
        except Exception:
            sample["disk_total_gb"] = None
            sample["disk_used_gb"] = None
            sample["disk_pct"] = None

        # Network: 从 /proc/net/dev 计算吞吐量
        try:
            net = self._read_net_bytes()
            dt = now - self._prev_time
            if dt > 0:
                rx_rate = (net["rx"] - self._prev_net["rx"]) / dt
                tx_rate = (net["tx"] - self._prev_net["tx"]) / dt
                sample["net_rx_kbps"] = round(rx_rate / 1024, 1)
                sample["net_tx_kbps"] = round(tx_rate / 1024, 1)
            self._prev_net = net
            self._prev_time = now
        except Exception:
            sample["net_rx_kbps"] = None
            sample["net_tx_kbps"] = None

        return sample

    @staticmethod
    def _read_cpu_times() -> dict:
        with open("/proc/stat") as f:
            line = f.readline()
        parts = line.split()
        # user, nice, system, idle, iowait, irq, softirq, steal
        values = [int(x) for x in parts[1:9]]
        idle = values[3] + values[4]  # idle + iowait
        total = sum(values)
        return {"idle": idle, "total": total}

    @staticmethod
    def _read_meminfo() -> dict:
        result = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if parts[0].rstrip(":") in ("MemTotal", "MemAvailable", "MemFree", "Buffers", "Cached"):
                    result[parts[0].rstrip(":")] = int(parts[1])  # in kB
        return result

    @staticmethod
    def _read_net_bytes() -> dict:
        """汇总所有非 lo 接口的收发字节数"""
        rx_total, tx_total = 0, 0
        try:
            with open("/proc/net/dev") as f:
                for line in f:
                    if ":" not in line or "lo:" in line:
                        continue
                    parts = line.split()
                    rx_total += int(parts[1])
                    tx_total += int(parts[9])
        except Exception:
            pass
        return {"rx": rx_total, "tx": tx_total}

    def get_summary(self) -> dict:
        """生成系统指标汇总，包含时间序列和统计摘要"""
        if not self.samples:
            return {"error": "No system metrics collected"}

        cpu_vals = [s["cpu_pct"] for s in self.samples if s.get("cpu_pct") is not None]
        mem_vals = [s["mem_pct"] for s in self.samples if s.get("mem_pct") is not None]

        summary = {}
        if cpu_vals:
            summary["cpu"] = {
                "avg_pct": round(statistics.mean(cpu_vals), 1),
                "max_pct": round(max(cpu_vals), 1),
                "min_pct": round(min(cpu_vals), 1),
            }
        if mem_vals:
            summary["memory"] = {
                "avg_pct": round(statistics.mean(mem_vals), 1),
                "max_pct": round(max(mem_vals), 1),
                "min_pct": round(min(mem_vals), 1),
            }

        return {
            "summary": summary,
            "sample_interval_s": self.interval,
            "total_samples": len(self.samples),
            "time_series": self.samples,
        }

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 新加坡坐标范围
SG_LAT_RANGE = (1.22, 1.47)
SG_LON_RANGE = (103.62, 104.05)

# 默认内置地点（当无外部数据文件时使用）
DEFAULT_LOCATIONS = [
    {"name": "Marina Bay Sands", "weight": 15},
    {"name": "Sentosa", "weight": 12},
    {"name": "Orchard Road", "weight": 10},
    {"name": "Changi Airport", "weight": 10},
    {"name": "Gardens by the Bay", "weight": 9},
    {"name": "East Coast Park", "weight": 8},
    {"name": "Jurong East", "weight": 5},
    {"name": "Ang Mo Kio", "weight": 5},
    {"name": "Tampines", "weight": 5},
    {"name": "Woodlands", "weight": 4},
]


class TestData:
    """从 JSON 数据文件加载可复用的测试地点和查询模板"""

    def __init__(self, data_file: Optional[str] = None):
        self.locations = []
        self.query_templates = []
        self.time_slots = []

        if data_file and Path(data_file).exists():
            self._load_from_file(data_file)
            logger.info(f"📂 Loaded {len(self.locations)} locations from {data_file}")
        else:
            self._use_defaults()
            logger.info(f"📂 Using {len(self.locations)} built-in locations")

    def _load_from_file(self, data_file: str):
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        for loc in data.get("locations", []):
            # 按类别赋予权重：热门地标 > 海滩公园 > 自然步道 > 一般公园
            category_weights = {
                "attraction": 15,
                "beach_park": 10,
                "garden": 8,
                "nature_trail": 6,
                "park": 5,
                "island": 3,
            }
            weight = category_weights.get(loc.get("category", "park"), 5)
            self.locations.append({
                "name": loc["name"],
                "lat": loc.get("lat"),
                "lon": loc.get("lon"),
                "weight": weight,
                "activities": loc.get("activities", []),
                "category": loc.get("category", "park"),
            })

        self.query_templates = data.get("query_templates", [
            "Will it rain at {location} {time_desc}?",
            "Weather at {location} {time_desc}",
        ])
        self.time_slots = data.get("time_slots", [
            {"desc": "today", "hour_start": 6, "hour_end": 21},
            {"desc": "now", "hour_start": None, "hour_end": None},
        ])

    def _use_defaults(self):
        self.locations = [
            {**loc, "activities": [], "category": "general"}
            for loc in DEFAULT_LOCATIONS
        ]
        self.query_templates = [
            "Will it rain at {location} {time_desc}?",
            "Should I bring umbrella to {location} {time_desc}?",
            "Weather at {location} {time_desc}",
        ]
        self.time_slots = [
            {"desc": "today"},
            {"desc": "now"},
            {"desc": "this afternoon"},
        ]

    def pick_location(self) -> dict:
        """按权重随机选取一个地点"""
        names = self.locations
        weights = [loc["weight"] for loc in names]
        return random.choices(names, weights=weights, k=1)[0]

    def build_smart_query(self) -> tuple[str, str]:
        """构造一条自然语言查询，返回 (query_text, location_name)"""
        loc = self.pick_location()
        template = random.choice(self.query_templates)
        time_slot = random.choice(self.time_slots)
        activity = random.choice(loc["activities"]) if loc["activities"] else "outdoor activity"

        query = template.format(
            location=loc["name"],
            time_desc=time_slot.get("desc", "today"),
            activity=activity,
        )
        return query, loc["name"]


class PerfResult:
    """单次请求的结果记录"""

    def __init__(
        self,
        endpoint: str,
        status_code: int,
        response_time_ms: float,
        success: bool,
        forecast_status: Optional[str] = None,
        location: Optional[str] = None,
        error: Optional[str] = None,
    ):
        self.endpoint = endpoint
        self.status_code = status_code
        self.response_time_ms = response_time_ms
        self.success = success
        self.forecast_status = forecast_status
        self.location = location
        self.error = error


def random_coordinates() -> tuple[float, float]:
    lat = random.uniform(*SG_LAT_RANGE)
    lon = random.uniform(*SG_LON_RANGE)
    return round(lat, 4), round(lon, 4)


def test_health(base_url: str) -> PerfResult:
    start = time.time()
    try:
        resp = requests.get(f"{base_url}/health", timeout=10)
        elapsed = (time.time() - start) * 1000
        return PerfResult("/health", resp.status_code, elapsed, resp.status_code == 200)
    except Exception as e:
        return PerfResult("/health", 0, (time.time() - start) * 1000, False, error=str(e))


def test_predict_location(base_url: str, location: str) -> PerfResult:
    start = time.time()
    try:
        resp = requests.get(f"{base_url}/predict", params={"location": location}, timeout=30)
        elapsed = (time.time() - start) * 1000
        forecast_status = None
        if resp.status_code == 200:
            forecast_status = resp.json().get("forecast", {}).get("description", "Unknown")
        return PerfResult("/predict?location", resp.status_code, elapsed, resp.status_code == 200,
                          forecast_status=forecast_status, location=location)
    except Exception as e:
        return PerfResult("/predict?location", 0, (time.time() - start) * 1000, False,
                          location=location, error=str(e))


def test_predict_coords(base_url: str, lat: float, lon: float) -> PerfResult:
    start = time.time()
    try:
        resp = requests.get(f"{base_url}/predict", params={"lat": lat, "lon": lon}, timeout=30)
        elapsed = (time.time() - start) * 1000
        forecast_status = None
        if resp.status_code == 200:
            forecast_status = resp.json().get("forecast", {}).get("description", "Unknown")
        loc_str = f"{lat},{lon}"
        return PerfResult("/predict?coords", resp.status_code, elapsed, resp.status_code == 200,
                          forecast_status=forecast_status, location=loc_str)
    except Exception as e:
        return PerfResult("/predict?coords", 0, (time.time() - start) * 1000, False,
                          location=f"{lat},{lon}", error=str(e))


def test_smart_query(base_url: str, query: str, location: str) -> PerfResult:
    start = time.time()
    try:
        resp = requests.get(f"{base_url}/smart-query", params={"q": query}, timeout=30)
        elapsed = (time.time() - start) * 1000
        return PerfResult("/smart-query", resp.status_code, elapsed, resp.status_code == 200,
                          location=location)
    except Exception as e:
        return PerfResult("/smart-query", 0, (time.time() - start) * 1000, False,
                          location=location, error=str(e))


def test_stations(base_url: str) -> PerfResult:
    start = time.time()
    try:
        resp = requests.get(f"{base_url}/stations", timeout=10)
        elapsed = (time.time() - start) * 1000
        return PerfResult("/stations", resp.status_code, elapsed, resp.status_code == 200)
    except Exception as e:
        return PerfResult("/stations", 0, (time.time() - start) * 1000, False, error=str(e))


def test_popular_searches(base_url: str) -> PerfResult:
    start = time.time()
    try:
        resp = requests.get(f"{base_url}/popular-searches", timeout=10)
        elapsed = (time.time() - start) * 1000
        return PerfResult("/popular-searches", resp.status_code, elapsed, resp.status_code == 200)
    except Exception as e:
        return PerfResult("/popular-searches", 0, (time.time() - start) * 1000, False, error=str(e))


# ── Accuracy 端点：纯 GET 只读操作，统计 backtest 预测精度 ──

ACCURACY_ENDPOINTS = [
    "/accuracy/summary",
    "/accuracy/by-hour",
    "/accuracy/by-location",
    "/accuracy/by-rain-level",
    "/accuracy/by-distance",
]


def test_accuracy(base_url: str, endpoint: str) -> PerfResult:
    start = time.time()
    try:
        resp = requests.get(f"{base_url}{endpoint}", timeout=10)
        elapsed = (time.time() - start) * 1000
        return PerfResult(endpoint, resp.status_code, elapsed, resp.status_code == 200)
    except Exception as e:
        return PerfResult(endpoint, 0, (time.time() - start) * 1000, False, error=str(e))


def pick_test_type() -> str:
    """
    按真实用户行为比例随机选取测试类型：
    - 45% location predict（写入搜索历史）
    - 13% coordinate predict
    - 13% smart query（写入搜索历史）
    - 8%  health check
    - 4%  stations
    - 4%  popular-searches
    - 13% accuracy（5 个端点均匀分配）
    """
    return random.choices(
        ["predict_location", "predict_coords", "smart_query", "health",
         "stations", "popular_searches", "accuracy"],
        weights=[45, 13, 13, 8, 4, 4, 13],
        k=1
    )[0]


def execute_one(base_url: str, test_data: TestData) -> PerfResult:
    """执行一次随机测试"""
    test_type = pick_test_type()

    if test_type == "health":
        return test_health(base_url)
    elif test_type == "predict_location":
        loc = test_data.pick_location()
        return test_predict_location(base_url, loc["name"])
    elif test_type == "predict_coords":
        loc = test_data.pick_location()
        # 优先使用数据文件中的坐标，否则随机生成
        lat = loc.get("lat") or random.uniform(*SG_LAT_RANGE)
        lon = loc.get("lon") or random.uniform(*SG_LON_RANGE)
        return test_predict_coords(base_url, round(lat, 4), round(lon, 4))
    elif test_type == "smart_query":
        query, location = test_data.build_smart_query()
        return test_smart_query(base_url, query, location)
    elif test_type == "stations":
        return test_stations(base_url)
    elif test_type == "popular_searches":
        return test_popular_searches(base_url)
    elif test_type == "accuracy":
        ep = random.choice(ACCURACY_ENDPOINTS)
        return test_accuracy(base_url, ep)
    else:
        return test_health(base_url)


def percentile(data: list[float], p: int) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


def generate_report(results: list[PerfResult], base_url: str, duration_s: float,
                    system_metrics: Optional[dict] = None) -> dict:
    """汇总测试结果生成 JSON 报告"""

    by_endpoint: dict[str, list[PerfResult]] = {}
    for r in results:
        by_endpoint.setdefault(r.endpoint, []).append(r)

    # Service Availability
    availability = {}
    for endpoint, items in by_endpoint.items():
        total = len(items)
        success = sum(1 for i in items if i.success)
        availability[endpoint] = {
            "total_requests": total,
            "successful": success,
            "failed": total - success,
            "availability_pct": round(success / total * 100, 2) if total else 0,
        }

    # Response Time
    response_times = {}
    for endpoint, items in by_endpoint.items():
        times = [i.response_time_ms for i in items if i.success]
        if times:
            response_times[endpoint] = {
                "avg_ms": round(statistics.mean(times), 1),
                "median_ms": round(percentile(times, 50), 1),
                "p95_ms": round(percentile(times, 95), 1),
                "p99_ms": round(percentile(times, 99), 1),
                "min_ms": round(min(times), 1),
                "max_ms": round(max(times), 1),
                "sample_count": len(times),
            }

    # Forecast Performance
    forecast_statuses = [r.forecast_status for r in results if r.forecast_status]
    forecast_distribution = {}
    for status in forecast_statuses:
        forecast_distribution[status] = forecast_distribution.get(status, 0) + 1

    # Popular Places（只统计会写入 DB 的端点）
    location_counts: dict[str, int] = {}
    for r in results:
        if r.location and r.endpoint in ("/predict?location", "/smart-query"):
            location_counts[r.location] = location_counts.get(r.location, 0) + 1
    popular_places = sorted(
        [{"name": k, "searches": v} for k, v in location_counts.items()],
        key=lambda x: x["searches"],
        reverse=True,
    )

    # Error Analysis
    errors = [r for r in results if not r.success]
    error_summary = {}
    for e in errors:
        key = f"{e.endpoint} -> {e.status_code}"
        error_summary[key] = error_summary.get(key, 0) + 1

    # Overall
    total = len(results)
    success_total = sum(1 for r in results if r.success)
    all_times = [r.response_time_ms for r in results if r.success]

    report = {
        "metadata": {
            "base_url": base_url,
            "test_time": datetime.now().isoformat(),
            "total_requests": total,
            "total_duration_s": round(duration_s, 1),
            "throughput_rps": round(total / duration_s, 2) if duration_s > 0 else 0,
        },
        "overall": {
            "total_requests": total,
            "successful": success_total,
            "failed": total - success_total,
            "success_rate_pct": round(success_total / total * 100, 2) if total else 0,
            "avg_response_ms": round(statistics.mean(all_times), 1) if all_times else 0,
            "p95_response_ms": round(percentile(all_times, 95), 1) if all_times else 0,
        },
        "service_availability": availability,
        "response_times": response_times,
        "forecast_performance": {
            "total_forecasts": len(forecast_statuses),
            "distribution": forecast_distribution,
        },
        "popular_places": popular_places[:20],
        "error_analysis": error_summary if error_summary else "No errors",
    }
    if system_metrics:
        report["system_metrics"] = system_metrics
    return report


def print_progress(results: list[PerfResult], elapsed_s: float, total_duration_s: Optional[float]):
    success = sum(1 for r in results if r.success)
    failed = len(results) - success
    avg_ms = statistics.mean([r.response_time_ms for r in results if r.success]) if success else 0

    if total_duration_s:
        remaining = max(0, total_duration_s - elapsed_s)
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        logger.info(
            f"[{mins:02d}:{secs:02d} left] {len(results)} reqs | ✓ {success} ✗ {failed} | Avg: {avg_ms:.0f}ms"
        )
    else:
        logger.info(
            f"Progress: {len(results)} reqs | ✓ {success} ✗ {failed} | Avg: {avg_ms:.0f}ms"
        )


def print_summary(report: dict, duration: float):
    """打印最终摘要"""
    logger.info("=" * 60)
    logger.info("📊 RESULTS SUMMARY")
    logger.info("=" * 60)
    overall = report["overall"]
    logger.info(f"Total:        {overall['total_requests']} requests in {duration:.1f}s")
    logger.info(f"Success Rate: {overall['success_rate_pct']}%")
    logger.info(f"Throughput:   {report['metadata']['throughput_rps']} req/s")
    logger.info(f"Avg Latency:  {overall['avg_response_ms']}ms")
    logger.info(f"P95 Latency:  {overall['p95_response_ms']}ms")

    logger.info("-" * 40)
    logger.info("🏥 Service Availability:")
    for ep, avail in report["service_availability"].items():
        logger.info(f"  {ep:25s} {avail['availability_pct']:6.1f}% ({avail['successful']}/{avail['total_requests']})")

    logger.info("-" * 40)
    logger.info("⏱️  Response Times:")
    for ep, rt in report["response_times"].items():
        logger.info(f"  {ep:25s} avg={rt['avg_ms']:7.0f}ms  p95={rt['p95_ms']:7.0f}ms  max={rt['max_ms']:7.0f}ms")

    if report["forecast_performance"]["distribution"]:
        logger.info("-" * 40)
        logger.info("🌦️  Forecast Distribution:")
        for status, count in report["forecast_performance"]["distribution"].items():
            logger.info(f"  {status:20s} {count}")

    if report["popular_places"]:
        logger.info("-" * 40)
        logger.info("📍 Top Searched Places:")
        for place in report["popular_places"][:10]:
            logger.info(f"  {place['name']:30s} {place['searches']} searches")

    if report["error_analysis"] != "No errors":
        logger.info("-" * 40)
        logger.info("❌ Errors:")
        for err, count in report["error_analysis"].items():
            logger.info(f"  {err}: {count}")

    logger.info("=" * 60)
    logger.info("✅ Performance test complete!")


def main():
    parser = argparse.ArgumentParser(
        description="Performance test for Singapore Weather AI API"
    )
    parser.add_argument(
        "--base-url", default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--requests", type=int, default=None,
        help="Total requests to send (mutually exclusive with --duration)",
    )
    mode_group.add_argument(
        "--duration", type=int, default=None,
        help="Run for N minutes continuously",
    )

    parser.add_argument(
        "--concurrency", type=int, default=5,
        help="Concurrent workers (default: 5)",
    )
    parser.add_argument(
        "--data", default="perf-test-locations.json",
        help="Path to locations data file (default: perf-test-locations.json)",
    )
    parser.add_argument(
        "--output", default="perf-report.json",
        help="Output report file (default: perf-report.json)",
    )
    parser.add_argument(
        "--delay-min", type=float, default=0.1,
        help="Min delay between requests per worker (seconds)",
    )
    parser.add_argument(
        "--delay-max", type=float, default=0.5,
        help="Max delay between requests per worker (seconds)",
    )
    args = parser.parse_args()

    # 默认：无参数时运行 10 分钟
    if args.requests is None and args.duration is None:
        args.duration = 10

    # 加载测试数据
    test_data = TestData(args.data)

    mode_desc = f"{args.duration} minutes" if args.duration else f"{args.requests} requests"

    logger.info("=" * 60)
    logger.info("🚀 Singapore Weather AI — Performance Test")
    logger.info("=" * 60)
    logger.info(f"Target:       {args.base_url}")
    logger.info(f"Mode:         {mode_desc}")
    logger.info(f"Concurrency:  {args.concurrency}")
    logger.info(f"Locations:    {len(test_data.locations)}")
    logger.info(f"Delay:        {args.delay_min}~{args.delay_max}s")
    logger.info("-" * 60)

    # 预检
    logger.info("🔍 Pre-flight health check...")
    preflight = test_health(args.base_url)
    if not preflight.success:
        logger.error(f"❌ Service unreachable at {args.base_url}: {preflight.error}")
        return
    logger.info(f"✅ Service is up ({preflight.response_time_ms:.0f}ms)")

    # 启动系统指标采集
    metrics_collector = SystemMetricsCollector(interval=15)
    metrics_collector.start()
    logger.info("📈 System metrics collector started (15s interval)")

    # 执行测试
    results: list[PerfResult] = []
    start_time = time.time()
    last_progress_time = start_time
    total_duration_s = args.duration * 60 if args.duration else None

    logger.info("-" * 60)
    logger.info("🏃 Running tests...")

    def worker_fn():
        time.sleep(random.uniform(args.delay_min, args.delay_max))
        return execute_one(args.base_url, test_data)

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        if args.duration:
            # 持续时间模式：不断提交任务直到超时
            end_time = start_time + args.duration * 60
            active_futures = set()

            # 初始填充 worker 数量的任务
            for _ in range(args.concurrency * 2):
                active_futures.add(executor.submit(worker_fn))

            while time.time() < end_time:
                done_futures = {f for f in active_futures if f.done()}

                for f in done_futures:
                    active_futures.discard(f)
                    result = f.result()
                    results.append(result)

                    # 补充新任务（只要还没到时间）
                    if time.time() < end_time:
                        active_futures.add(executor.submit(worker_fn))

                # 每 15 秒打印进度
                now = time.time()
                if now - last_progress_time >= 15:
                    print_progress(results, now - start_time, total_duration_s)
                    last_progress_time = now

                time.sleep(0.1)

            # 等待剩余任务完成（最多再等 30 秒）
            logger.info("⏳ Finishing remaining requests...")
            for f in as_completed(active_futures, timeout=30):
                results.append(f.result())

        else:
            # 固定请求数模式
            futures = [executor.submit(worker_fn) for _ in range(args.requests)]

            for i, future in enumerate(as_completed(futures), 1):
                results.append(future.result())
                now = time.time()
                if now - last_progress_time >= 15 or i == len(futures):
                    print_progress(results, now - start_time, None)
                    last_progress_time = now

    duration = time.time() - start_time

    # 停止系统指标采集
    metrics_collector.stop()
    system_metrics = metrics_collector.get_summary()
    logger.info(f"📈 Collected {system_metrics.get('total_samples', 0)} system metric samples")

    # 生成报告
    logger.info("-" * 60)
    logger.info("📊 Generating report...")
    report = generate_report(results, args.base_url, duration, system_metrics=system_metrics)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info(f"💾 Report saved to: {args.output}")
    print_summary(report, duration)


if __name__ == "__main__":
    main()
