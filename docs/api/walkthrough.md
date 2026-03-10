# Performance Test Walkthrough

## Deliverables

| File | Purpose |
|------|---------|
| [perf-test.py](file:///Users/jinhui/development/tools/claude-skill/api-perf-test/perf-test.py) | Test script (`--duration` / `--requests` modes) |
| [perf-test-locations.json](file:///Users/jinhui/development/tools/claude-skill/api-perf-test/perf-test-locations.json) | Reusable: 25 outdoor activity locations, 10 query templates, 8 time slots |
| [perf-report.json](file:///Users/jinhui/development/tools/claude-skill/api-perf-test/perf-report.json) | Test report (5-concurrency run) |

---

## Test Comparison: 5 vs 20 Concurrency

| Metric | 5 Workers | 20 Workers |
|--------|-----------|------------|
| Total Requests | 2,360 | ~7,000 |
| Success Rate | 100% | 100% |
| Throughput | 3.87 req/s | **~12 req/s** (3x ↑) |
| Avg Latency | 988ms | 1,651ms (67% ↑) |
| Duration | 10 min | 10 min |

> [!NOTE]
> Increasing concurrency from 5→20 tripled throughput but increased latency by 67%, indicating the server is I/O bound, not CPU bound.

---

## Bottleneck Analysis

Server is only **6% CPU** with 1,651ms average latency. Root causes:

### 1. External API I/O Blocking (Primary)

The biggest latency contributor is **`/smart-query` (avg 6,130ms)**. The call chain:

```
smart_query → parse_query → analyze_path_weather
  → fetch_osm_path()        ← HTTP to overpass-api.de (~2-5s)
  → geocode_location()      ← HTTP to nominatim.openstreetmap.org (~0.3-1s)  
  → predict_ensemble() × N  ← local inference (~50ms each)
```

Each smart query makes **2+ external HTTP calls** that block the thread.

### 2. Single Uvicorn Worker

API runs as `python3 api.py` → single uvicorn worker (PID 43852). A single worker with sync endpoints means:
- Requests queue behind slow ones
- Only 1 core of 2 vCPUs used
- GIL limits CPU parallelism even further

### 3. No Geocoding Cache

`geocode_location("Marina Bay Sands")` calls Nominatim every time, even for repeated searches. No caching = redundant ~300ms per duplicate lookup.

### Recommended Fixes (Impact × Effort)

| Fix | Impact | Effort | Details |
|-----|--------|--------|---------|
| **Geocoding Cache** | ⭐⭐⭐ | Low | `functools.lru_cache` on `geocode_location()` — eliminates redundant HTTP calls |
| **Multi-worker Uvicorn** | ⭐⭐⭐ | Low | `uvicorn api:app --workers 4` — uses both vCPUs |
| **Async endpoints** | ⭐⭐ | Medium | Convert `/predict` and `/smart-query` to `async def` with `httpx` for non-blocking I/O |
| **Pre-cache popular locations** | ⭐⭐ | Low | Warm cache at startup for the 25 known locations |

---

## How to Rerun

```bash
# Deploy to server
scp api-perf-test/perf-test.py api-perf-test/perf-test-locations.json ubuntu@3.0.28.161:~/

# Standard load (5 workers, 10 min)
ssh ubuntu@3.0.28.161 "python3 perf-test.py --duration 10"

# High load (20 workers, 10 min)
ssh ubuntu@3.0.28.161 "python3 perf-test.py --duration 10 --concurrency 20 --delay-min 0 --delay-max 0.1"

# Pull report
scp ubuntu@3.0.28.161:~/perf-report.json ./
```
