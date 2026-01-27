#!/bin/bash
# fetch_latest_model.sh
# Helper for API server to pull latest model

S3_BUCKET="s3://weather-ai-models-jinhui"
MODEL_FILE="weather_fusion_model.pth"

echo "Fetching latest model from $S3_BUCKET..."

if [ -f "$MODEL_FILE" ]; then
    cp "$MODEL_FILE" "${MODEL_FILE}.backup"
    echo "Backed up current model."
fi

aws s3 cp "$S3_BUCKET/models/latest.pth" "$MODEL_FILE"

if [ $? -eq 0 ]; then
    echo "✅ Successfully downloaded latest model."
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
