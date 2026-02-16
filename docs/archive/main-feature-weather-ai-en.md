# 🌦️ Singapore Weather AI Prediction System - Feature List

> **Version**: 0.5 | **Last Updated**: 2026-02-07

---

## 1. Data Ingestion & Processing

### 1.1 Satellite Data Acquisition (`download_jaxa_data.py`)
- Automated download of Himawari-9 infrared satellite imagery from JAXA FTP
- Batch download and incremental update support
- Auto-crop to Singapore region (103.6°E-104.1°E, 1.15°N-1.50°N)
- Parallel download optimization (xargs -P) for improved throughput

### 1.2 Sensor Data Acquisition (`fetch_and_process_gov_data.py`)
- Real-time meteorological data from NEA (National Environment Agency) API
- Data types: Temperature, Humidity, Rainfall, PM2.5
- SSL certificate verification and error handling
- Automatic resampling to 10-minute intervals

### 1.3 Image Preprocessing (`preprocess_images.py`)
- NetCDF to NumPy array conversion
- Multi-folder batch processing support
- Data normalization and standardization

### 1.4 Smart Data Alignment (`convert_govdata_to_csv.py`)
- 100% timestamp alignment between satellite and sensor data
- Automatic timezone conversion (UTC ↔ SGT)

---

## 2. Deep Learning Model

### 2.1 Dual-Branch Fusion Model (`weather_fusion_model.py`)

```
Satellite Image → CNN (SatelliteEncoder) ──┐
                                           ├─→ Fusion Layer → Rainfall Prediction
Sensor Sequence → LSTM (SensorEncoder) ────┘
```

- **SatelliteEncoder**: 3-layer Conv2d + BatchNorm + ReLU + AdaptiveAvgPool
- **SensorEncoder**: LSTM temporal encoder
- **FusionHead**: Fully connected + Dropout
- **Output**: 10-minute ahead rainfall prediction

### 2.2 Training (`train.py`)
- GPU/CPU/MPS adaptive training
- Incremental learning: auto-load existing model for continued training
- Feature dimension auto-adaptation (3→4 features smart migration)
- Dynamic epoch configuration (initial 30 / incremental 5)
- Environment variable override support

### 2.3 Model Evaluation (`evaluate.py`)
- MAE (Mean Absolute Error)
- RMSE (Root Mean Square Error)
- Classification accuracy (rain/no-rain)
- Visual evaluation chart generation

---

## 3. Automated Training System

### 3.1 End-to-End Training Pipeline (`auto_train_pipeline.py`)
Fully automated workflow:
1. Download latest satellite data
2. Fetch incremental sensor data
3. Preprocess images
4. Train model
5. Evaluate performance
6. Generate HTML report
7. Send email notification

### 3.2 Historical Batch Scheduler (`training_scheduler.py`)
- Day-by-day batch training (Oct 2025 – Jan 2026)
- S3 data readiness detection (`.complete` markers)
- Train → Cleanup → Archive workflow
- Real-time status sync to S3 monitoring dashboard
- Automatic failure retry mechanism

### 3.3 Rolling Window Training (`train_rolling_window.py`)
- 1-day or 10-day window batch training
- S3 checkpoint persistence and recovery
- Training history merge and upload

### 3.4 Training History (`training_history.py`)
- Training metrics logging (timestamp, duration, MAE, RMSE)
- Statistical analysis: average duration, performance trends

### 3.5 Email Notifications (`notification.py`)
- Automatic success/failure notifications
- HTML email templates with attachments (reports, charts, logs)
- Gmail SMTP integration

### 3.6 HTML Report Generation (`generate_report.py`)
- Training overview and timeline
- Performance metrics comparison (current vs. previous)
- Responsive design for mobile viewing

---

## 4. Prediction API Service (`api.py`)

### 4.1 Core Prediction Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/predict` | GET | Single-point weather prediction (location name / lat-lon) |
| `/predict/path` | GET | Path weather prediction (sampling along route) |
| `/health` | GET | Health check |
| `/stations` | GET | Weather station information |
| `/log-search` | POST | Log search history |
| `/popular-searches` | GET | Popular search statistics |

### 4.2 Core Algorithms (`predict.py`)
- **IDW Spatial Interpolation**: Inverse Distance Weighting using 3 nearest sensors
- **Haversine Distance**: Precise geospatial calculation
- **OpenStreetMap Integration**: Forward/reverse geocoding
- **Path Sampling**: One prediction point every 2km along route

### 4.3 Technical Features
- CORS cross-origin support
- Dual route registration (root path + `/api` prefix)
- SPA static file hosting
- SQLite search history storage
- Model hot-reloading

---

## 5. Frontend Application (React + TypeScript + Vite)

### 5.1 Page Structure

| Page | Component | Description |
|------|-----------|-------------|
| Home | `MapComponent` | Leaflet interactive map, click for prediction |
| Home | `ForecastPanel` | Weather prediction result display |
| Home | `QuickLinks` | Quick search shortcuts |
| Stats | `StatsPage` | Search data statistics |
| Monitor | `TrainingMonitor` | 3-tab training monitoring dashboard |
| Settings | `SettingsPage` | User configuration (station visibility, etc.) |
| About | `AboutPage` | Project information |

### 5.2 Frontend Features
- Interactive map: click any location for weather prediction
- Path search: enter landmark name for along-route weather
- Station markers: configurable show/hide weather stations
- Global config context (`ConfigContext`) with localStorage persistence
- Responsive design: desktop and mobile support
- Side navigation menu (`SideMenu`)

---

## 6. Monitoring Dashboard (`TrainingMonitor.tsx` + `monitor_api.py`)

### 6.1 Chrome-Style 3-Tab Interface

| Tab | Content |
|-----|---------|
| 📥 File Download | Daily download progress, completed days, satellite/NEA file counts |
| 🧠 Training Process | 4-phase stepper, batch progress, training history table |
| 🚀 API Application | Model/sensor sync status, last sync time |

### 6.2 Log Viewer
- 📋 Log modal overlay (S3/local log sources)
- Syntax highlighting: ERROR (red), WARNING (orange), SUCCESS (green)
- Auto-refresh every 5 seconds

### 6.3 Monitoring API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /monitor/overview` | End-to-end status overview |
| `GET /monitor/download` | Download status |
| `GET /monitor/training` | Training status + history |
| `GET /monitor/sync` | API sync status |
| `GET /monitor/logs/{type}` | Log content |

---

## 7. Infrastructure (AWS 3-Server Architecture)

| Server | Instance Type | IP | Purpose |
|--------|---------------|-----|---------|
| API Server | t3.medium | 3.0.28.161 | FastAPI + Frontend SPA hosting |
| Training Server | t3.large | 46.137.236.8 | Model training + S3 sync |
| Download Server | t3.micro | 18.142.90.30 | Parallel FTP data ingestion |

### S3 Data Lake
- **Bucket**: `weather-ai-models-de08370c`
- Model storage (`models/`)
- Satellite data staging (`satellite/`)
- Government data (`govdata/`)
- Training state (`state/`)
- Historical archive (`archived/`)

---

## 8. DevOps & Deployment

| Feature | File |
|---------|------|
| Docker containerization | `Dockerfile`, `Dockerfile.api` |
| One-click deployment | `deploy-all.sh` |
| Local development | `run-local.sh`, `stop-local.sh` |
| CloudFront HTTPS proxy | `setup-cloudfront-api-proxy.sh` |
| Infrastructure verification | `verify-infrastructure.sh` |
| Model sync to S3 | `sync_model_to_s3.sh` |
| Model pull from S3 | `fetch_latest_model.sh` |
| Cron automation | 10-minute model/data sync |

---

## 9. Test Coverage

### Frontend Tests (Vitest)

| File | Coverage |
|------|----------|
| `StatsPage.test.tsx` | Stats page |
| `TrainingMonitor.test.tsx` | Monitoring dashboard |
| `AboutPage.test.tsx` | About page |
| `ConfigContext.test.tsx` | Config context |
| `SettingsPage.test.tsx` | Settings page |

### Backend Tests (Python)

| File | Coverage |
|------|----------|
| `test_api.py` | API endpoint testing |
| `test_auto_training.py` | Auto-training pipeline |
| `verify_deployment.py` | Deployment verification |
| `verify_pm25_api.py` | PM2.5 API verification |

---

## 10. System Performance Metrics

| Metric | Value |
|--------|-------|
| Model MAE | ~0.12 mm |
| Model RMSE | ~0.23 mm |
| Classification Accuracy | ~85% |
| Single-point Prediction | <200ms |
| Path Prediction | <1s (10 sample points) |
| Concurrency Support | 100+ req/s |
| Model File Size | ~270KB |

---

**Repository**: https://github.com/goantigravity-bot/singapore-weather-ai
