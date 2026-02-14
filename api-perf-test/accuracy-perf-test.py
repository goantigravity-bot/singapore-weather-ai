#!/usr/bin/env python3
"""Accuracy API Performance Test

Tests all 5 accuracy endpoints:
- /accuracy/summary
- /accuracy/by-hour
- /accuracy/by-location
- /accuracy/by-rain-level
- /accuracy/by-distance

Measures: latency (p50/p95/p99), throughput, concurrent performance.

Usage:
    python3 accuracy-perf-test.py                    # Run on API server (localhost:8000)
    python3 accuracy-perf-test.py http://3.0.28.161:8000  # Run remotely
"""
import json
import statistics
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
ENDPOINTS = [
    "/accuracy/summary",
    "/accuracy/by-hour",
    "/accuracy/by-location",
    "/accuracy/by-rain-level",
    "/accuracy/by-distance",
]


def measure_single(endpoint, timeout=10):
    url = f"{BASE_URL}{endpoint}"
    t0 = time.time()
    try:
        r = requests.get(url, timeout=timeout)
        elapsed_ms = (time.time() - t0) * 1000
        return {
            "endpoint": endpoint,
            "status": r.status_code,
            "time_ms": round(elapsed_ms, 2),
            "success": r.status_code == 200,
            "body_size": len(r.content),
            "data": r.json() if r.status_code == 200 else None,
        }
    except Exception as e:
        elapsed_ms = (time.time() - t0) * 1000
        return {
            "endpoint": endpoint,
            "status": 0,
            "time_ms": round(elapsed_ms, 2),
            "success": False,
            "body_size": 0,
            "error": str(e),
        }


def run_warmup():
    print("🔥 Warmup (2 requests per endpoint)...")
    for ep in ENDPOINTS:
        for _ in range(2):
            measure_single(ep)
    print("   Done")


def percentile(data, pct):
    """Calculate percentile from sorted list."""
    idx = int(len(data) * pct / 100)
    return data[min(idx, len(data) - 1)]


def test_single_request():
    """Phase 1: 每个端点跑 10 次，测量单请求延迟分布"""
    print("\n📊 Phase 1: Single-Request Latency (10 iterations per endpoint)")
    print("=" * 70)
    results = {}
    for ep in ENDPOINTS:
        times = []
        for _ in range(10):
            r = measure_single(ep)
            times.append(r["time_ms"])
        times.sort()
        stats = {
            "min": round(min(times), 1),
            "avg": round(statistics.mean(times), 1),
            "p50": round(percentile(times, 50), 1),
            "p95": round(percentile(times, 95), 1),
            "max": round(max(times), 1),
        }
        results[ep] = stats
        print(
            f"  {ep:<30} min={stats['min']:>7.1f}ms  "
            f"avg={stats['avg']:>7.1f}ms  p95={stats['p95']:>7.1f}ms  "
            f"max={stats['max']:>7.1f}ms"
        )
    return results


def test_concurrent(concurrency=5, total_requests=50):
    """Phase 2: 并发请求，测量吞吐和延迟"""
    print(
        f"\n🚀 Phase 2: Concurrent Load "
        f"(concurrency={concurrency}, total={total_requests})"
    )
    print("=" * 70)
    results_by_ep = {ep: [] for ep in ENDPOINTS}
    errors = []

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = []
        for i in range(total_requests):
            ep = ENDPOINTS[i % len(ENDPOINTS)]
            futures.append(pool.submit(measure_single, ep))

        for f in as_completed(futures):
            r = f.result()
            results_by_ep[r["endpoint"]].append(r["time_ms"])
            if not r.get("success"):
                errors.append(r)

    total_time = time.time() - t0
    throughput = total_requests / total_time

    print(f"  Total time: {total_time:.2f}s")
    print(f"  Throughput: {throughput:.1f} req/s")
    print(f"  Errors: {len(errors)}")
    print()

    concurrent_stats = {}
    for ep, times in results_by_ep.items():
        if times:
            times.sort()
            stats = {
                "count": len(times),
                "avg": round(statistics.mean(times), 1),
                "p50": round(percentile(times, 50), 1),
                "p95": round(percentile(times, 95), 1),
                "max": round(max(times), 1),
            }
            concurrent_stats[ep] = stats
            print(
                f"  {ep:<30} n={stats['count']:>3}  "
                f"avg={stats['avg']:>7.1f}ms  p95={stats['p95']:>7.1f}ms  "
                f"max={stats['max']:>7.1f}ms"
            )

    return {
        "total_time_s": round(total_time, 2),
        "throughput_rps": round(throughput, 1),
        "errors": len(errors),
        "per_endpoint": concurrent_stats,
    }


def test_sustained(duration_s=30, rps=5):
    """Phase 3: 持续负载，测量稳定性"""
    print(f"\n⏱️  Phase 3: Sustained Load ({duration_s}s @ ~{rps} req/s)")
    print("=" * 70)
    results = []
    error_count = 0
    stop = threading.Event()
    lock = threading.Lock()
    interval = 1.0 / rps

    def sender():
        nonlocal error_count
        i = 0
        while not stop.is_set():
            ep = ENDPOINTS[i % len(ENDPOINTS)]
            r = measure_single(ep)
            with lock:
                results.append(r)
                if not r["success"]:
                    error_count += 1
            i += 1
            # Simple rate limiting per thread
            sleep_time = max(0, interval - r["time_ms"] / 1000)
            time.sleep(sleep_time)

    num_threads = min(rps, 3)
    threads = []
    for _ in range(num_threads):
        t = threading.Thread(target=sender, daemon=True)
        t.start()
        threads.append(t)

    time.sleep(duration_s)
    stop.set()
    for t in threads:
        t.join(timeout=5)

    all_times = [r["time_ms"] for r in results]
    all_times.sort()

    sustained_stats = {}
    if all_times:
        sustained_stats = {
            "min": round(min(all_times), 1),
            "avg": round(statistics.mean(all_times), 1),
            "p50": round(percentile(all_times, 50), 1),
            "p95": round(percentile(all_times, 95), 1),
            "max": round(max(all_times), 1),
        }
        actual_rps = len(all_times) / duration_s
        print(f"  Requests sent: {len(all_times)}")
        print(f"  Actual RPS: {actual_rps:.1f}")
        print(f"  Errors: {error_count}")
        print(
            f"  Latency: min={sustained_stats['min']:.1f}ms  "
            f"avg={sustained_stats['avg']:.1f}ms  "
            f"p50={sustained_stats['p50']:.1f}ms  "
            f"p95={sustained_stats['p95']:.1f}ms  "
            f"max={sustained_stats['max']:.1f}ms"
        )

    return {
        "duration_s": duration_s,
        "target_rps": rps,
        "actual_rps": round(len(all_times) / duration_s, 1) if all_times else 0,
        "total_requests": len(all_times),
        "errors": error_count,
        "latency": sustained_stats,
    }


def test_data_validation():
    """Phase 4: 检查每个端点返回的数据结构和值是否合理"""
    print("\n✅ Phase 4: Data Validation")
    print("=" * 70)
    checks = []

    # /accuracy/summary
    r = measure_single("/accuracy/summary")
    d = r.get("data") or {}
    checks.append(("summary returns data", r["success"]))
    checks.append(("sample_count >= 0", (d.get("sample_count") or 0) >= 0))
    checks.append(("total_forecasts >= 0", (d.get("total_forecasts") or 0) >= 0))
    checks.append(("match_rate in [0,1]", 0 <= (d.get("match_rate") or 0) <= 1))
    if d.get("mae") is not None:
        checks.append(("mae >= 0", d["mae"] >= 0))
    print(f"  /accuracy/summary: {json.dumps(d)}")

    # /accuracy/by-hour
    r = measure_single("/accuracy/by-hour")
    d = r.get("data") or []
    checks.append(("by-hour is list", isinstance(d, list)))
    if d:
        checks.append(("hour in [0,23]", all(0 <= x.get("hour", -1) <= 23 for x in d)))
    print(f"  /accuracy/by-hour: {len(d)} entries")

    # /accuracy/by-location
    r = measure_single("/accuracy/by-location")
    d = r.get("data") or []
    checks.append(("by-location is list", isinstance(d, list)))
    print(f"  /accuracy/by-location: {len(d)} entries")

    # /accuracy/by-rain-level
    r = measure_single("/accuracy/by-rain-level")
    d = r.get("data") or []
    checks.append(("by-rain-level is list", isinstance(d, list)))
    valid_levels = {"No Rain", "Light", "Moderate", "Heavy"}
    if d:
        checks.append(
            ("rain levels valid", all(x.get("rain_level") in valid_levels for x in d))
        )
    levels = [x.get("rain_level") for x in d]
    print(f"  /accuracy/by-rain-level: {len(d)} entries, levels={levels}")

    # /accuracy/by-distance
    r = measure_single("/accuracy/by-distance")
    d = r.get("data") or []
    checks.append(("by-distance is list", isinstance(d, list)))
    print(f"  /accuracy/by-distance: {len(d)} entries")

    print()
    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    for name, ok in checks:
        icon = "✅" if ok else "❌"
        print(f"  {icon} {name}")
    print(f"\n  Result: {passed}/{total} passed")

    return {"passed": passed, "total": total}


if __name__ == "__main__":
    print(
        f"🧪 Accuracy API Performance Test — "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    print(f"   Target: {BASE_URL}")
    print()

    run_warmup()

    report = {"timestamp": datetime.now().isoformat(), "base_url": BASE_URL}
    report["single_request"] = test_single_request()
    report["concurrent"] = test_concurrent(concurrency=5, total_requests=50)
    report["sustained"] = test_sustained(duration_s=30, rps=5)
    report["validation"] = test_data_validation()

    # Save report
    report_file = "/tmp/accuracy-perf-report.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n📄 Report saved to {report_file}")
    print("\n🏁 Done!")
