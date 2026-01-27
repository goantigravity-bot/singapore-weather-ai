#!/bin/bash
# fetch_latest_model.sh
# Helper for API server to pull latest model

S3_BUCKET="s3://weather-ai-models-de08370c"
MODEL_FILE="weather_fusion_model.pth"

echo "Fetching latest model from $S3_BUCKET..."

ENDPOINT_FLAG=""
if [ -n "$S3_ENDPOINT_URL" ]; then
    ENDPOINT_FLAG="--endpoint-url $S3_ENDPOINT_URL"
    echo "Using custom endpoint: $S3_ENDPOINT_URL"
fi

if [ -f "$MODEL_FILE" ]; then
    cp "$MODEL_FILE" "${MODEL_FILE}.backup"
    echo "Backed up current model."
fi

aws s3 cp "$S3_BUCKET/models/latest.pth" "$MODEL_FILE" $ENDPOINT_FLAG

if [ $? -eq 0 ]; then
    echo "✅ Successfully downloaded latest model."
    
    # 下载传感器数据
    echo "Fetching sensor data..."
    aws s3 cp "$S3_BUCKET/sensor_data/real_sensor_data.csv" "real_sensor_data.csv" $ENDPOINT_FLAG 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Successfully downloaded sensor data."
    else
        echo "⚠️ Sensor data not available in S3 (using existing local copy)."
    fi
    
    # Optional: Restart API service
    # sudo systemctl restart weather-api
else
    echo "❌ Failed to download model."
    # Restore backup if download failed
    if [ -f "${MODEL_FILE}.backup" ]; then
        mv "${MODEL_FILE}.backup" "$MODEL_FILE"
        echo "Restored backup."
    fi
    exit 1
fi
