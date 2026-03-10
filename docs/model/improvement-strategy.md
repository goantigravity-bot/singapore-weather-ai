# Model Training Improvement Strategy

## Background

The Weather AI system predicts rainfall using a fusion model (`WeatherFusionNet`) that combines:
- **Satellite imagery** (Himawari-8/9, 3-channel B08/B11/B13, 41×37 full-map)
- **Ground sensor data** (NEA: temperature, rainfall, humidity, PM2.5, wind_speed, wind_direction from 80 stations)

### Current Performance (V2 Baseline)

| Metric | V1 | V2 | Issue |
|---|---|---|---|
| Accuracy | 32.2% | **96.1%** | — |
| Precision | 6.4% | **32.1%** | Still too many false positives |
| Recall | 97.7% | 69.5% | — |
| F1 Score | 12.1% | **43.9%** | Target: 60%+ |
| MAE | 0.198mm | **0.111mm** | — |

**Root cause**: 97.8% of test samples are dry — the model is biased toward predicting small amounts of rain "just in case."

---

## Improvement Groups (Priority Order)

### 🔴 Group 1: Low-Cost, High-Impact (Code Changes Only)

#### 1. ✅ Balanced DataLoader (WeightedRandomSampler)
- **Problem**: 95% of training samples are dry → model biased toward dry predictions
- **Solution**: Use PyTorch `WeightedRandomSampler` so each training batch has ~50% rain/dry
- **Result**: Implemented — 4% rain / 96% dry rebalanced to 50:50 per batch
- **Effort**: ~10 lines of code

#### 2. Focal Loss
- **Problem**: `WeightedMSELoss` with manual `rain_weight` is coarse
- **Solution**: Focal Loss auto-focuses on hard-to-classify boundary samples
- **Expected**: Precision +5-10% on top of balanced sampling
- **Effort**: Replace loss class (~20 lines)

#### 3. Two-Stage Model (Classify → Regress)
- **Problem**: Single regression head conflates "is it raining?" with "how much?"
- **Solution**: First binary classifier (rain/no-rain), then regression for amount
- **Expected**: Precision 55-70%, F1 60-70%
- **Effort**: ~50 lines, new model head

---

### 🟡 Group 2: Medium Investment — Data Gap Recovery

#### Problem: Missing Satellite Data

Of 77 rainy days identified, only 32 have processed satellite `.npy` files. **45 days have raw `.nc` in S3 but were never processed.**

| Date Range | Raw .nc in S3 | Processed .npy | Status |
|---|---|---|---|
| Oct 1-10 | ✅ | ✅ | Already processed |
| Oct 11 – Nov 29 | ✅ | ❌ | **Gap — needs processing** |
| Nov 30 – Jan 2 | ✅ | ✅ | Already processed |
| Jan 3 – Jan 5 | ✅ | ❌ | **Gap — needs processing** |

#### Solution: Day-by-Day Processing Pipeline

Created `model-tuned/process_and_train_daily.py`:

```
For each rainy day (from rainy_timestamps.json):
  1. Download raw .nc from S3 (only rainy time slots)
  2. Crop to Singapore area → .npy (64×64)
  3. Upload .npy to S3 processed/satellite/YYYYMMDD/
  4. Keep .npy locally
  5. Delete .nc to free disk space
  6. Train model on accumulated data
  7. → Next day
```

**Key stats from scan:**
- 48 dates need processing
- 1,629 rainy 10-minute slots
- ~1,100 GB raw .nc download (deleted after processing)
- ~17 seconds per slot (verified with Oct 15: 49 files in 13.8 min)

#### File Naming Compatibility

Raw satellite files use different satellite naming:
- **Himawari-8** (older, Oct 2025): `NC_H08_YYYYMMDD_HHMM_*.nc`
- **Himawari-9** (newer, Dec 2025+): `NC_H09_YYYYMMDD_HHMM_*.nc`

`WeatherDataset` hardcodes `NC_H09_` prefix. Solution: create H09 symlinks for H08 files at runtime.

---

### 🟢 Group 3: Larger Investment, High Potential

| Improvement | Status | Description | Expected Impact |
|---|---|---|---|
| Multi-channel satellite | ✅ | 3-channel B08/B11/B13 (41×37) | Better cloud detection |
| Time features | ⬜ | Add hour_of_day, day_of_year as input | "Afternoon rain" pattern |
| Rate-of-change features | ⬜ | Humidity/temperature derivatives | Pre-rain signals |
| Attention mechanism | ⬜ | Cross-attention between satellite & sensor branches | Smarter fusion |
| Transformer encoder | ⬜ | Replace LSTM with Transformer | Longer time dependencies |
| More historical data | ✅ | 2020-2026 year-by-year training | Better generalization |

---

### 🔵 Group 4: Cloud Training Pipeline Optimization (2025-02-22)

#### Data Pipeline
| Change | Detail | Impact |
|---|---|---|
| 10-min pre-aggregation | Resample during CSV generation, not training | 13M → 3.2M rows, 500x faster preprocessing |
| Pure numpy `__getitem__` | Precompute `_sensor_data_cache`, `_rainfall_cache`, `_sat_utc_cache` | Eliminate all pandas from hot path |
| Vectorized sample generation | `np.where` + tuple format | 17 min → 2.1s |

#### Training Config (T4 GPU)
| Config | Value | Reason |
|---|---|---|
| Batch Size (CUDA) | 1024 | T4 15GB VRAM only uses ~675 MiB |
| AMP (Mixed Precision) | ✅ | `autocast` + `GradScaler` for FP16 |
| Gradient Clipping | max_norm=1.0 | Prevent gradient explosion with large batch |
| prefetch_factor | 4 | Minimize GPU data starvation |

#### Bug Fixes
| Bug | Root Cause | Fix |
|---|---|---|
| NaN Loss | 0.1% satellite .npy files contain NaN pixels | `torch.nan_to_num(sat_img, nan=0.0)` |
| Cache pollution | numpy slice returns view, normalization corrupts cache | `.copy()` on slice |
| False success notification | `tee` pipe hides Python exit code | `PIPESTATUS[0]` check |

#### GPU Utilization: 0% → 33-61%
- Bottleneck: 4 vCPU (g4dn.xlarge) data feeding
- Mac UMA has no PCIe transfer overhead → 70% GPU on MPS
- Future: g4dn.2xlarge (8 vCPU) or pre-computed tensor cache

---

## Pipeline Scripts

| Script | Purpose |
|---|---|
| `model-tuned/scan_rainy_dates.py` | V1: Scan S3 for rainy days (daily total > 5mm) |
| `model-tuned/scan_rainy_timestamps.py` | **V3: Scan for rainy 10-min slots (> 0.10mm)** |
| `model-tuned/process_and_train_daily.py` | **V3: Day-by-day download → process → train** |
| `model-tuned/download_and_train.py` | V2: Batch download + train |
| `model-tuned/backtest.py` | Evaluate model with confusion matrix + metrics |

## Usage

```bash
# Step 1: Scan for rainy timestamps
python3 model-tuned/scan_rainy_timestamps.py

# Step 2: Process satellite data + train (all days)
python3 model-tuned/process_and_train_daily.py

# Step 2 (process only, no training):
python3 model-tuned/process_and_train_daily.py --process-only

# Step 2 (resume from specific date):
python3 model-tuned/process_and_train_daily.py --start 2025-10-15

# Step 2 (test with limited days):
python3 model-tuned/process_and_train_daily.py --max-days 3

# Step 3: Run backtest
python3 model-tuned/backtest.py
```

## Expected Result After All Improvements

| Metric | V2 Current | V3 Target |
|---|---|---|
| Accuracy | 96.1% | 96-97% |
| **Precision** | **32.1%** | **55-65%** |
| Recall | 69.5% | 60-70% |
| **F1** | **43.9%** | **58-68%** |
| MAE | 0.111mm | 0.08-0.10mm |
