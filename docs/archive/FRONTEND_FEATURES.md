# Singapore Weather AI - Frontend Features

## Overview

The Weather AI frontend is a React-based single-page application that provides real-time weather forecasting for Singapore using AI-powered predictions.

**Live URL**: http://3.0.28.161:8000/

---

## 🏠 Main Features

| Feature | Description |
|---------|-------------|
| **Interactive Map** | Leaflet-based map of Singapore with weather station markers |
| **Location Search** | Search by location name (e.g., "Sentosa", "Changi Airport") |
| **Map Click Forecast** | Click anywhere on map to get weather forecast for that location |
| **Geolocation** | Auto-detect user's current location on app load |
| **Path Forecast** | Search for routes/paths (e.g., "Rail Corridor") to see weather along the path |

---

## 🌦️ Weather Forecast Panel

The forecast panel displays real-time weather data with the following metrics:

| Metric | Description | Unit |
|--------|-------------|------|
| **Rainfall Prediction** | AI-powered 10-minute rainfall forecast | mm |
| **Temperature** | Current temperature reading | °C |
| **Humidity** | Current relative humidity | % |
| **PM2.5** | Air quality index | μg/m³ |

### Rainfall Descriptions

| Value | Description |
|-------|-------------|
| < 0.1 mm | Clear / No Rain |
| 0.1 - 2.0 mm | Light Rain |
| > 2.0 mm | Heavy Rain / Storm |

---

## 🗺️ Map Visualization

### Marker Types

| Element | Color | Description |
|---------|-------|-------------|
| **User Location** | 🔴 Red | Selected/clicked location by user |
| **Contributing Stations** | 🟢 Green | Weather stations used for IDW interpolation |
| **Passive Stations** | 🔵 Blue | Other available weather stations |

### Overlays

| Overlay | Color | Description |
|---------|-------|-------------|
| **Interpolation Triangle** | 🟠 Orange (dashed) | Shows the 3 stations used for weighted prediction |
| **Path Route** | 🟣 Purple | Route visualization with forecast points |

---

## 📱 Pages & Routes

| Page | Route | Description |
|------|-------|-------------|
| **Home** | `/` | Main map + forecast view |
| **Settings** | `/settings` | Toggle visibility of weather metrics |
| **Popular Places** | `/stats` | Shows popular search locations based on user history |
| **Training Monitor** | `/training` | View model training status, history, and metrics |
| **About** | `/about` | Application information and credits |

---

## ⚙️ Settings Page

Users can customize which weather metrics are displayed:

| Setting | Default | Description |
|---------|---------|-------------|
| **Rainfall Prediction** | ✅ Visible | Toggle rainfall forecast display |
| **Temperature** | ✅ Visible | Toggle temperature display |
| **Humidity** | ✅ Visible | Toggle humidity display |
| **PM2.5** | ✅ Visible | Toggle air quality display |
| **Interpolation Triangle** | ❌ Hidden | Visualize 3-station IDW interpolation area |

---

## 📊 Training Monitor Page

The training monitor provides visibility into the AI model training pipeline:

### Status Card
- **Training Status**: Active / Idle / Completed / Failed
- **Current Batch**: Progress through data batches
- **Current Step**: Download / Preprocess / Train / Sync
- **Date Range**: Data period being processed

### Training History Table

| Column | Description |
|--------|-------------|
| **ID** | Training run identifier |
| **Timestamp** | When training completed |
| **Date Range** | Data period used for training |
| **Duration** | Training time |
| **MAE** | Mean Absolute Error (lower is better) |
| **RMSE** | Root Mean Square Error |
| **Status** | ✅ Success / ❌ Failed |

### Features
- Auto-refresh every 30 seconds
- Links to full monitoring dashboard (`/monitor/`)

---

## 🍔 Side Menu Navigation

| Menu Item | Icon | Route | Description |
|-----------|------|-------|-------------|
| **Popular Places** | 🏛️ | `/stats` | View popular search locations |
| **Training Monitor** | 📈 | `/training` | Model training status |
| **Settings** | ⚙️ | `/settings` | App configuration |
| **About** | ℹ️ | `/about` | App information |

---

## 🔍 Search Features

### Single Location Search
```
Example: "Sentosa", "Changi Airport", "Orchard Road"
```
- Geocodes the location
- Finds 3 nearest weather stations
- Uses IDW interpolation for prediction
- Displays forecast in panel

### Path/Route Search
```
Example: "Rail Corridor", "East Coast Park"
```
- Fetches route geometry from OpenStreetMap
- Samples points along the path
- Predicts weather at each sample point
- Visualizes path with color-coded forecast markers

---

## 🎨 Design System

### Theme
- **Style**: Dark glassmorphism
- **Primary Color**: Cyan (`#00bcd4`)
- **Secondary Colors**: Orange, Green, Red for status indicators
- **Background**: Semi-transparent dark panels with blur effect

### Responsive Design
- Mobile-friendly layout
- Touch-optimized map interactions
- Collapsible side menu

---

## 📝 Tech Stack

| Layer | Technology | Version |
|-------|------------|---------|
| **Framework** | React | 18.x |
| **Language** | TypeScript | 5.x |
| **Routing** | React Router | v6 |
| **State Management** | React Context API | Built-in |
| **Map Library** | Leaflet + react-leaflet | 4.x |
| **HTTP Client** | Axios | 1.x |
| **Build Tool** | Vite | 5.x |
| **Styling** | Vanilla CSS | - |

---

## 📁 Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── ForecastPanel.tsx    # Weather forecast display
│   │   ├── MapComponent.tsx     # Interactive Leaflet map
│   │   ├── QuickLinks.tsx       # Popular places chips
│   │   └── SideMenu.tsx         # Navigation menu
│   ├── pages/
│   │   ├── AboutPage.tsx        # About page
│   │   ├── SettingsPage.tsx     # Settings configuration
│   │   ├── StatsPage.tsx        # Popular places stats
│   │   └── TrainingMonitor.tsx  # Training status page
│   ├── context/
│   │   └── ConfigContext.tsx    # Global app configuration
│   ├── App.tsx                  # Main application component
│   ├── config.ts                # API configuration
│   ├── index.css                # Global styles
│   └── main.tsx                 # Entry point
├── public/
├── package.json
└── vite.config.ts
```

---

## 🔗 API Integration

The frontend communicates with the backend API:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/predict` | GET | Single location weather forecast |
| `/predict/path` | GET | Path/route weather forecast |
| `/stations` | GET | List all weather stations |
| `/log-search` | POST | Log user search queries |
| `/popular-searches` | GET | Get popular search locations |
| `/training/status` | GET | Get current training status |
| `/training/history` | GET | Get training history |

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-29 | 1.0 | Initial documentation |
| 2026-01-29 | 1.1 | Added Training Monitor, removed main page Popular Places chips, added side menu links |
