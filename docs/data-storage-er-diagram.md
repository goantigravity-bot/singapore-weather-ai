# Data Storage Schema — ER Diagram

**Generated**: 2026-02-13 | **Database**: SQLite (weather.db) | **Module**: `services/api/db.py`

This diagram covers the 9-table structured data storage schema used by the Weather AI platform to track user queries, forecast predictions, actual weather outcomes, and cross-worker shared caches.

## Entity-Relationship Diagram

```mermaid
erDiagram
    search_history {
        INTEGER id PK "Auto increment"
        TEXT query "Location or NL query"
        TEXT ip_address "Client IP"
        DATETIME timestamp "DEFAULT CURRENT_TIMESTAMP"
        REAL response_time_ms "API latency"
        TEXT response_result "JSON summary"
    }

    user_activity {
        INTEGER query_id PK "Auto increment"
        TEXT query "Natural language query"
        REAL response_time_ms "API latency"
        TEXT forecast_outcome "GO / CAUTION / NOT RECOMMENDED"
        TEXT ip_address "Client IP"
        DATETIME created_at "DEFAULT CURRENT_TIMESTAMP"
    }

    place {
        INTEGER place_id PK "Auto increment"
        TEXT place_name "UNIQUE constraint"
        TEXT place_type "point | path | area"
        REAL center_lat "Center latitude"
        REAL center_lon "Center longitude"
        DATETIME created_at "DEFAULT CURRENT_TIMESTAMP"
    }

    location {
        INTEGER loc_id PK "Auto increment"
        INTEGER place_id FK "References place"
        REAL lat "Latitude"
        REAL lon "Longitude"
        INTEGER point_index "Order in path"
        TEXT label "Optional label"
    }

    activity {
        INTEGER activity_id PK "Auto increment"
        INTEGER query_id FK "References user_activity"
        TEXT activity_name "Cycling, Walking, etc."
        REAL rain_tolerance "mm threshold"
    }

    forecast_result {
        INTEGER forecast_id PK "Auto increment"
        INTEGER query_id FK "References user_activity"
        INTEGER loc_id FK "References location"
        REAL rainfall_mm "Predicted rainfall"
        TEXT status "Clear | Light Rain | Heavy Rain"
        REAL confidence "0.0 to 1.0"
        INTEGER is_risky "Boolean: 0 or 1"
        REAL response_time_ms "Per-point latency"
        DATETIME forecast_time "Prediction target time"
        DATETIME created_at "DEFAULT CURRENT_TIMESTAMP"
    }

    actual_result {
        INTEGER actual_id PK "Auto increment"
        INTEGER loc_id FK "References location"
        REAL actual_rainfall_mm "Observed rainfall"
        TEXT source "DEFAULT NEA"
        DATETIME observation_time "Observation timestamp"
        DATETIME created_at "DEFAULT CURRENT_TIMESTAMP"
    }

    geocode_cache {
        TEXT address PK "Location name or address"
        REAL lat "Cached latitude"
        REAL lon "Cached longitude"
        DATETIME created_at "DEFAULT CURRENT_TIMESTAMP"
    }

    overpass_cache {
        TEXT query PK "OSM query string"
        TEXT data_json "JSON-serialized path data"
        DATETIME created_at "DEFAULT CURRENT_TIMESTAMP"
    }

    user_activity ||--o{ activity : "has activities"
    user_activity ||--o{ forecast_result : "produces forecasts"
    place ||--o{ location : "contains points"
    location ||--o{ forecast_result : "predicted at"
    location ||--o{ actual_result : "observed at"
```

## Table Descriptions

| Table | Purpose | Key Relationships |
|-------|---------|-------------------|
| `search_history` | Legacy table — raw search logging for popular searches aggregation | Standalone |
| `user_activity` | Structured query record — stores each user query with outcome | → activity, → forecast_result |
| `place` | Geographic entity — a named point, path, or area (deduplicated) | → location |
| `location` | Individual coordinate point belonging to a place | → forecast_result, → actual_result |
| `activity` | Detected outdoor activity with rain tolerance threshold | ← user_activity |
| `forecast_result` | AI prediction result per query per location point | ← user_activity, ← location |
| `actual_result` | Real-world observed rainfall from NEA for accuracy tracking | ← location |
| `geocode_cache` | L2 shared cache — Nominatim geocoding results (cross-worker, persistent) | Standalone |
| `overpass_cache` | L2 shared cache — OSM path data as JSON (cross-worker, persistent) | Standalone |

## Indexes

| Index | Table | Column | Purpose |
|-------|-------|--------|---------|
| `idx_location_place` | location | place_id | Fast lookup of points within a place |
| `idx_forecast_query` | forecast_result | query_id | All forecasts for a query |
| `idx_forecast_loc` | forecast_result | loc_id | Forecasts at a specific location |
| `idx_actual_loc` | actual_result | loc_id | Actuals at a specific location |
| `idx_actual_time` | actual_result | observation_time | Time-range queries on observations |

## Data Flow

```mermaid
flowchart LR
    subgraph UserQuery["User Query"]
        Q["Natural Language Input"]
    end

    subgraph Parsing["Query Parsing"]
        P["parse_query"]
    end

    subgraph Storage["SQLite Storage"]
        UA["user_activity"]
        ACT["activity"]
        PL["place"]
        LOC["location"]
        FR["forecast_result"]
        AR["actual_result"]
    end

    Q --> P
    P --> UA
    P --> ACT
    P --> PL --> LOC
    UA --> FR
    LOC --> FR
    LOC --> AR

    subgraph CacheLayer["L2 Cache (SQLite)"]
        GC["geocode_cache"]
        OC["overpass_cache"]
    end

    P -.->|"/predict?location"| GC
    P -.->|"/smart-query"| OC
    GC -.-> LOC
    OC -.-> LOC
```
