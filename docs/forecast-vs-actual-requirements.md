# Forecast vs Actual — Requirements & Considerations

> **Date**: 2026-02-13 | **Status**: Draft | **Module**: actual_collector

---

## 1. Objective

Build a closed-loop system that automatically collects actual rainfall observations after each forecast, enabling error analysis to identify model weaknesses and drive targeted improvements.

## 2. Functional Requirements

### FR-1: Automatic Actual Rainfall Collection

| ID | Requirement |
|---|---|
| FR-1.1 | System SHALL scan `forecast_result` for records without matching `actual_result` every 5 minutes |
| FR-1.2 | System SHALL call NEA Rainfall API (`api.data.gov.sg/v1/environment/rainfall`) to fetch observed values |
| FR-1.3 | System SHALL match forecast to the nearest NEA station within `MAX_MATCH_DISTANCE_KM` |
| FR-1.4 | System SHALL record `match_distance_km` and `station_id` with each actual result for quality traceability |
| FR-1.5 | System SHALL skip matching when nearest station exceeds `MAX_MATCH_DISTANCE_KM` and log the skip |

### FR-2: Error Analysis

| ID | Requirement |
|---|---|
| FR-2.1 | System SHALL provide MAE, bias, and sample count aggregated by **hour of day** |
| FR-2.2 | System SHALL provide MAE and sample count aggregated by **place name** |
| FR-2.3 | System SHALL provide MAE and bias aggregated by **rain level** (None / Light / Moderate / Heavy) |
| FR-2.4 | System SHALL expose analysis results via REST API endpoints (`/accuracy/*`) |

---

## 3. Station Matching Distance — Design Rationale

### 3.1 Rain Cell Size in Tropical Singapore

Singapore's rainfall is dominated by **convective storms** (~70% of all events). The spatial extent of a single rain cell determines how reliably a station reading represents actual conditions at the forecast point.

| Rain Type | Cell Diameter | Duration | Frequency |
|---|---|---|---|
| **Convective** (afternoon thunderstorm) | 2–10 km | 30–60 min | ~70% of events |
| **Stratiform** (monsoon rain) | 50–200 km | Hours to days | ~25% of events |
| **Squall Line** | 20–50 km wide | 1–3 hours | ~5% of events |

**Key insight**: Convective storms can produce the "one street raining, opposite street dry" phenomenon. Within a 5 km radius, two points may experience completely different rainfall conditions during a convective event.

```
Convective Rain Cell (typical)

        ←── 5 km ──→
    ┌───────────────────┐
    │   ☔ Rain area     │  Outer boundary: 5-10 km
    │  ┌─────────────┐  │
    │  │  Core zone   │  │  Heaviest rainfall: 1-2 km
    │  │  > 10 mm/hr  │  │
    │  └─────────────┘  │
    └───────────────────┘
    ← Edge: nearby area may be completely dry →
```

### 3.2 NEA Station Density in Singapore

Singapore has **60+ rainfall stations** across ~730 km². Typical nearest-station distances:

| Area | Typical Distance to Nearest Station |
|---|---|
| Central / East (urban) | < 2 km |
| West / North (suburban) | 2–5 km |
| Offshore islands (Pulau Ubin) | 5–8 km |

### 3.3 Chosen Threshold: 5 km

**Decision**: `MAX_MATCH_DISTANCE_KM = 5.0`

| Option | Coverage | Accuracy Risk | Verdict |
|---|---|---|---|
| 100 m | < 5% of forecasts matched | None | ❌ Too restrictive, almost no data |
| 1 km | ~40% | Low | ❌ Suburban areas excluded |
| **5 km** | **~95%** | **Moderate for convective** | **✅ Best balance** |
| No limit | 100% | High for offshore | ❌ Unreliable data for islands |

### 3.4 Mitigation: Distance-Aware Quality

To address the inaccuracy risk for convective events at 3–5 km distance:

1. **Record `match_distance_km`** with every actual result
2. **Post-hoc sensitivity analysis**: Compare MAE at `< 1km` vs `1-3km` vs `3-5km`
3. If MAE degrades significantly with distance, **narrow the threshold** or **down-weight** distant matches
4. Strategy: **Collect broadly (5 km), analyze with distance bins, then refine**

---

## 4. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | Actual collection SHALL NOT block or degrade API response time (background thread) |
| NFR-2 | NEA API calls SHALL be rate-limited (max 1 call per 5-minute cycle) |
| NFR-3 | Collection failures SHALL be logged but SHALL NOT crash the API server |
| NFR-4 | All collected data SHALL be stored in SQLite alongside existing tables |

---

## 5. Data Schema Changes

### 5.1 `actual_result` Table — Add Columns

| Column | Type | Purpose |
|---|---|---|
| `station_id` | TEXT | NEA station used for matching (traceability) |
| `match_distance_km` | REAL | Distance from forecast point to matched station |

### 5.2 New Index

| Index | Table | Column | Purpose |
|---|---|---|---|
| `idx_forecast_time` | `forecast_result` | `forecast_time` | Accelerate time-range scan for unmatched forecasts |

---

## 6. API Endpoints

| Endpoint | Method | Response |
|---|---|---|
| `GET /accuracy/summary` | GET | `{ mae, bias, sample_count, match_rate }` |
| `GET /accuracy/by-hour` | GET | `[{ hour, mae, bias, count }]` |
| `GET /accuracy/by-location` | GET | `[{ place_name, mae, count }]` |

---

## 7. Open Questions

| # | Question | Current Decision | To Validate |
|---|---|---|---|
| 1 | 5 km threshold appropriate? | Yes (collect now, validate later) | Compare MAE across distance bins after 1 week of data |
| 2 | Time window for matching? | ≤ 30 min between forecast_time and observation_time | Check NEA data freshness (typically 5-min intervals) |
| 3 | Multiple stations within range? | Use nearest only | Consider weighted average of 2-3 nearest stations |
