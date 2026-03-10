# Haze PSI Alert — Requirements

> **Date**: 2026-02-14 | **Status**: Draft | **Module**: Forecast / Settings

---

## 1. Objective

Integrate real-time PSI (Pollutant Standards Index) data from NEA into the weather forecast to provide **outdoor activity recommendations**. Users can configure a personal PSI threshold in the settings page.

---

## 2. Functional Requirements

### FR-1: PSI Data Collection (Backend)

| ID | Requirement |
|---|---|
| FR-1.1 | System SHALL fetch PSI data from `api-open.data.gov.sg/v2/real-time/api/psi` every 5 minutes (same cycle as sensor data) |
| FR-1.2 | System SHALL cache `psi_twenty_four_hourly` readings for all 5 regions (west, east, central, south, north) |
| FR-1.3 | PSI fetch failure SHALL NOT affect other sensor data collection |

### FR-2: Zone-Based PSI Matching (Backend)

| ID | Requirement |
|---|---|
| FR-2.1 | System SHALL map any coordinate (lat, lon) to the nearest PSI region using region center coordinates |
| FR-2.2 | For **single-point queries** (`/predict`), system SHALL return the PSI reading of the matched region |
| FR-2.3 | For **path queries** (`/smart-query`, `/predict/path`), system SHALL check all regions the path traverses and return the **highest PSI** value |

#### Region Center Coordinates

Source: `regionMetadata` from PSI API response.

| Region | Latitude | Longitude |
|---|---|---|
| West | 1.35735 | 103.700 |
| East | 1.35735 | 103.940 |
| Central | 1.35735 | 103.820 |
| South | 1.29587 | 103.820 |
| North | 1.41803 | 103.820 |

#### Zone Matching Diagram

```
                    NORTH
                  (1.418, 103.82)
                      ●
                      │
         WEST ●───────●───────● EAST
       (103.70)    CENTRAL   (103.94)
                  (103.82)
                      │
                      ●
                    SOUTH
                  (1.296, 103.82)
```

- Matching uses **Euclidean distance** to nearest region center (sufficient for Singapore's scale)

### FR-3: Outdoor Activity Recommendation (Frontend)

| ID | Requirement |
|---|---|
| FR-3.1 | Forecast panel SHALL display a recommendation banner based on weather + PSI |
| FR-3.2 | Recommendation logic SHALL follow a **waterfall** evaluation |
| FR-3.3 | When recommended, the banner SHALL display the PSI reading |
| FR-3.4 | When not recommended, the banner SHALL display the reason (rain or haze) |
| FR-3.5 | PSI value SHALL be color-coded according to NEA standard (see Color Scale below) |

#### Recommendation Waterfall Logic

```
Step 1: Is rain predicted?
  └─ YES → 🌧️ Not Recommended (Rain expected)
  └─ NO  → Step 2

Step 2: Is PSI > user threshold?
  └─ YES → 🌫️ Not Recommended (Haze PSI: XX)
  └─ NO  → ✅ Recommended (PSI: XX)
```

### FR-4: PSI Threshold Configuration (Frontend)

| ID | Requirement |
|---|---|
| FR-4.1 | Settings page SHALL provide a slider to configure PSI threshold |
| FR-4.2 | Slider range SHALL be 0–300 with step 10 |
| FR-4.3 | Default threshold SHALL be **50** |
| FR-4.4 | Threshold SHALL be persisted in `localStorage` |

#### PSI Reference Scale

> For user context, the slider should reference Singapore's NEA PSI scale:

| PSI Range | Descriptor | Color | Health Advisory |
|---|---|---|---|
| 0–50 | Good | 🟢 `#4CAF50` (Green) | Normal activities |
| 51–100 | Moderate | 🔵 `#2196F3` (Blue) | Reduce prolonged outdoor exertion |
| 101–200 | Unhealthy | 🟠 `#FF9800` (Orange) | Avoid prolonged outdoor exertion |
| 201–300 | Very Unhealthy | 🔴 `#F44336` (Red) | Minimize outdoor activities |
| >300 | Hazardous | 🟤 `#880E4F` (Maroon) | Avoid all outdoor activities |

---

## 3. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | PSI fetch SHALL NOT increase `/predict` response time (data pre-cached in background) |
| NFR-2 | PSI data unavailability SHALL gracefully degrade (banner hidden, no crash) |
| NFR-3 | Threshold changes SHALL take effect immediately on next forecast query |

---

## 4. API Response Changes

### `/predict` — Add `psi` to Response

```diff
 "current_weather": {
     "temperature": 31.2,
     "humidity": 72,
-    "pm25": 14
+    "pm25": 14,
+    "psi": 54
 }
```

### `/smart-query` and `/predict/path` — Add `psi` to Result

```diff
 {
     "recommendation": "GO AHEAD",
     "reason": "No rain detected along the route.",
+    "psi": 54,
     "details": [...]
 }
```

- For path queries, `psi` is the **maximum PSI** across all regions traversed

---

## 5. Files Affected

| File | Change |
|---|---|
| `services/api/api.py` | PSI fetch, zone matching, `/predict` response |
| `services/api/smart_query.py` | Inject `psi` into path analysis result |
| `frontend/src/context/ConfigContext.tsx` | Add `psiThreshold` state |
| `frontend/src/pages/SettingsPage.tsx` | Add threshold slider UI |
| `frontend/src/components/ForecastPanel.tsx` | Add recommendation banner |
| `frontend/src/i18n/labels.ts` | Add new labels |
