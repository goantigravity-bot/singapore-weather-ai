# Singapore Weather AI — System Pipeline & Model Improvement Guide

*Last updated: 2026-03-01*

---

## 1. End-to-End System Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Download Server                       │
│  download_manager.py  (systemd service, always-on)       │
│                                                          │
│  Every 10 minutes:                                       │
│  ├── Pull NEA APIs → save JSON to S3 (govdata/)          │
│  │     rainfall, temperature, humidity,                  │
│  │     pm25, wind-speed, wind-direction                  │
│  └── Download satellite imagery                          │
│        Source: NOAA AWS Open Data (public, no auth)      │
│          s3://noaa-himawari9/AHI-L2-FLDK-ISatSS/         │
│          Satellite: Himawari-9 (AHI sensor)              │
│          Band: C13 (10.41μm IR brightness temperature)   │
│          Tile: T036 (covers Singapore ~0°N–2.65°N)       │
│          Cadence: 10-min UTC slots, ~30 min delay        │
│        → crop 128×128 px around Singapore                │
│        → save as .npy arrays                             │
│        → upload to S3 (processed/satellite-3ch/)         │
└──────────────────────┬───────────────────────────────────┘
                       │  S3: govdata/*.json
                       │  S3: processed/satellite-3ch/*.npy
                       ▼
┌──────────────────────────────────────────────────────────┐
│                    Training Server                       │
│  train_yearly.sh  (triggered manually or on schedule)    │
│                                                          │
│  For each year (2020 → 2026):                            │
│  1. Download govdata JSON from S3                        │
│  2. process_gov_data_from_s3.py                          │
│       → merge 6 sensor types → real_sensor_data.csv      │
│  3. Download satellite .npy files from S3                │
│  4. train_rolling_window.py                              │
│       → GPU training (g4dn.xlarge)                       │
│       → initial: 30 epochs / incremental: 10 epochs      │
│  5. Upload model → S3: models/latest.pth                 │
│  6. Upload per-year backup → models/weather_fusion_       │
│       model_YYYY.pth                                     │
└──────────────────────┬───────────────────────────────────┘
                       │  S3: models/latest.pth
                       ▼
┌──────────────────────────────────────────────────────────┐
│                      API Server                          │
│  start.py  (nohup, always-on)                            │
│                                                          │
│  On startup:                                             │
│  ├── sensor_data_manager.py                              │
│  │     → sync last 14 days of JSON from S3               │
│  │     → build real_sensor_data.csv                      │
│  └── Load weather_fusion_model.pth into GPU/CPU          │
│                                                          │
│  Every 5 minutes (background sync thread):               │
│  ├── Download models/latest.pth → hot-reload model       │
│  ├── Refresh sensor CSV (latest 14 days)                 │
│  └── Download latest satellite .npy (for inference)      │
│                                                          │
│  On each user query (/predict, /smart-query):            │
│  ├── predict_ensemble() → rainfall prediction            │
│  └── Save result → forecast_result table (SQLite)        │
│                                                          │
│  Every 10 minutes (actual_collector background thread):  │
│  ├── Scan unmatched forecast_result records              │
│  ├── Call NEA API for actual observed rainfall           │
│  └── Write → actual_result table (closed-loop feedback)  │
│                                                          │
│  Every 2 hours (cron: export_to_s3.py):                  │
│  └── Export DB tables → S3 / Snowflake                   │
└──────────────────────────────────────────────────────────┘
```

---

## 2. Sensor Data Pipeline Detail

### Data Quality Issues — Discovery & Fix (March 2026)

After loading `real_sensor_data.csv` into **Snowflake**, distribution analysis across millions of rows immediately surfaced an anomaly that would have been **extremely difficult to spot manually** by inspecting raw files:

- **~16 million temperature records had a value of exactly `0`** — clearly wrong for Singapore's climate
- Many stations that only collect rainfall were showing `0` for temperature, humidity, and wind

The Snowflake query that revealed the problem:

```sql
SELECT temperature, COUNT(*) AS cnt
FROM real_sensor_data
GROUP BY temperature
ORDER BY cnt DESC
LIMIT 10;
-- "0.0" appeared 16M+ times — a clear data pipeline bug, not real observations
```

> **Note:** A set of Databricks/Snowflake notebooks was used both as **evidence of the issue** and to **verify data quality after the fix was applied**, confirming that zero values were replaced by proper NULLs and that wind speed/direction columns were now populated.

**Root causes identified:**

| Issue | Cause | Fix |
|:---|:---|:---|
| Temperature/humidity zero-filled | `fillna(0.0)` applied to all columns, not just rainfall | Only fill `rainfall` with `0`; others use `NaN` → `""` → `NULL` |
| Wind speed/direction all zero | NEA uses a different JSON format for wind (Format B) — parser didn't handle it | Added Format B parser (`data.readings[].data[].stationId`) |
| Long float decimals in CSV | No rounding applied | Round all floats to 2 decimal places on write |

**Lesson:** Loading pipeline output into a columnar analytics platform and running distribution checks is a fast and reliable way to surface data quality bugs that are invisible at the individual file level.

---

The raw JSON files from NEA come in two formats:

| Sensor Type | JSON Format | Station Key |
|:---|:---|:---|
| rainfall, temperature, humidity, pm25 | `items[].readings[].station_id` | `station_id` |
| wind-speed, wind-direction | `data.readings[].data[].stationId` | `stationId` (camelCase) |

The script `process_gov_data_from_s3.py` (training) and `sensor_data_manager.py` (API) both:

1. Parse both JSON formats correctly
2. Merge 6 sensor types into one wide CSV row per `(timestamp, sensor_id)`
3. Resample to 10-minute intervals (rainfall = sum, others = mean)
4. Write missing values as empty string (→ NULL in Snowflake), **not zero**
5. Round all floats to 2 decimal places

### CSV Schema

```
timestamp, sensor_id, humidity, pm25, rainfall, temperature, wind_speed, wind_direction
```

---

## 3. Model Training Strategy

### Initial Training (from scratch)

- **Trigger**: `train_yearly.sh` with no existing `weather_fusion_model.pth`
- **Mode**: `initial`, 30 epochs per year, year-by-year 2020 → 2026
- **Data**: sensor CSV + satellite .npy (155,000+ files per year)
- **Hardware**: NVIDIA T4 GPU (g4dn.xlarge), ~1–2 hours per year

### Incremental Training (ongoing improvement)

- **Trigger**: Run `train_yearly.sh` with existing model present
- **Mode**: `incremental`, 10 epochs, builds on previous checkpoint
- **Recommended frequency**: Monthly, using the latest year's data

```bash
# Run on training server — incremental update with 2026 data
TRAIN_YEARS="2026" \
EPOCHS_INCREMENTAL=10 \
PYTHON=/usr/bin/python3 \
WORK_DIR=/home/ubuntu/weather-ai/services/training \
nohup bash train_yearly.sh > /tmp/train_incremental.log 2>&1 &
```

After training completes, the new model is automatically uploaded to S3.
The API server picks it up within 5 minutes (no restart required).

---

## 4. Closed-Loop Feedback (Forecast vs Actual)

Every user query generates a `forecast_result` record. The `actual_collector`
background thread then fetches the real observed rainfall from NEA 10 minutes
later and stores it in `actual_result`. This enables:

- **Accuracy monitoring**: Compare predicted vs actual rainfall over time
- **Model retraining signal**: Identify systematic errors (time periods, locations)
- **Backtest dataset**: Use historical forecast+actual pairs to validate new models

### Key Tables (SQLite: `weather.db`)

| Table | Description |
|:---|:---|
| `forecast_result` | Model predictions per query |
| `actual_result` | Real observed values from NEA |
| `user_activity` | Query logs with response times |
| `location` | Geocoded coordinates per query |

---

## 5. How to Continuously Improve Model Accuracy

### Step 1 — Monitor current accuracy

Check the `/monitor` API or query the DB directly:

```sql
SELECT
    DATE(f.forecast_time) as date,
    COUNT(*) as total,
    AVG(ABS(f.rainfall_mm - a.actual_rainfall_mm)) as mae
FROM forecast_result f
JOIN actual_result a ON a.loc_id = f.loc_id
    AND ABS(julianday(f.forecast_time) - julianday(a.observation_time)) < 0.021
GROUP BY date
ORDER BY date DESC;
```

### Step 2 — Trigger incremental training monthly

```bash
ssh ubuntu@13.212.195.153
cd /home/ubuntu/weather-ai/services/training
TRAIN_YEARS="2026" PYTHON=/usr/bin/python3 WORK_DIR=$(pwd) \
nohup bash train_yearly.sh > /tmp/train.log 2>&1 &
```

### Step 3 — Update latest.pth after training

Training automatically uploads per-year models. Manually promote to latest:

```bash
aws s3 cp s3://weather-ai-models-gcc/models/weather_fusion_model_2026.pth \
          s3://weather-ai-models-gcc/models/latest.pth --profile gcc-jinhui
```

API server auto-pulls within 5 minutes.

### Step 4 — Backfill missing data gaps

If S3 is missing data for certain dates, use the backfill script:

```bash
ssh ubuntu@<download-server>
python3 /home/ubuntu/weather-ai/services/download/backfill.py --days 30
```

---

## 6. Key Configuration

| Parameter | Location | Default | Description |
|:---|:---|:---|:---|
| `SENSOR_DAYS` | API `.env` | 14 | Days of sensor data to keep locally |
| `S3_BUCKET` | All `.env` | `weather-ai-models-gcc` | S3 bucket |
| `EPOCHS_INITIAL` | `train_yearly.sh` | 30 | Epochs for first-time training |
| `EPOCHS_INCREMENTAL` | `train_yearly.sh` | 10 | Epochs for incremental updates |
| `SYNC_INTERVAL` | `api.py` | 300s | How often API syncs model from S3 |
| `TELEGRAM_BOT_TOKEN` | `.env` | — | Telegram notifications |

---

## 7. Server Reference

| Server | IP | Role |
|:---|:---|:---|
| Download Server | (see AWS console) | NEA + satellite ingestion |
| Training Server | `13.212.195.153` | GPU model training |
| API Server | `13.228.95.52` | Prediction serving |
