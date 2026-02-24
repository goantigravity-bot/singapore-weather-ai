# Solution Proposal — Singapore Weather AI

> **Team**: Jin Hui | **Date**: 2026-02-20 | **Capstone Project**

---

## 1. Overall Solution Proposal

### 1.1 Solution Architectural Overview

The team proposes a **Data Engineering Solution** built on AWS to ingest, process, and serve hyper-local weather intelligence for Singapore. The overall software architecture follows a **Medallion Architecture (Bronze → Silver → Gold)** pattern deployed across managed AWS services.

**Architecture Components:**

| Layer | Service | Role |
|-------|---------|------|
| **External Data Sources** | NOAA AWS Open Data (Himawari-9 satellite), NEA data.gov.sg APIs | Raw weather data providers |
| **Ingestion** | EC2 Download Server | Downloads satellite HSD files (.bz2, 3 bands: B08, B11, B13) and NEA JSON (Temp, Rain, Humidity, PM2.5, Wind) |
| **Bronze (Raw/Archived)** | S3 Bucket | Stores raw, unprocessed satellite and sensor data |
| **Processing** | EC2 GPU Training Server | PyTorch distributed training, outputs model checkpoints |
| **Silver (Processed)** | S3 Bucket | Cleaned .npy arrays and CSV feature files ready for consumption |
| **Gold (Trained Model)** | S3 Bucket | Production-grade model artifacts (latest.pth) |
| **Serving** | EC2 API Server (FastAPI) | Real-time prediction API with SQLite read/write cache |
| **NLU** | Google Gemini API | Parses free-text user queries into structured intent |
| **CDN** | Amazon CloudFront | HTTPS proxy and caching for REST API and frontend assets |
| **Frontend** | React SPA (S3 + CloudFront) | Interactive weather map for end users |
| **Analytics** | Databricks / Snowflake | Consumes Silver-tier performance data for BI dashboards and model evaluation |

**Architecture Diagram:**

![AWS Data-Driven Architecture](aws-architecture.png)

---

### 1.2 Project Plan and Task

Over the course of the Capstone Delivery, team members will be assigned different tasks. The following states the expected project timeline and tasks:

| Phase | Timeline | Tasks | Deliverables |
|-------|----------|-------|-------------|
| **Phase 1: Data Ingestion** | Week 1–2 | Set up S3 buckets (Bronze/Silver/Gold), build satellite download scripts, configure NEA API data fetch | Working data pipeline, S3 folder structure |
| **Phase 2: Data Processing** | Week 3–4 | Build HSD parser, numpy array converter, feature engineering scripts | Processed .npy and CSV files in Silver bucket |
| **Phase 3: Model Training** | Week 5–6 | Train PyTorch weather prediction model on GPU instance, evaluate MAE/RMSE | Trained model artifact in Gold bucket |
| **Phase 4: API & Serving** | Week 7–8 | Deploy FastAPI prediction server, integrate Gemini NLU, set up CloudFront | Live REST API endpoint |
| **Phase 5: Frontend & Dashboard** | Week 9–10 | Build React weather map, integrate real-time satellite overlay and wind animation | Deployed frontend application |
| **Phase 6: Analytics & Reporting** | Week 11–12 | Set up Databricks/Snowflake, create performance dashboards, final documentation | BI dashboards, final report |

---

### 1.3 Methodology

The team adopts the **Medallion Architecture** as the core methodology for managing the lifecycle of data:

| Layer | Naming Convention | Purpose | Example |
|-------|-------------------|---------|---------|
| **Bronze** | `{source}/{YYYYMMDD}/raw_filename.ext` | Raw, immutable archive of source data exactly as received | `satellite/20260220/HS_H09_20260220_0300_B13_FLDK_R20_S0110.DAT.bz2` |
| **Silver** | `{domain}/{YYYYMMDD}/{TYPE}_{BAND}_{YYYYMMDD}_{HHMM}.npy` | Parsed, cleaned, and standardized data ready for analysis | `processed/satellite/20260220/SAT_B13_20260220_0300.npy` |
| **Gold** | `models/latest.pth` | Final, consumption-ready business artifacts | Trained PyTorch model weights |

**Data Transformation Rules:**
1. **Bronze → Silver**: HSD binary decompression → numpy array extraction → coordinate cropping to Singapore bounding box → 10-min interval alignment
2. **Silver → Gold**: Multi-day feature stacking → PyTorch DataLoader batching → GPU training → model checkpoint selection by best validation MAE

---

## 2. Data Source

### 2.1 Datasets Info

| # | Data Source | Data Size | No. of Records | Data Type | Key Data Fields | Change Data Capture |
|---|-----------|-----------|----------------|-----------|----------------|-------------------|
| 1 | **NOAA AWS Open Data** (Himawari-9 Satellite) | ~500 MB/day (3 bands × 144 intervals) | ~432 files/day | Binary HSD (.bz2) | Band (B08/B11/B13), Timestamp, Lat/Lon grid, Brightness temperature | Append-only, new files every 10 minutes |
| 2 | **NEA data.gov.sg — Rainfall** | ~50 KB/call | ~50 stations per call | JSON | station_id, timestamp, rainfall_mm | Polling every 5 minutes |
| 3 | **NEA data.gov.sg — Temperature** | ~50 KB/call | ~50 stations per call | JSON | station_id, timestamp, temperature_°C | Polling every 5 minutes |
| 4 | **NEA data.gov.sg — Humidity** | ~50 KB/call | ~50 stations per call | JSON | station_id, timestamp, relative_humidity_% | Polling every 5 minutes |
| 5 | **NEA data.gov.sg — Wind** | ~50 KB/call | ~50 stations per call | JSON | station_id, timestamp, wind_speed_knots, wind_direction_° | Polling every 5 minutes |
| 6 | **NEA data.gov.sg — PM2.5** | ~20 KB/call | ~5 regions per call | JSON | region, timestamp, pm25_µg/m³ | Polling every 1 hour |
| 7 | **User Query Logs** (Internal) | ~1 KB/record | Growing (~100/day) | SQLite → CSV | query_id, query_text, ip_address, response_time_ms, forecast_outcome | Append-only, real-time |

### 2.2 Security Design

The following section describes the security access design and data masking strategy:

**Access Control:**

| Layer | Access Policy | Who Can Access |
|-------|--------------|---------------|
| **S3 Bronze/Silver/Gold** | IAM Role-based, bucket policies | Download Server (write), Training Server (read/write), API Server (read) |
| **API Server (FastAPI)** | CloudFront origin access, no direct public IP | End users via HTTPS only |
| **SQLite Cache** | Local file-system only, no remote access | API Server process only |
| **Databricks / Snowflake** | Cross-account IAM Role with read-only S3 access | Data Science team |

**Data Masking & Privacy:**

| Data Field | Sensitivity | Masking Strategy |
|-----------|-------------|-----------------|
| `ip_address` | PII (Personal) | Hashed using SHA-256 before storage; original IP never persisted in Silver/Gold layers |
| `query_text` | Low sensitivity | Retained for NLU analysis; no personal identifiers expected |
| AWS Access Keys | Secret | Stored in environment variables / AWS Secrets Manager; never hardcoded in source code |
| Databricks PAT Token | Secret | Stored in Databricks Secret Scope; rotated every 90 days |
