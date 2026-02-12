# 🌦️ Singapore Weather AI

[![Version](https://img.shields.io/badge/version-0.7-blue.svg)](./docs/CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-≥3.10-green.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](./LICENSE)

> A deep learning-powered weather prediction system that fuses Himawari-9 satellite imagery with NEA ground sensor data to deliver real-time 10-minute rainfall forecasts for Singapore.

![Architecture Overview](docs/architecture-banner.png)

---

## ✨ Key Features

- 🛰️ **Satellite + Sensor Fusion** — WeatherFusionNet (CNN + LSTM) jointly learns spatial and temporal patterns
- 🗺️ **Interactive Map** — Click anywhere on the Singapore map for instant rainfall predictions
- 🔍 **Smart Query (NLU)** — Ask natural language questions like *"Can I cycle at East Coast Park today?"*
- 📍 **Path Forecasting** — Weather analysis along routes (e.g., Rail Corridor, park connectors)
- 📊 **Training Monitor** — Real-time dashboard for download progress, training status, and system health
- ☁️ **Cloud-Native** — Terraform-managed AWS infrastructure with S3 data lake

---

## 🏗️ Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                        Users / Browser                        │
│                    React + Leaflet + Vite                      │
└──────────────────────────┬────────────────────────────────────┘
                           │ HTTPS
┌──────────────────────────▼────────────────────────────────────┐
│                    CloudFront CDN (Optional)                   │
└──────────────────────────┬────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────┐
│                  API Server (t3.medium)                        │
│              FastAPI + PyTorch + Gemini NLU                    │
└───────┬──────────────────┬────────────────────────────────────┘
        │                  │
        ▼                  ▼
┌───────────────┐  ┌───────────────────────────────────────────┐
│  SQLite DB    │  │              S3 Data Lake                  │
│ (search hist) │  │  models/ satellite/ govdata/ state/ logs/  │
└───────────────┘  └───────┬───────────────────┬───────────────┘
                           │                   │
               ┌───────────▼───────┐  ┌───────▼───────────────┐
               │ Training Server   │  │  Download Server      │
               │ (g4dn.xlarge GPU) │  │  (t3.micro)           │
               │ PyTorch Training  │  │  JAXA FTP + NEA API   │
               └───────────────────┘  └───────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

| Tool | Version | Installation |
|:---|:---|:---|
| Python | ≥ 3.10 | `brew install python@3.10` |
| Node.js | ≥ 18 LTS | `brew install node` |
| Docker | Latest | [Docker Desktop](https://docker.com) |

### Option A: Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/goantigravity-bot/singapore-weather-ai.git
cd singapore-weather-ai

# Configure environment
cp .env.production.template .env
# Edit .env with your JAXA/Gemini API credentials

# Build and start all services
docker compose up -d

# Access the app
open http://localhost:8000
```

This starts 4 services:
- **MinIO** (S3-compatible storage) — `localhost:9000`
- **Download Service** — Fetches satellite + sensor data
- **Training Service** — Trains the ML model
- **API Service** — Serves predictions at `localhost:8000`

### Option B: Local Development

```bash
# Backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cd services/api && uvicorn api:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

---

## 📂 Project Structure

```
singapore-weather-ai/
├── services/
│   ├── api/                    # FastAPI prediction service
│   │   ├── api.py              # Main API endpoints
│   │   ├── predict.py          # Prediction logic + IDW interpolation
│   │   ├── smart_query.py      # Gemini NLU integration
│   │   ├── monitor_api.py      # Training monitor endpoints
│   │   └── weather_fusion_model.py  # PyTorch model definition
│   ├── training/               # Model training service
│   │   ├── train.py            # Training loop (AMP, Early Stopping)
│   │   └── training_scheduler.py    # Batch training orchestrator
│   ├── download/               # Data ingestion service
│   │   └── download_manager.py # JAXA FTP + NEA API fetcher
│   └── shared/                 # Shared utilities
├── frontend/                   # React + TypeScript + Vite
│   └── src/
│       ├── components/         # MapComponent, ForecastPanel, etc.
│       ├── pages/              # TrainingMonitor, StatsPage, etc.
│       └── App.tsx             # Main app with routing
├── terraform/                  # AWS IaC (EC2, S3, CloudFront, IAM)
├── scripts/                    # Automation scripts
├── docs/                       # Technical documentation
│   ├── technology-stack.md     # Full tech stack (中文)
│   ├── technology-stack-en.md  # Full tech stack (English)
│   ├── data-model.md           # Data model + ER diagrams
│   └── databricks-integration-analysis.md  # Databricks feasibility
├── docker-compose.yml          # Full-stack local deployment
├── deploy-all.sh               # One-click AWS deployment
└── requirements.txt            # Python dependencies
```

---

## 🧠 ML Model — WeatherFusionNet

A dual-branch fusion architecture combining satellite imagery (CNN) and sensor time-series (LSTM):

```
Satellite Image (NetCDF)          Sensor Time Series (CSV)
        │                                  │
   ┌────▼────┐                       ┌─────▼─────┐
   │   CNN   │                       │   LSTM    │
   │ 3×Conv2d│                       │ Temporal  │
   │ + BN    │                       │ Encoder   │
   │ + Pool  │                       │           │
   └────┬────┘                       └─────┬─────┘
        │ (128-d)                          │ (64-d)
        └───────────┬──────────────────────┘
                    │ Concatenate (192-d)
               ┌────▼─────┐
               │  Fusion   │
               │ FC+Dropout│
               │   FC(1)   │
               └────┬──────┘
                    │
            Rainfall Prediction
              (mm / 10 min)
```

### Performance Baseline

| Metric | Value |
|:---|:---|
| MAE | ~0.11 mm |
| RMSE | ~0.40 mm |
| Rain/No-Rain Accuracy | ~85% |
| API Latency | < 200ms |
| Model Size | ~270 KB |

---

## 🌐 API Reference

| Endpoint | Method | Description |
|:---|:---|:---|
| `/predict` | GET | Single-point rainfall prediction (`lat`/`lon` or `location` name) |
| `/predict/path` | GET | Weather along a route (e.g., `?query=Rail Corridor`) |
| `/smart-query` | GET | Natural language query (e.g., `?q=Can I jog at Botanic Gardens?`) |
| `/stations` | GET | List all NEA weather stations |
| `/popular-searches` | GET | Top 8 searched locations |
| `/health` | GET | Service health check |
| `/monitor/overview` | GET | Training pipeline status (download + training + sync) |
| `/monitor/logs/{type}` | GET | View logs (download / training / sync) |

### Example

```bash
# Predict by location name
curl "http://localhost:8000/predict?location=Marina Bay Sands"

# Predict by coordinates
curl "http://localhost:8000/predict?lat=1.2838&lon=103.8591"

# Smart query
curl "http://localhost:8000/smart-query?q=Can%20I%20cycle%20at%20East%20Coast%20Park%20today"
```

---

## ☁️ AWS Deployment

### Infrastructure (Terraform)

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars

terraform init && terraform plan && terraform apply
```

Provisions:
- **EC2** — API server (`t3.medium`), Training server (`g4dn.xlarge`), Download server (`t3.micro`)
- **S3** — Data lake (`weather-ai-models-*`) + Frontend hosting (`weather-ai-frontend-*`)
- **CloudFront** — CDN with HTTPS + SPA routing
- **IAM** — Least-privilege roles for each server
- **EIP** — Static IP for API server

### Application Deployment

```bash
# Deploy everything (backend + frontend + monitoring dashboard)
./deploy-all.sh --full

# Backend only
./deploy-all.sh --backend

# Frontend only
./deploy-all.sh --frontend
```

---

## 📖 Documentation

| Document | Description |
|:---|:---|
| [Technology Stack (EN)](docs/technology-stack-en.md) | Full tech stack, AWS infra, network, model details |
| [Technology Stack (中文)](docs/technology-stack.md) | 技术栈文档中文版 |
| [Data Model & ER Diagram](docs/data-model.md) | Complete data model with Mermaid ER diagrams |
| [Databricks Analysis](docs/databricks-integration-analysis.md) | Databricks integration feasibility study |
| [Terraform README](terraform/README.md) | AWS infrastructure setup guide |
| [Auto Training Guide](docs/AUTO_TRAINING_README.md) | Automated training pipeline usage |
| [Deployment Guide](docs/DEPLOYMENT_GUIDE.md) | Step-by-step deployment instructions |
| [Security](docs/SECURITY.md) | Security configuration and best practices |

---

## 🔧 Development

### Running Tests

```bash
# Backend tests
pytest services/api/ -v

# Frontend tests
cd frontend && npm test

# API integration test
python test_api.py
```

### Environment Variables

| Variable | Required | Description |
|:---|:---|:---|
| `JAXA_USER` / `JAXA_PASS` | Yes | JAXA FTP credentials for satellite data |
| `GEMINI_API_KEY` | Yes | Google Gemini API key for NLU smart queries |
| `SENDER_EMAIL` / `SENDER_PASSWORD` | Optional | Gmail SMTP for training notifications |
| `S3_BUCKET` | Yes (prod) | AWS S3 bucket name |
| `S3_ENDPOINT_URL` | Optional | Custom S3 endpoint (MinIO for local dev) |

### Converting Docs to HTML

```bash
# Convert any markdown doc to styled HTML (with Mermaid diagram support)
./docs/md-to-html.sh docs/data-model.md
```

---

## 📊 Data Sources

| Source | Type | Frequency | Description |
|:---|:---|:---|:---|
| [JAXA Himawari-9](https://www.eorc.jaxa.jp/ptree/) | Satellite NetCDF | Every 10 min | Infrared/visible imagery over Singapore |
| [NEA Data.gov.sg](https://data.gov.sg) | REST API | Real-time | Temperature, humidity, rainfall, PM2.5 from 50+ stations |
| [OpenStreetMap](https://www.openstreetmap.org) | REST API | On-demand | Geocoding and route geometry for path predictions |

### ⚠️ Rate Limits & Caching

External APIs enforce rate limits that can cause failures under load:

| API | Rate Limit | Consequence | Mitigation |
|:---|:---|:---|:---|
| [Nominatim](https://operations.osmfoundation.org/policies/nominatim/) | 1 req/sec (absolute) | HTTP 429 / empty response → 404 errors | SQLite L2 cache (`geocode_cache`), L1 in-memory dict |
| [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API) | ~10K/day (shared pool) | Empty JSON response → parse failures | SQLite L2 cache (`overpass_cache`), L1 in-memory dict |
| [NEA Data.gov.sg](https://api.data.gov.sg) | ~500 req/min | Throttled responses | 60-sec in-memory cache in `predict.py` |

**Cache Architecture** (since v0.7):

```
Request → L1 (in-memory dict, per-worker) → L2 (SQLite, cross-worker) → External API
```

- Only **successful** responses are cached — failures trigger retries on next request
- L2 persists across service restarts
- See [ER Diagram](docs/data-storage-er-diagram.html) for cache table schema

---

## 🗺️ Roadmap

- [ ] Multi-step forecast (30 min, 1 hour ahead)
- [ ] Transformer / Attention mechanism for temporal modeling
- [ ] MLflow experiment tracking integration
- [ ] Mobile-responsive PWA
- [ ] Multi-region expansion (Southeast Asia)
- [ ] EKS container orchestration

---

## 👤 Author

**Jin Hui** — [goantigravity-bot](https://github.com/goantigravity-bot)

---

## 📄 License

This project is developed for learning and research purposes. Data sources are from publicly available APIs and services.
