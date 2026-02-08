# Source this file to set up environment for local development
# Usage: source local_env_setup.sh

# AWS / MinIO
export AWS_ACCESS_KEY_ID=minioadmin
export AWS_SECRET_ACCESS_KEY=minioadmin
export AWS_DEFAULT_REGION=us-east-1
export S3_ENDPOINT_URL=http://localhost:9000
export S3_BUCKET=weather-ai-models-de08370c

# Paths
export FRONTEND_DIR=../../frontend/dist
export WORK_DIR=$(pwd)/data  # For training service

# JAXA (From .env.production)
export JAXA_USER=jinhui.sg_gmail.com
export JAXA_PASS=SP+wari8

# Settings
# Modes: 
# - DAILY: Incremental training (Waits for today's data)
# - BACKFILL: Historical training loop (Iterates from START_DATE to END_DATE)
export TRAINING_MODE=DAILY
export CHECK_INTERVAL_REALTIME=300

echo "✅ Environment variables set for LOCAL development."
echo "   S3 Endpoint: $S3_ENDPOINT_URL"
echo "   Bucket: $S3_BUCKET"
