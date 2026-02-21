# Snowflake Integration Plan — Singapore Weather AI

**Prepared by:** Weather AI Team
**Date:** 2026-02-21
**Purpose:** Share the data export design with the Snowflake team to align on setup and ingestion approach.

---

## 1. Overview

The Singapore Weather AI system runs a real-time weather forecasting pipeline on AWS. We would like to export operational transaction data to Snowflake for analytics and dashboard reporting.

**Data source:** SQLite database (`weather.db`) on the API server (EC2, `ap-southeast-1`)
**Export method:** Incremental CSV files pushed to Amazon S3 every 5 minutes
**S3 bucket:** `s3://weather-ai-models-de08370c/`

---

## 2. S3 Folder Structure

```
s3://weather-ai-models-de08370c/
└── 2snowflake/
    ├── stations.csv                  ← One-time static export (NEA station coordinates)
    ├── 2026-02-21_11-55/             ← Incremental batch (timestamp = export time, UTC+8)
    │   ├── forecast_result.csv
    │   ├── actual_result.csv
    │   ├── user_activity.csv
    │   ├── location.csv
    │   └── place.csv
    ├── 2026-02-21_12-00/
    │   └── (same files, next 5-min window)
    └── ...
```

- Each timestamped subfolder contains **only new records** created in that 5-minute window.
- File names within each subfolder are **always the same** — Snowflake can pattern-match on the subfolder.
- `stations.csv` is written once and updated only if NEA station metadata changes.

---

## 3. Table Schemas

### 3.1 `stations` *(one-time load)*
NEA weather station reference data. Static — stations rarely change location.

| Column | Type | Description |
|--------|------|-------------|
| `station_id` | STRING | NEA station identifier (e.g. `S111`) |
| `station_name` | STRING | Human-readable name (e.g. `Newton`) |
| `lat` | FLOAT | Station latitude |
| `lon` | FLOAT | Station longitude |

---

### 3.2 `forecast_result` *(incremental — backtest records only)*
Model predictions generated every 10 minutes for 10 fixed benchmark locations across Singapore.

| Column | Type | Description |
|--------|------|-------------|
| `forecast_id` | INT | Primary key |
| `loc_id` | INT | FK → `location.loc_id` |
| `rainfall_mm` | FLOAT | Predicted rainfall (mm / 10 min) |
| `status` | STRING | `No Rain` / `Light` / `Moderate` / `Heavy` |
| `confidence` | FLOAT | Model confidence score (0–1) |
| `is_risky` | INT | 1 if rainfall_mm ≥ 2.0, else 0 |
| `forecast_time` | TIMESTAMP | Time the prediction was made (SGT) |
| `created_at` | TIMESTAMP | DB write time |

> Only records with `source = 'backtest'` are exported. User-triggered predictions are excluded.

---

### 3.3 `actual_result` *(incremental)*
Observed rainfall from the nearest NEA station, automatically matched to each backtest forecast within a 30-minute window.

| Column | Type | Description |
|--------|------|-------------|
| `actual_id` | INT | Primary key |
| `loc_id` | INT | FK → `location.loc_id` (joins to `forecast_result`) |
| `actual_rainfall_mm` | FLOAT | Real observed rainfall (mm / 10 min) |
| `station_id` | STRING | NEA station used for matching (joins to `stations`) |
| `match_distance_km` | FLOAT | Distance from forecast point to NEA station |
| `observation_time` | TIMESTAMP | Time of NEA observation (SGT) |
| `created_at` | TIMESTAMP | DB write time |

---

### 3.4 `user_activity` *(incremental)*
Logs of user queries submitted to the prediction API.

| Column | Type | Description |
|--------|------|-------------|
| `query_id` | INT | Primary key |
| `query` | STRING | Natural language query text |
| `response_time_ms` | FLOAT | API response latency (ms) |
| `forecast_outcome` | STRING | Summary of prediction returned |
| `ip_address` | STRING | SHA-256 hashed (PII masked) |
| `created_at` | TIMESTAMP | Query time (SGT) |

---

### 3.5 `location` *(incremental / slow-changing)*
Coordinate points associated with each forecast or query.

| Column | Type | Description |
|--------|------|-------------|
| `loc_id` | INT | Primary key |
| `place_id` | INT | FK → `place.place_id` |
| `lat` | FLOAT | Latitude of the point |
| `lon` | FLOAT | Longitude of the point |

---

### 3.6 `place` *(incremental / slow-changing)*
Named locations (benchmark sites, user-queried places).

| Column | Type | Description |
|--------|------|-------------|
| `place_id` | INT | Primary key |
| `place_name` | STRING | e.g. `backtest:Newton`, `Marina Bay` |
| `center_lat` | FLOAT | Representative latitude |
| `center_lon` | FLOAT | Representative longitude |

---

## 4. Entity Relationship

```
stations ←──────────────────── actual_result
                                     │
place ──── location ─────── forecast_result
                  └───────── actual_result
user_activity (standalone for usage analytics)
```

**Key JOIN for accuracy analysis:**
```sql
SELECT
    p.place_name,
    HOUR(f.forecast_time)                                  AS hour_of_day,
    AVG(ABS(f.rainfall_mm - a.actual_rainfall_mm))         AS mae,
    AVG(f.rainfall_mm - a.actual_rainfall_mm)              AS bias,
    COUNT(*)                                               AS sample_count
FROM forecast_result f
JOIN actual_result a
    ON  f.loc_id = a.loc_id
    AND ABS(DATEDIFF('minute', f.forecast_time, a.observation_time)) < 30
JOIN location l ON f.loc_id = l.loc_id
JOIN place   p  ON l.place_id = p.place_id
GROUP BY p.place_name, hour_of_day
ORDER BY mae DESC;
```

---

## 5. AWS Side — What We Provide

We will configure an **IAM Role** on our AWS account that grants Snowflake read-only access to the `2snowflake/` prefix.

**IAM Policy:**
```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:ListBucket"],
  "Resource": [
    "arn:aws:s3:::weather-ai-models-de08370c",
    "arn:aws:s3:::weather-ai-models-de08370c/2snowflake/*"
  ]
}
```

We will need the **Snowflake Storage Integration ARN** (provided by the Snowflake team after creating the integration) to complete the IAM trust relationship.

---

## 6. Snowflake Side — Setup Required

```sql
-- Step 1: Create Storage Integration
CREATE OR REPLACE STORAGE INTEGRATION weather_ai_s3_integration
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  ENABLED = TRUE
  STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::<our_account_id>:role/snowflake-weather-ai-reader'
  STORAGE_ALLOWED_LOCATIONS = ('s3://weather-ai-models-de08370c/2snowflake/');

-- Retrieve the Snowflake IAM values to send back to us:
DESC INTEGRATION weather_ai_s3_integration;
-- → STORAGE_AWS_IAM_USER_ARN and STORAGE_AWS_EXTERNAL_ID

-- Step 2: Create External Stage
CREATE OR REPLACE STAGE weather_ai_stage
  URL = 's3://weather-ai-models-de08370c/2snowflake/'
  STORAGE_INTEGRATION = weather_ai_s3_integration
  FILE_FORMAT = (TYPE = 'CSV' FIELD_OPTIONALLY_ENCLOSED_BY = '"' SKIP_HEADER = 1);

-- Step 3: Create tables (schemas as above in Section 3)

-- Step 4: One-time load for stations
COPY INTO stations FROM @weather_ai_stage/stations.csv;

-- Step 5: Incremental load (per batch folder)
COPY INTO forecast_result FROM @weather_ai_stage/2026-02-21_12-00/forecast_result.csv;
COPY INTO actual_result   FROM @weather_ai_stage/2026-02-21_12-00/actual_result.csv;
COPY INTO user_activity   FROM @weather_ai_stage/2026-02-21_12-00/user_activity.csv;
COPY INTO location        FROM @weather_ai_stage/2026-02-21_12-00/location.csv;
COPY INTO place           FROM @weather_ai_stage/2026-02-21_12-00/place.csv;
```

---

## 7. Planned Snowsight Dashboards

| Dashboard | Primary Tables | Key Metrics |
|-----------|---------------|-------------|
| **Model Accuracy** | `forecast_result` ⟕ `actual_result` ⟕ `place` | MAE, Bias by hour / location / rain intensity |
| **User Behaviour** | `user_activity` ⟕ `place` | Daily query volume, top queried locations, response time trend |
| **API Performance** | `forecast_result` | P50 / P95 response time, backtest coverage rate |

---

## 8. Open Questions for Snowflake Team

| # | Question |
|---|----------|
| 1 | Which Snowflake account / database / schema should we target? |
| 2 | Will you configure **Snowpipe** for automated ingestion, or will loading be triggered manually? |
| 3 | Please share `STORAGE_AWS_IAM_USER_ARN` and `STORAGE_AWS_EXTERNAL_ID` after creating the Storage Integration so we can complete the IAM trust policy on our side. |
| 4 | Any preference on the Snowsight dashboard layout or additional metrics to include? |
