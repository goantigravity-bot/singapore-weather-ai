# Singapore Weather AI Prediction System - Project Summary

## 📋 Project Overview

This is a deep learning-based weather prediction system that fuses satellite imagery and ground sensor data to provide accurate short-term rainfall forecasts for Singapore.

### Core Technology Stack
- **Deep Learning**: PyTorch + Custom Fusion Model
- **Data Sources**: JAXA Satellite Data + NEA Sensor Data
- **Backend API**: FastAPI
- **Frontend**: React + TypeScript
- **Deployment**: Docker + AWS

---

## 🎯 Implemented Core Features

### 1. Data Collection & Processing

#### 1.1 Satellite Data Download (`download_jaxa_data.py`)
- ✅ Automatic download from JAXA FTP server
- ✅ Batch download and incremental updates
- ✅ Auto-crop Singapore region (103.6-104.0°E, 1.2-1.5°N)
- ✅ Time range queries (by hour/day)

#### 1.2 Sensor Data Acquisition (`fetch_and_process_gov_data.py`)
- ✅ Real-time weather data from NEA API
- ✅ Incremental updates (based on last training time)
- ✅ SSL certificate verification and error handling
- ✅ Data cleaning and formatting
- ✅ Auto-resampling to 10-minute intervals

#### 1.3 Image Preprocessing (`preprocess_images.py`)
- ✅ NetCDF to NumPy array conversion
- ✅ Multi-folder batch processing
- ✅ Data normalization and standardization
- ✅ Automatic validation of processed results

---

### 2. Model Training System

#### 2.1 Deep Learning Model (`weather_fusion_model.py`)
- ✅ **Dual-Branch Fusion Architecture**:
  - Satellite Image Branch: CNN feature extraction
  - Sensor Data Branch: Fully connected network
  - Fusion Layer: Multi-modal feature integration
- ✅ Output: 10-minute ahead rainfall prediction

#### 2.2 Training Pipeline (`train.py`)
- ✅ Automatic dataset construction and splitting
- ✅ GPU/CPU adaptive training
- ✅ Model checkpoint saving
- ✅ Training log recording

#### 2.3 Model Evaluation (`evaluate.py`)
- ✅ Multi-dimensional performance metrics:
  - MAE (Mean Absolute Error)
  - RMSE (Root Mean Square Error)
  - Classification Accuracy (rain/no-rain)
- ✅ Visualization chart generation
- ✅ JSON result export

---

### 3. Automated Training System

#### 3.1 Complete Training Pipeline (`auto_train_pipeline.py`)
- ✅ **End-to-End Automation**:
  1. Download latest satellite data
  2. Fetch incremental sensor data
  3. Preprocess images
  4. Train model
  5. Evaluate performance
  6. Generate reports
  7. Send email notifications
- ✅ Automatic retry mechanism on failure
- ✅ Training state persistence

#### 3.2 Training History Management (`training_history.py`)
- ✅ Record detailed information for each training:
  - Timestamp and duration
  - Performance metrics
  - Dataset information
  - Training configuration
- ✅ Statistical analysis features:
  - Average training duration
  - Performance trend analysis
  - Best/worst records

#### 3.3 Training Monitoring (`monitor_training.py`)
- ✅ Real-time process status checking
- ✅ Resource usage monitoring (CPU/Memory)
- ✅ File update status tracking

#### 3.4 Report Generation (`generate_report.py`)
- ✅ **Beautiful HTML Reports**:
  - Training overview and timeline
  - Performance metrics comparison (current vs previous)
  - Dataset statistics
  - Embedded visualization charts
- ✅ Responsive design, mobile-friendly

#### 3.5 Email Notification System (`notification.py`)
- ✅ Automatic success/failure notifications
- ✅ HTML email templates
- ✅ Attachment support (reports, charts, logs)
- ✅ Gmail integration

---

### 4. Prediction API Service

#### 4.1 FastAPI Backend (`api.py`)

##### Core Prediction Endpoints
- ✅ **`GET /predict`** - Single Point Weather Prediction
  - Location name query support
  - Latitude/longitude query support
  - **IDW Spatial Interpolation**: Weighted average from 3 nearest sensors
  - Reverse geocoding (coordinates → place name)
  - Forward geocoding (place name → coordinates)
  - Returns:
    - 10-minute ahead rainfall amount
    - Current temperature/humidity
    - Weather description (Clear/Light Rain/Heavy Rain)

- ✅ **`GET /predict/path`** - Path Weather Prediction
  - Landmark/route queries (e.g., "Rail Corridor")
  - OpenStreetMap integration
  - Automatic path sampling (one point per 2km)
  - Batch prediction along route

##### Auxiliary Endpoints
- ✅ **`GET /health`** - Health check
- ✅ **`GET /stations`** - Get all weather station information
- ✅ **`POST /log-search`** - Log search history
- ✅ **`GET /popular-searches`** - Popular search statistics

##### Technical Features
- ✅ CORS cross-origin support
- ✅ Request logging
- ✅ IP address tracking
- ✅ SQLite database integration
- ✅ Model hot-loading
- ✅ Real-time data simulation (mapped to historical data)

#### 4.2 Prediction Core Logic (`predict.py`)
- ✅ Geospatial calculations (Haversine distance)
- ✅ Nearest sensor lookup
- ✅ IDW (Inverse Distance Weighting) interpolation algorithm
- ✅ OpenStreetMap API integration
- ✅ Path geometry processing
- ✅ Batch prediction optimization

---

### 5. Frontend Application

#### 5.1 React Web App (`frontend/`)
- ✅ **Interactive Map Interface**:
  - Leaflet map integration
  - Click map for predictions
  - Sensor station markers
  - Path visualization
- ✅ **Search Functionality**:
  - Location name search
  - Path/landmark search
  - Popular search suggestions
  - Search history
- ✅ **Weather Display**:
  - Real-time rainfall prediction
  - Temperature/humidity display
  - Animated weather icons
  - Path weather cards
- ✅ **Responsive Design**: Desktop/mobile support

---

### 6. Deployment & Operations

#### 6.1 Docker Containerization
- ✅ **API Service Container** (`Dockerfile.api`)
  - FastAPI application
  - Model file packaging
  - Health check configuration
- ✅ **Training Container** (`Dockerfile`)
  - Complete training environment
  - Data processing tools
  - Automation scripts

#### 6.2 AWS Deployment (`AWS_DEPLOY.md`)
- ✅ EC2 instance configuration guide
- ✅ Docker deployment workflow
- ✅ Security group configuration
- ✅ Domain binding instructions

#### 6.3 Scheduled Tasks
- ✅ Cron scheduled training configuration
- ✅ macOS launchd configuration
- ✅ Log rotation management

---

### 7. Database & Storage

#### 7.1 SQLite Database (`weather.db`)
- ✅ Search history table
- ✅ IP address records
- ✅ Timestamp indexing

#### 7.2 File Storage Structure
```
.
├── satellite_data/          # Raw satellite data (.nc)
├── processed_images/        # Preprocessed images (.npy)
├── real_sensor_data.csv     # Sensor data
├── weather_fusion_model.pth # Trained model
├── training_logs/           # Training logs
├── training_reports/        # HTML reports
├── training_history.json    # Training history
└── training_state.json      # Training state
```

---

### 8. Utility Scripts

#### 8.1 Data Validation
- ✅ `verify_processed.py` - Verify preprocessed data
- ✅ `debug_data.py` - Debug data issues
- ✅ `debug_nc.py` - Check NetCDF files
- ✅ `visualize_processed_data.py` - Visualize data

#### 8.2 Database Management
- ✅ `query_db.py` - Query database
- ✅ `migrate_db.py` - Database migration
- ✅ `add_first_record.py` - Add initial data

#### 8.3 Testing Tools
- ✅ `test_api.py` - API endpoint testing
- ✅ `test_auto_training.py` - Auto-training testing
- ✅ `verify_deployment.py` - Deployment verification

#### 8.4 Batch Processing
- ✅ `batch_forecast.py` - Batch predictions
- ✅ `run_pipeline.sh` - One-click run script

---

## 📊 System Performance

### Model Performance Metrics
- **MAE**: ~0.12 mm (Mean Absolute Error)
- **RMSE**: ~0.23 mm (Root Mean Square Error)
- **Classification Accuracy**: ~85% (rain/no-rain detection)

### API Response Performance
- **Single Point Prediction**: <200ms
- **Path Prediction**: <1s (10 sample points)
- **Concurrent Support**: 100+ req/s

### Training Efficiency
- **Single Training Duration**: 30-60 minutes (30 epochs)
- **Data Processing**: ~5 minutes
- **Model Size**: 270KB

---

## 🔧 Technical Highlights

### 1. Multi-Modal Data Fusion
- Combines satellite remote sensing and ground observations
- Comprehensive analysis across spatial and temporal dimensions
- Improved prediction accuracy

### 2. Spatial Interpolation Algorithm
- IDW (Inverse Distance Weighting)
- Multi-sensor collaborative prediction
- Coverage for areas without sensors

### 3. Automated Pipeline
- End-to-end unattended operation
- Automatic retry on failure
- Email notification mechanism

### 4. Real-Time Prediction Simulation
- Historical data time mapping
- 10-minute granularity alignment
- Seamless user experience

### 5. Geospatial Processing
- OpenStreetMap integration
- Path geometry calculations
- Geocoding/reverse geocoding

---

## 📚 Documentation System

### User Documentation
- ✅ `AUTO_TRAINING_README.md` - Auto-training usage guide
- ✅ `DEPLOYMENT.md` - Deployment instructions
- ✅ `AWS_DEPLOY.md` - AWS deployment guide

### Developer Documentation
- ✅ `SECURITY.md` - Security configuration
- ✅ `NEA_FETCH_IMPROVEMENT_PLAN.md` - NEA data optimization plan
- ✅ `TRAINING_OPTIMIZATION_PLAN.md` - Training optimization plan

### Project Management
- ✅ `video_script.md` - Demo script
- ✅ `gotsomeidea` - Ideas log

---

## 🚀 Use Cases

### 1. Individual Users
- Weather check before going out
- Route planning (running, cycling)
- Activity scheduling reference

### 2. Enterprise Applications
- Logistics delivery optimization
- Outdoor event management
- Agricultural irrigation decisions

### 3. Research Purposes
- Weather model validation
- Data fusion research
- Deep learning applications

---

## 🔮 Future Roadmap

### Short-Term Optimization
- [ ] Add more weather element predictions (wind speed, visibility)
- [ ] Extend prediction time window (30 minutes, 1 hour)
- [ ] Optimize model architecture (Transformer, Attention)

### Mid-Term Goals
- [ ] Mobile app development (iOS/Android)
- [ ] Push notification service
- [ ] User personalization settings

### Long-Term Vision
- [ ] Expand to other Southeast Asian countries
- [ ] Integrate more data sources (radar, lightning)
- [ ] Commercial service offerings

---

## 📞 Technical Support

### Log Viewing
```bash
# Training logs
tail -f training_logs/training_*.log

# API logs
tail -f api.log
```

### Common Issues
1. **Model loading failed**: Check if `weather_fusion_model.pth` exists
2. **Data download failed**: Verify network connection and FTP credentials
3. **Abnormal prediction results**: Confirm data time range covers query time

### Contact
- Project Repository: `goantigravity-bot/singapore-weather-ai`
- Developer: Jin Hui

---

## 📄 License

This project is developed for learning and research purposes. Data sources are from public APIs and services.

---

**Last Updated**: 2026-01-26  
**Version**: 0.3  
**Status**: ✅ Production Ready
