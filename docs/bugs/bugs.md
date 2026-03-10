# Singapore Weather AI — Bug Registry

> **Consolidated**: 2026-02-16

---

## Summary

| ID | Date | Severity | Status | Title |
|---|---|---|---|---|
| BUG-001 | 2026-02-07 | Critical | ✅ Fixed | Training completes in 0.1s with 0 samples |
| BUG-002 | 2026-02-07 | Critical | ✅ Fixed | Sensor data source mismatch |
| BUG-003 | 2026-02-07 | Critical | ✅ Fixed | Off-by-one loop condition |
| BUG-004 | 2026-02-07 | Medium | ✅ Fixed | PyTorch `verbose` deprecation |
| BUG-005 | 2026-02-07 | Medium | ✅ Fixed | S3 sync warning misclassified as error |
| BUG-006 | 2026-02-07 | High | ✅ Fixed | Redundant JAXA FTP download in training |
| BUG-007 | 2026-02-07 | Low | ✅ Fixed | Email notification epoch count hardcoded |
| BUG-008 | 2026-02-07 | Low | ✅ Fixed | Training log buffered (not real-time) |
| BUG-009 | 2026-02-14 | Critical | ✅ Fixed | API server disk exhaustion (satellite cleanup TODO) |
| BUG-010 | 2026-02-14 | Critical | ✅ Fixed | Empty dataset training loop (incomplete .npy) |
| BUG-011 | 2026-02-14 | Medium | ✅ Fixed | API downloads raw .nc instead of processed .npy |
| BUG-012 | 2026-02-14 | Critical | 🔴 Open | Timezone mismatch in actual_collector JOIN |
| BUG-013 | 2026-02-14 | Medium | 🔴 Open | Negative rainfall predictions (model output unclamped) |
| BUG-014 | 2026-02-14 | Low | 🟡 Won't Fix | Choa Chu Kang benchmark outside 2km range |
| BUG-015 | 2026-02-16 | Medium | ✅ Fixed | ProcessPoolExecutor SEGV with netCDF4 under systemd |

---

## BUG-001 ~ 008: Training Pipeline Failures (2026-02-07)

**Root cause**: 7 bugs combined to make training report "complete in 0.1s" with 0 actual learning.

| Bug | File | Issue | Fix |
|---|---|---|---|
| BUG-002: Sensor source | `train_rolling_window.py` | Called NEA API (returns 2026-01) instead of downloaded govdata JSON (2025-10) | Use `convert_govdata_to_csv.py` for local JSON |
| BUG-003: Off-by-one | `train_rolling_window.py` | `while current < end` skips single-day batches (`start == end`) | Changed to `<=` |
| BUG-004: PyTorch API | `train.py` | `ReduceLROnPlateau(verbose=True)` removed in PyTorch 2.x | Removed parameter |
| BUG-005: S3 warning | `training_scheduler.py` | `aws s3 sync` warning → non-zero exit → false failure | Parse stderr for actual errors only |
| BUG-006: Redundant FTP | `train_rolling_window.py` | Re-downloaded from JAXA FTP after scheduler already had data on S3 | Removed duplicate download step |
| BUG-007: Hardcoded epochs | `notification.py` | Email shows 100 epochs when early stopping at 10 | Read actual from `training_metrics.json` |
| BUG-008: Log buffering | `train_rolling_window.py` | `train.py` stdout buffered in subprocess | Added `PYTHONUNBUFFERED=1` |

**Verification**:
```
修复前: Training Complete in 0.1s  (0 batches, 0 samples)
修复后: Training Complete in 270s (547 batches, 10 epochs)
       Epoch [1/10] Time: 27.4s | Loss: 0.4296 | Val Loss: 0.1348
```

---

## BUG-009: API Disk Exhaustion (2026-02-14) ✅

**Severity**: Critical

`sync_satellite_data()` downloaded raw .nc (~700MB/day) but cleanup was `# TODO`. Disk hit 96% (914MB free).

```python
# api.py L175-176 (before fix)
# Cleanup old files (> 6 hours)
# TODO: Implement strict cleanup to avoid disk fill
```

**Fix**: Added 3-hour cleanup window based on filename timestamp (not `os.stat` mtime — filename is the true data time).

```
修复前: 磁盘 95% (914MB free), satellite_data/ = 8.8GB
修复后: 磁盘 50% (9.8GB free), satellite_data/ = 16KB
```

---

## BUG-010: Empty Dataset Training Loop (2026-02-14) ✅

**Severity**: Critical

Training scheduler stuck on `2026-01-05`, failing every ~3 minutes with email spam:

```
ValueError: Dataset is empty (0 samples)
```

**Root cause chain**:

```
143 complete raw .nc on S3
  → but only 12 .npy (partial preprocess, SGT 01:40-03:30 only)
    → scheduler detects .npy, takes fast path (skips full-day reprocess)
      → 12 .npy cover midnight window only
        → nighttime sensor data extremely sparse
          → 0 valid aligned samples → ValueError → retry loop
```

**Fix**: Delete incomplete .npy from S3, force full re-preprocess from 143 raw .nc.

---

## BUG-011: Raw .nc Instead of Processed .npy (2026-02-14) ✅

**Severity**: Medium (optimization)

API server downloaded raw `.nc` (5MB each, ~700MB/day) for inference when it only needs the cropped Singapore 64×64 matrix. Root cause of BUG-009.

**Fix**: Changed `sync_satellite_data()` to sync `.npy` from `processed/satellite/` (~16KB each, ~2.3MB/day).

---

## BUG-012: Timezone Mismatch in actual_collector (2026-02-14) 🔴

**Severity**: Critical

All 5 accuracy endpoints (`/accuracy/summary`, etc.) return `sample_count: 0` despite data existing.

**Root cause**: NEA API returns `observation_time` with timezone offset (`2026-02-14T21:15:00+08:00`). SQLite `julianday()` returns NULL for this format — no error raised, JOIN silently matches 0 rows.

```
forecast_result.forecast_time  = '2026-02-14 21:21:13'       ← naive ✅
actual_result.observation_time = '2026-02-14T21:15:00+08:00'  ← offset ❌
```

**Proposed fix**:
```python
def _normalize_timestamp(ts):
    """Strip timezone for SQLite julianday() compatibility"""
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return ts[:19].replace("T", " ")
```

**Impact**: All historically collected `actual_result` data has invalid timestamps — needs retroactive SQL UPDATE.

---

## BUG-013: Negative Rainfall Predictions (2026-02-14) 🔴

**Severity**: Medium

Model produces negative values (e.g., -6.34mm, -6.70mm). Physically impossible for rainfall.

**Proposed fix**: `rainfall_mm = max(0.0, raw_prediction)` in `predict.py`

**Impact**: Distorts MAE/bias in accuracy endpoints; confuses `status` field mapping.

---

## BUG-014: Choa Chu Kang Benchmark (2026-02-14) 🟡

**Severity**: Low — **Won't Fix**

Benchmark coords 3.2km from nearest NEA station (exceeds 2km `MAX_MATCH_DISTANCE_KM`). 9/10 locations match successfully.

**Decision**: 2km threshold is intentional for accuracy. Consider replacing with Jurong West or Bukit Timah.

---

## BUG-015: ProcessPoolExecutor SEGV (2026-02-16) ✅

**Severity**: Medium

netCDF4 library is not fork-safe. `ProcessPoolExecutor` in `download_manager.py` caused SEGV in child processes under systemd.

**Fix**: Reverted to serial download for backfill stability. ~6s/frame, ~14 min/day.

---

## Lessons Learned

| # | Lesson | Related |
|---|---|---|
| 1 | **TODO ≠ done** — critical cleanup must be implemented immediately | BUG-009 |
| 2 | **Data pipeline must be end-to-end aligned** — download and training must use same data source | BUG-002 |
| 3 | **Boundary conditions** — `start == end` is a common edge case | BUG-003 |
| 4 | **Silent failures are the worst** — `julianday()` returns NULL without error | BUG-012 |
| 5 | **Background threads need monitoring** — invisible disk growth, email storms | BUG-009/010 |
| 6 | **Subprocess exit codes lie** — warnings ≠ errors for `aws s3 sync` | BUG-005 |
| 7 | **Fork-safety matters** — netCDF4 + ProcessPool = SEGV | BUG-015 |
