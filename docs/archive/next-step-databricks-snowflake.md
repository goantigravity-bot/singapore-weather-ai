# Next Step: Databricks & Snowflake Integration

> **Date**: 2026-02-13  
> **Status**: Planning  
> **Version**: Weather AI v0.7.0+

## 1. Executive Summary

Evaluate and adopt **Databricks Lakehouse** as the primary data platform for ML training and data engineering, with **Snowflake** as an optional downstream BI/analytics layer. This unifies the current fragmented infrastructure (EC2 × 3 + S3 + SageMaker) into a managed platform.

## 2. Technology Selection

### 2.1 Why Databricks (Primary)

Our data profile drives this decision:

| Data Type | Format | Volume | Why Databricks Wins |
|---|---|---|---|
| 🛰 Himawari-9 Satellite | NetCDF (.nc) | ~2GB/day | Spark UDF for binary processing; Snowflake can't handle this |
| 🌧 Rainfall | JSON (NEA API) | ~31K rows/day | Both can handle, but Databricks keeps it in one platform |
| 🌡 Temperature | JSON (NEA API) | ~31K rows/day | Same |
| 💧 Humidity | JSON (NEA API) | ~31K rows/day | Same |
| 😶‍🌫️ PM2.5 (Haze) | JSON (NEA API) | ~31K rows/day | Same |
| 🧠 PyTorch Model | .pth weights | ~50MB | MLflow Model Registry; Snowflake has no ML runtime |

### 2.2 Snowflake (Optional BI Layer)

Snowflake remains useful for:
- SQL-native BI dashboards (Tableau, Metabase integration)
- Time Travel queries on historical forecast accuracy
- Cross-team data sharing via Secure Views

### 2.3 Decision Matrix

| Capability | Current (EC2+S3) | Databricks | Snowflake |
|---|---|---|---|
| Satellite image processing | ✅ Custom scripts | ✅ Spark UDF | ❌ Not supported |
| PyTorch GPU training | ✅ g4dn.xlarge | ✅ ML Runtime | ❌ Not supported |
| Model versioning | ❌ Manual S3 sync | ✅ MLflow Registry | ❌ N/A |
| Structured data ETL | ✅ Python scripts | ✅ Delta Live Tables | ✅ Snowpipe |
| SQL analytics / BI | ❌ None | ✅ Databricks SQL | ✅ Best-in-class |
| Managed infrastructure | ❌ Self-managed | ✅ Serverless | ✅ Serverless |
| Cost (estimated monthly) | ~$120 | ~$80 | ~$30 (analytics only) |

---

## 3. Target Architecture

```text
┌─────────────────────── Databricks Lakehouse ────────────────────────┐
│                                                                     │
│  Auto Loader ──→ Bronze ──→ Silver ──→ Gold ──→ Feature Store       │
│  (S3 ingest)     (raw)      (cleaned)   (ML-ready)                  │
│                                                                     │
│  Workflow DAG: Ingest → Preprocess → Train (GPU) → Evaluate         │
│                                                        │            │
│                                              MLflow Registry        │
│                                                        │            │
└────────────────────────────────────────────────┬────────┘            │
                                                 │                    │
              ┌──────────────────────────────────┼────────────────────┘
              │                                  │
              │  ① Pull model (startup)          │ ② Async log write
              ▼                                  │
   ┌──────────────────────────┐                  │
   │  FastAPI + React (EC2)   │──────────────────┘
   │  - Predict API           │
   │  - Smart Query (Bedrock) │───────→ Snowflake (optional)
   │  - User Dashboard        │         BI / Ad-hoc Analytics
   └──────────────────────────┘
```

---

## 4. Data Flow Design

### 4.1 Model Consumption (Databricks → Web App)

**Approach**: Pull model at startup, local inference (zero network latency per request).

```python
# predict.py — only 3 lines change
import mlflow
mlflow.set_tracking_uri("databricks")
MODEL = mlflow.pytorch.load_model("models:/weather-precipitation-model/Production")
```

- Model updates: Databricks trains → registers new version → marks as `Production` → restart FastAPI (or scheduled reload)
- Fallback: if Databricks unreachable, use last cached model from local disk

### 4.2 Transaction Log Pipeline (Web App → Databricks)

**Approach**: Non-blocking async buffer with periodic flush.

```text
API Request → Response (immediate)
     │
     └──→ In-memory buffer (non-blocking)
              │
              └──→ Background thread flush (every 60s or 100 events)
                        │
                        └──→ Databricks Delta Lake (gold.user_activity)
```

Key design decisions:
- **Zero impact on API latency**: events buffered in memory, flushed by daemon thread
- **Acceptable data loss window**: max 60 seconds of logs on crash (tolerable for analytics)
- **Batch write efficiency**: 100 rows per INSERT vs. per-request writes

### 4.3 Delta Lake Table Schema

```
Bronze (raw)           Silver (cleaned)         Gold (ML-ready / analytics)
─────────────          ──────────────────       ──────────────────────────
satellite_raw          aligned_observations     training_features
sensor_readings                                 forecast_accuracy
                                                user_activity
                                                search_history
```

---

## 5. Implementation Phases

### Phase 1: Delta Lakehouse Setup (Week 1)
- [ ] Create Databricks Workspace on AWS
- [ ] Configure Unity Catalog + External Location (S3)
- [ ] Create Bronze/Silver/Gold schemas
- [ ] Set up Auto Loader for existing S3 bucket

### Phase 2: Training Pipeline Migration (Week 2-3)
- [ ] Port `preprocess_images.py` to Databricks Notebook + Spark UDF
- [ ] Port `train_rolling_window.py` to Databricks ML Runtime
- [ ] Configure MLflow experiment tracking
- [ ] Build Workflow DAG (Ingest → Preprocess → Train → Evaluate → Notify)
- [ ] Set up GPU cluster (g4dn.xlarge) with auto-termination

### Phase 3: Web App Integration (Week 3-4)
- [ ] Modify `predict.py` to load model from MLflow Registry
- [ ] Implement `log_pipeline.py` (async buffer → Delta Lake)
- [ ] Add transaction logging to API endpoints (`/predict`, `/smart-query`)
- [ ] Verify end-to-end: user query → prediction → log appears in Delta

### Phase 4: Analytics & Monitoring (Week 4)
- [ ] Create Databricks SQL Dashboard (forecast accuracy, user activity, latency)
- [ ] Configure Lakehouse Monitoring (data quality, model drift)
- [ ] (Optional) Set up Snowflake as downstream BI layer via Delta Sharing

---

## 6. Cost Projection

| Component | Monthly Cost | Notes |
|---|---|---|
| Databricks Serverless SQL | ~$10 | Pay-per-query, auto-suspend |
| Databricks ML Runtime (GPU) | ~$30 | 30 min/day, g4dn.xlarge |
| Databricks Workflow | ~$15 | Daily ETL, serverless |
| Delta Storage (S3) | ~$5 | <200GB compressed |
| Snowflake (optional) | ~$20-30 | X-Small warehouse, auto-suspend |
| **Total** | **$60-90/mo** | vs. current EC2 ~$120/mo |

---

## 7. Prerequisites

1. **Databricks Account**: Start with [Community Edition](https://community.cloud.databricks.com) (free) for POC
2. **AWS IAM**: Cross-account role for Databricks to access S3 bucket `weather-ai-models-de08370c`
3. **Snowflake Account** (optional): 30-day free trial with $400 credits
4. **Environment Variables** (new):
   - `DATABRICKS_HOST` — Workspace URL
   - `DATABRICKS_TOKEN` — Personal Access Token
   - `DATABRICKS_HTTP_PATH` — SQL Warehouse path
   - `MLFLOW_TRACKING_URI` — `databricks`

---

## 8. Risk & Mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| Databricks outage blocks model loading | No predictions | Local model cache as fallback |
| Log pipeline buffer overflow | Lost analytics data | Cap buffer at 10K events + disk spill |
| GPU cluster cost overrun | Budget exceeded | Auto-termination (20 min idle) + daily budget alerts |
| Migration disrupts live service | Downtime | Run Databricks in parallel with current setup during transition |
