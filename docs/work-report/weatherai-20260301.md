# Weather AI — Daily Work Report

**Date:** 2026-03-01 (SGT)
**Author:** Jinhui

---

## Summary

Today's work focused on resolving historical sensor data quality issues, retraining the model from scratch with clean data, and updating system documentation.

---

## 1. Data Quality Fix — Sensor CSV Pipeline

### Problem Identified (via Snowflake)

After loading `real_sensor_data.csv` into Snowflake, distribution analysis revealed:

- **~16 million temperature records were incorrectly zero-filled** for rainfall-only stations
- **Wind speed and direction were entirely absent** due to NEA's alternative JSON format (Format B) not being handled
- Float values lacked consistent decimal precision

### Root Causes

| Issue | Cause |
|:---|:---|
| Zero temperature/humidity values | `fillna(0.0)` applied to all columns instead of only `rainfall` |
| Missing wind data | NEA wind JSON uses `data.readings[].data[].stationId` (Format B), not parsed |
| Inconsistent decimal precision | No rounding applied before writing to CSV |

### Fix Applied

- **Files modified:** `services/api/backend/sensor_data_manager.py`, `services/training/process_gov_data_from_s3.py`
- Only `rainfall` is now filled with `0`; all other missing values written as `""` → `NULL` in Snowflake
- Format B JSON parsing added for wind speed and wind direction
- All float values rounded to 2 decimal places on CSV write

### Verification

Post-fix data quality verified using Snowflake/Databricks notebook:
📎 [`docs/model-tuned/weather-playground-cleanup-20260301.ipynb`](../model-tuned/weather-playground-cleanup-20260301.ipynb)

---

## 2. Historical CSV Rebuild (2020–2026)

Rebuilt `real_sensor_data.csv` for all 7 years using the fixed pipeline and uploaded to S3.

| Year | Rows | S3 Path |
|:---|:---|:---|
| 2020 | ~3.2M | `processed/sensor/2020/real_sensor_data.csv` |
| 2021 | ~3.2M | `processed/sensor/2021/real_sensor_data.csv` |
| 2022 | ~3.2M | `processed/sensor/2022/real_sensor_data.csv` |
| 2023 | ~3.2M | `processed/sensor/2023/real_sensor_data.csv` |
| 2024 | ~3.2M | `processed/sensor/2024/real_sensor_data.csv` |
| 2025 | ~3.2M | `processed/sensor/2025/real_sensor_data.csv` |
| 2026 | ~407K | `processed/sensor/2026/real_sensor_data.csv` |

**Completed:** 09:58 SGT (started 09:30 SGT)

---

## 3. Model Retraining from Scratch

Triggered full retraining on the training server (GPU: g4dn.xlarge) using clean data.

**Training mode:** Initial (30 epochs per year), year-by-year 2020 → 2026

| Year | Completed | Satellite Files |
|:---|:---|:---|
| 2020 | 11:09 | 155,568 |
| 2021 | 11:55 | 155,172 |
| 2022 | 13:07 | 154,184 |
| 2023 | 13:45 | 155,169 |
| 2024 | 14:24 | 155,326 |
| 2025 | 14:56 | 135,726 |
| 2026 | 15:00 | 22,559 |

### Model Evaluation (on 2026 data)

| Year | Accuracy | Best F1 | Best Threshold |
|:---|:---|:---|:---|
| 2020 | 92.9% | 69.9% | 0.90 |
| 2021 | 94.3% | 72.6% | 0.90 |
| 2022 | 93.9% | 70.7% | 0.90 |
| 2023 | 93.3% | 71.3% | 0.90 |
| 2024 | 93.2% | 72.1% | 0.90 |
| 2025 | 94.4% | 76.3% | 0.90 |
| 2026 | 97.1% | 64.1% | 0.90 |

### Comparison with Previous Model (2/23)

| Metric | Old Model (2/23) | New Model (3/1) | Change |
|:---|:---|:---|:---|
| Accuracy | ~2.4% effective | 97.1% | 🚀 Major improvement |
| F1 Score | 2.67% | 64.1% | 🚀 +61.4pp |
| Precision | 1.35% | High | ✅ Fixed |
| Recall | 99.78% | Balanced | ✅ Fixed |

Old model was essentially predicting rain for all observations (Recall 99.78%, Precision 1.35%). New clean data enabled proper classification learning.

### Deployment

- New model uploaded to `s3://weather-ai-models-gcc/models/weather_fusion_model_2026.pth`
- Promoted to `s3://weather-ai-models-gcc/models/latest.pth` at ~18:21 SGT
- API server auto-pulled new model by 19:11 SGT (confirmed via MD5 match)

---

## 4. API Server Maintenance

- **Restarted API server** (new PID 180080) to pick up latest model and apply environment changes
- **Confirmed:** `actual_result` table exists with 171,911 records — actual collector running normally
- **Confirmed:** `forecast_result` table accumulating new predictions normally

---

## 5. Gmail Notification Disabled

Removed Gmail credentials from API server `.env` to stop email notifications:

- Removed: `SENDER_EMAIL`, `SENDER_PASSWORD`, `RECIPIENT_EMAIL`, `CC_EMAILS`
- Telegram notifications remain active
- Training server had no Gmail config — no change needed

---

## 6. Documentation Updated

New document created:
📄 [`docs/system-pipeline-and-model-improvement.md`](../system-pipeline-and-model-improvement.md)

Covers:

- End-to-end architecture (Download → Training → API)
- Satellite data source correction: **NOAA AWS Open Data** (Himawari-9, Band C13, Tile T036) — not JAXA
- Sensor data pipeline detail and CSV schema
- Data quality issue discovery via Snowflake (with notebook evidence)
- Model training strategy (initial vs incremental)
- Closed-loop feedback (forecast vs actual)
- Step-by-step guide for continuous model improvement

---

## 7. System Status at End of Day

| Component | Status |
|:---|:---|
| Download Server | ✅ Running (NEA + NOAA satellite, every 10 min) |
| Training Server | ✅ Idle (training complete) |
| API Server | ✅ Running with new model (PID 180080) |
| Export to S3 (Snowflake) | ✅ Last run 22:00 SGT — 197,572 rows exported |
| Actual Collector | ✅ 171,911 actual records in DB |
| Model in S3 | ✅ `latest.pth` updated to 2026 model |
| Gmail Notifications | 🔕 Disabled |
| Telegram Notifications | ✅ Active |
