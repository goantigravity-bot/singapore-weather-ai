#!/bin/bash
# sync_model_to_s3.sh
# Syncs trained models and history to S3

S3_BUCKET="s3://weather-ai-models-de08370c"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Ensure AWS CLI is configured
if ! command -v aws &> /dev/null; then
    echo "Error: aws cli not found"
    exit 1
fi

echo "Syncing models to $S3_BUCKET..."

# Check for custom endpoint (e.g., local moto server)
ENDPOINT_FLAG=""
if [ -n "$S3_ENDPOINT_URL" ]; then
    ENDPOINT_FLAG="--endpoint-url $S3_ENDPOINT_URL"
    echo "Using custom endpoint: $S3_ENDPOINT_URL"
fi

# 1. Upload Model
if [ -f "weather_fusion_model.pth" ]; then
    aws s3 cp weather_fusion_model.pth "$S3_BUCKET/models/$TIMESTAMP/weather_fusion_model.pth" $ENDPOINT_FLAG
    aws s3 cp weather_fusion_model.pth "$S3_BUCKET/models/latest.pth" $ENDPOINT_FLAG
    echo "✅ Uploaded model"
else
    echo "⚠️ Model file not found"
fi

# 2. Upload History
if [ -f "training_history.json" ]; then
    aws s3 cp training_history.json "$S3_BUCKET/history/training_history.json" $ENDPOINT_FLAG
    echo "✅ Uploaded history"
fi

# 3. Upload State
if [ -f "training_state.json" ]; then
    aws s3 cp training_state.json "$S3_BUCKET/state/training_state.json" $ENDPOINT_FLAG
    echo "✅ Uploaded state"
fi
