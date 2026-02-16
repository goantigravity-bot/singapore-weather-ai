# Singapore Weather AI — Requirements

> **Version**: 1.0 &nbsp; | &nbsp; **Consolidated**: 2026-02-16

---

## 1. Problem Statement

NEA's current weather forecasting provides broad, city-wide predictions (e.g., *"Thunderstorms in the afternoon"*) that lack spatial and temporal granularity. By fusing **Himawari-9 satellite imagery** with NEA's **real-time sensor network** through a **CNN + LSTM deep learning model**, this platform delivers:

1. **Hyper-local predictions** — street-level rainfall forecasts using IDW across sensor stations
2. **Real-time responsiveness** — predictions in <200ms, updated with 10-minute sensor readings
3. **Route-aware intelligence** — weather conditions along a commuter's path
4. **Self-improving accuracy** — automated daily retraining adapts to seasonal patterns

---

## 2. KPI Targets

### 2.1 Public Trust & Service Excellence

| Metric | Target | Measurement |
|---|---|---|
| Prediction Accuracy (rain/no-rain) | ≥ 85% | Confusion matrix on held-out test set |
| Forecast vs Actual Deviation | MAE < 0.5mm | `predicted_rainfall - actual_station_reading` |
| User Satisfaction | ≥ 4.2/5.0 | In-app feedback + quarterly survey |
| Monthly Active Users | ≥ 50,000 (12 months) | Firebase Analytics |

### 2.2 Public Safety

| Metric | Target |
|---|---|
| Alert Lead Time | ≥ 10 min before rainfall |
| Severe Weather Detection Rate | ≥ 90% |
| False Alert Rate | ≤ 10% |

### 2.3 Operational Efficiency

| Metric | Target |
|---|---|
| Data Pipeline Uptime | ≥ 99.5% |
| Model Retraining Frequency | Daily (automated) |
| Forecasting Automation Rate | ≥ 90% of routine forecasts |

---

## 3. Functional Requirements

### 3.1 Core Prediction

| ID | Requirement |
|---|---|
| FR-1.1 | Single-point forecast via location name or lat/lon (`/predict`) |
| FR-1.2 | Path/route forecast with sampled points every 2km (`/predict/path`) |
| FR-1.3 | NLU smart query via Gemini API (`/smart-query`) |
| FR-1.4 | IDW interpolation using 3 nearest stations for each prediction |

### 3.2 Forecast vs Actual (Closed-Loop Accuracy)

| ID | Requirement |
|---|---|
| FR-2.1 | Scan `forecast_result` for unmatched records every 5 minutes |
| FR-2.2 | Match forecast to nearest NEA station within `MAX_MATCH_DISTANCE_KM = 2.0` |
| FR-2.3 | Record `match_distance_km` and `station_id` for traceability |
| FR-2.4 | Provide MAE/bias aggregated by hour, location, and rain level via `/accuracy/*` |
| FR-2.5 | Run proactive backtests on 10 benchmark locations every 10 minutes |

#### Station Matching Distance — Design Rationale

Singapore's rainfall is 70% convective storms (2–10km cells). Within 5km, two points may experience completely different rainfall. NEA has 60+ rainfall stations across ~730km².

| Threshold | Coverage | Accuracy Risk | Decision |
|---|---|---|---|
| 1 km | ~40% | Low | Too restrictive |
| **2 km** | **~70%** | **Low** | **✅ Chosen** |
| 5 km | ~95% | Moderate (convective risk) | Too loose |

**Mitigation**: Record distance, analyze MAE by distance bins, refine threshold with data.

#### 10 Benchmark Locations

| Area | Location | NEA Station | Distance |
|---|---|---|---|
| Central | Newton | S111 | ~0.5km |
| East | Changi Airport | S24 | ~0.3km |
| West | West Coast | S116 | ~0.8km |
| North | Woodlands | S104 | ~0.5km |
| NE | Ang Mo Kio | S109 | ~0.4km |
| SW | Tuas South | S115 | ~0.6km |
| South | Sentosa | S60 | ~0.3km |
| NW | Choa Chu Kang | S121 | ~0.5km |
| SE | East Coast Park | S107 | ~0.4km |
| West | Clementi | S50 | ~0.3km |

### 3.3 Haze PSI Alert

| ID | Requirement |
|---|---|
| FR-3.1 | Fetch PSI from `api-open.data.gov.sg` every 5 minutes for all 5 regions |
| FR-3.2 | Map coordinate to nearest PSI region (west/east/central/south/north) |
| FR-3.3 | Path queries return **maximum PSI** across traversed regions |
| FR-3.4 | Frontend slider for PSI threshold (0–300, default 50, persisted in localStorage) |
| FR-3.5 | Recommendation waterfall: Rain? → PSI > threshold? → Recommend / Not |

#### PSI Reference Scale

| PSI | Descriptor | Color |
|---|---|---|
| 0–50 | Good | 🟢 Green |
| 51–100 | Moderate | 🔵 Blue |
| 101–200 | Unhealthy | 🟠 Orange |
| 201–300 | Very Unhealthy | 🔴 Red |
| >300 | Hazardous | 🟤 Maroon |

### 3.4 Monitoring Dashboard

Three-tab Chrome-style UI at `/training`:

| Tab | Content |
|---|---|
| 📥 Download | Daily progress, satellite/NEA file counts, overall progress bar |
| 🧠 Training | 4-phase stepper, batch progress, training history table (MAE, RMSE) |
| 🚀 API | Model/sensor sync status, last sync time |

Log modal with syntax highlighting (ERROR=red, WARNING=orange, SUCCESS=green), auto-refresh every 5 seconds.

### 3.5 Configuration Page (`/settings`)

| Setting | Default | Persistence |
|---|---|---|
| Rainfall / Temperature / Humidity / PM2.5 visibility | All visible | localStorage |
| Interpolation Triangle | Hidden | localStorage |
| Weather Station Markers | Visible | localStorage |

---

## 4. Frontend Features

### Pages & Routes

| Page | Route | Description |
|---|---|---|
| Home | `/` | Interactive Leaflet map + forecast panel + search |
| Settings | `/settings` | Toggle weather metrics, map overlays |
| Popular Places | `/stats` | Search analytics (top 8 locations) |
| Training Monitor | `/training` | Model training pipeline status |
| About | `/about` | Project information |

### Map Markers

| Marker | Color | Description |
|---|---|---|
| User Location | 🔴 Red | Selected/clicked location |
| Contributing Stations | 🟢 Green | 3 stations used for IDW |
| Passive Stations | 🔵 Blue | Other stations |
| Interpolation Triangle | 🟠 Orange dashed | IDW triangulation area |

### Search Types

- **Single Location**: geocode → 3 nearest stations → IDW prediction
- **Path/Route**: OpenStreetMap geometry → sample every 2km → per-point forecast

---

## 5. API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/predict` | GET | Single-point weather forecast |
| `/predict/path` | GET | Path/route weather forecast |
| `/smart-query` | GET | NLU natural language query |
| `/stations` | GET | List all weather stations |
| `/popular-searches` | GET | Top searched locations |
| `/satellite/frames` | GET | Full-day 144-frame cloud animation |
| `/health` | GET | Service health check |
| `/accuracy/summary` | GET | MAE, bias, sample count |
| `/accuracy/by-hour` | GET | Error by hour of day |
| `/accuracy/by-location` | GET | Error by place name |
| `/monitor/overview` | GET | End-to-end pipeline status |
| `/monitor/logs/{type}` | GET | Download/training/sync logs |

---

## 6. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | Prediction response time < 200ms |
| NFR-2 | Background data collection SHALL NOT block API response |
| NFR-3 | NEA API calls rate-limited (max 1 per 5-min cycle) |
| NFR-4 | Collection failures logged but SHALL NOT crash API |
| NFR-5 | All data stored in SQLite alongside existing tables |
| NFR-6 | PSI threshold changes take effect immediately |

---

## 7. Testing

### Coverage Targets

| Phase | Target | Status |
|---|---|---|
| Phase 1 | 35% | ✅ Achieved |
| Phase 2 | 50% | ⏳ |
| Phase 3 | 70% | ⏳ |
| Phase 4 | 80% | ⏳ |

### Test Commands

```bash
npm run test        # Interactive
npm run test:run    # Single run
npm run coverage    # Coverage report
```
