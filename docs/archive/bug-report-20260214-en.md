# Bug Report — 2026-02-14

## API Server Disk Exhaustion Due to Uncleaned Satellite Data

**Discovered**: 2026-02-14  
**Severity**: Critical  
**Status**: ✅ Fixed  

---

### Symptoms

API server (`3.0.28.161`, t3.medium, 20GB EBS) disk usage reached **96%** with only **914MB** free. The `satellite_data/` directory accumulated **8.8GB** (13 `.nc` files), threatening service stability.

### Root Cause

| # | Bug | File | Impact |
|---|-----|------|--------|
| 1 | Satellite data cleanup never implemented | `api.py` (`sync_satellite_data`) | Background sync thread downloads satellite data every 5 minutes (~144 files/day × 5MB = 700MB/day) but cleanup was left as `# TODO`, causing unlimited accumulation |

#### Code Location

```python
# api.py L175-176 (before fix)
# Cleanup old files (> 6 hours)
# TODO: Implement strict cleanup to avoid disk fill
```

`sync_satellite_data()` during each sync cycle:
1. ✅ Listed satellite files in S3 by date
2. ✅ Downloaded missing files to `satellite_data/`
3. ❌ **Never cleaned up** — old files were never deleted

### Fix

```diff
 # api.py — sync_satellite_data()
-    # Cleanup old files (> 6 hours)
-    # TODO: Implement strict cleanup to avoid disk fill
+    # Cleanup: remove satellite files older than 3 hours to prevent disk exhaustion.
+    cleanup_count = 0
+    cutoff = now_utc - timedelta(hours=3)
+    for f in os.listdir(local_dir):
+        if not f.endswith(".nc"):
+            continue
+        ...
```

**Design Decisions**:
- **3-hour window** (instead of the commented 6 hours): keeps enough recent data while capping max usage at ~100MB (3h × 6 files/h × 5MB)
- **Timestamp from filename** (not `os.stat` mtime): file name timestamp is the true data time, unaffected by download timing

### Deployment & Verification

| Step | Command | Result |
|------|---------|--------|
| Deploy | `scp api.py ubuntu@3.0.28.161:~/weather-ai/api.py` | ✅ |
| Clean old data | `rm -rf ~/weather-ai/satellite_data/*` | Freed 8.8GB |
| Restart | `sudo systemctl restart weather-api` | ✅ active |
| Health check | `curl http://3.0.28.161:8000/health` | `{"status":"ok","version":"0.8.0"}` |

```
Before: 95% disk used (914MB free), satellite_data/ = 8.8GB
After:  50% disk used (9.8GB free), satellite_data/ = 16KB
```

### Lessons Learned

1. **TODO comments ≠ done** — Critical resource cleanup should never be left as a TODO
2. **Background thread side-effects need monitoring** — Silent daemon threads produce no visible errors until disk fills
3. **Periodic health checks should include disk metrics** — `df -h` should be part of automated alerting

---

## Training Failure Loop: Dataset is empty (0 samples)

**Discovered**: 2026-02-14  
**Severity**: Critical  
**Status**: ✅ Fixed  

### Symptoms

Training scheduler stuck on `2026-01-05`, failing every ~3 minutes and sending email notifications for hours. Error:

```
ValueError: Dataset is empty (0 samples). Check satellite data in processed_data/ and satellite_data/
```

### Root Cause

| # | Bug | File | Impact |
|---|-----|------|--------|
| 1 | Incomplete preprocessed data on S3 | `processed/satellite/20260105/` | Only 12 .npy files (UTC 17:40-19:30, i.e. SGT 01:40-03:30) — too narrow a window |
| 2 | Scheduler reuses stale .npy | `training_scheduler.py` | `_check_processed_available` hits incomplete data, takes fast path, skips full-day preprocessing |
| 3 | Corrupt temp files not cleaned | Training server `satellite_data/` | 23 files with random suffixes (e.g. `.nc.8871bfaF`) consuming 7.1GB, not recognized by dataset |

**Causal Chain**: S3 has 143 complete raw .nc → but only 12 .npy (early morning window) → scheduler detects .npy, takes fast path → 12 .npy cover SGT 01:40-03:30 only → sparse nighttime sensor data → time alignment produces 0 valid samples → repeated failure without advancing date

### Fix Steps

| Step | Action | Result |
|------|--------|--------|
| 1 | Stop scheduler | Email bombardment stopped |
| 2 | Clean corrupt .nc temp files | Freed 7.1GB |
| 3 | Clean stale local .npy | Cleared wrong cache |
| 4 | Delete 12 incomplete .npy from S3 | Forces full raw .nc → preprocess pipeline |
| 5 | Restart scheduler `--run 1` | Downloading 143 complete .nc for full-day preprocessing |

---

## API Satellite Data Changed from Raw .nc to Processed .npy

**Discovered**: 2026-02-14  
**Severity**: Medium (Optimization)  
**Status**: ✅ Fixed  

### Symptoms

API server was downloading raw `.nc` satellite data (~700MB/day), which was the root cause of the earlier disk exhaustion. In practice, the API inference pipeline only needs the cropped Singapore region (64×64 matrix).

### Fix

Changed `sync_satellite_data()` to sync `.npy` files from S3 `processed/satellite/` (~16KB each), stored in `processed_data/`.

| Metric | Before (raw .nc) | After (processed .npy) |
|--------|-----------------|----------------------|
| Daily data volume | ~700MB | ~2.3MB |
| Disk exhaustion risk | High | Near zero |
| Cloud analysis | ✅ | ✅ (when data available) |

`predict.py` already prioritizes `processed_data/` directory — no additional changes needed. Once the download server catches up to the current date, the API will automatically receive real-time satellite data.

---

## Timezone Mismatch in actual_collector Breaks Accuracy JOIN

**Discovered**: 2026-02-14  
**Severity**: Critical  
**Status**: 🔴 Open  

### Symptoms

All 5 accuracy endpoints (`/accuracy/summary`, `/accuracy/by-hour`, etc.) returned `sample_count: 0` despite `actual_collector.py` running normally and having both `forecast_result` and `actual_result` records in the database.

### Root Cause

| # | Bug | File | Impact |
|---|-----|------|--------|
| 1 | NEA API `observation_time` stored with timezone offset | `actual_collector.py` L215 | SQLite `julianday()` cannot parse `2026-02-14T21:15:00+08:00` format, returning NULL. The accuracy JOIN (`ABS(julianday(f.forecast_time) - julianday(a.observation_time)) < 0.021`) always evaluates to NULL, matching zero rows. |

#### Data in Database

```
forecast_result.forecast_time  = '2026-02-14 21:21:13'       ← naive format ✅
actual_result.observation_time = '2026-02-14T21:15:00+08:00'  ← timezone offset ❌
```

SQLite `julianday('2026-02-14T21:15:00+08:00')` returns **NULL**, causing the time-window comparison to fail silently. No error is raised — the JOIN simply returns zero rows.

### Proposed Fix

```diff
 # actual_collector.py — collect_actuals()
+def _normalize_timestamp(ts):
+    """Strip timezone from ISO timestamp for SQLite julianday() compatibility"""
+    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
+        try:
+            return datetime.strptime(ts, fmt).strftime("%Y-%m-%d %H:%M:%S")
+        except ValueError:
+            continue
+    return ts[:19].replace("T", " ")

 weather_db.save_actual_result(
     loc_id=loc_id,
     actual_rainfall_mm=actual_rainfall,
-    observation_time=obs_time,
+    observation_time=_normalize_timestamp(obs_time),
     ...
 )
```

### Impact

- **All historically collected actual_result data has invalid timestamps** — needs retroactive fix via SQL UPDATE
- The accuracy pipeline has been silently broken since deployment
- Workaround applied in `accuracy-backfill-test.py` but the live collector remains unfixed

### Lessons Learned

1. **SQLite datetime functions are silently strict** — `julianday()` returns NULL on unrecognized formats without any error
2. **Always validate JOIN conditions** — a 0-row result on a JOIN should trigger an alert
3. **Integration tests should verify the full pipeline** — unit testing `save_actual_result()` alone would not catch this

---

## Negative Rainfall Predictions in Model Output

**Discovered**: 2026-02-14  
**Severity**: Medium  
**Status**: 🔴 Open  

### Symptoms

`forecast_result` table contains records with negative `rainfall_mm` values (e.g., `-6.34mm`, `-6.70mm`). These appear in backtest predictions generated by `actual_collector.py`.

```sql
SELECT forecast_id, rainfall_mm, status FROM forecast_result
WHERE rainfall_mm < 0 ORDER BY rainfall_mm LIMIT 5;
-- forecast_id=2901, rainfall_mm=-6.34, status='Cloudy'
-- forecast_id=2902, rainfall_mm=-6.70, status='Cloudy'
```

### Root Cause

| # | Bug | File | Impact |
|---|-----|------|--------|
| 1 | Model output not clamped to `[0, ∞)` | `predict.py` (`predict_ensemble`) | Neural network can produce negative values, which are physically impossible for rainfall |

### Proposed Fix

```diff
 # predict.py — predict_ensemble()
 raw_prediction = model(input_tensor).item()
-rainfall_mm = raw_prediction
+rainfall_mm = max(0.0, raw_prediction)  # Rainfall cannot be negative
```

### Impact

- Negative values distort MAE/bias calculations in accuracy endpoints
- User-facing predictions display "--" due to fallback handling, but if shown, would confuse users
- `status` field shows "Cloudy" instead of "No Rain" for negative values

---

## Choa Chu Kang Benchmark Location Outside NEA Station Range

**Discovered**: 2026-02-14  
**Severity**: Low  
**Status**: 🟡 Won't Fix  

### Symptoms

During accuracy backfill testing, Choa Chu Kang consistently fails to match any NEA station:

```
⏭️ Choa Chu Kang — no station within 2km
```

9/10 benchmark locations match successfully; only Choa Chu Kang is excluded.

### Root Cause

| # | Issue | Detail |
|---|-------|--------|
| 1 | Benchmark coords (1.37288, 103.72244) vs nearest NEA station S121 (1.3940, 103.7467) | Distance ≈ 3.2km, exceeds `MAX_MATCH_DISTANCE_KM = 2.0` |

### Decision

**Won't Fix** — The 2km threshold is intentional to ensure data quality. Loosening it would reduce accuracy of the entire pipeline. Choa Chu Kang is the only outlier among 10 points, and 90% coverage is acceptable.

Alternative: Replace Choa Chu Kang with a location closer to an NEA station (e.g., Jurong West, Paya Lebar, or Bukit Timah).

