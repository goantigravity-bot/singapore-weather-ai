# Source this file to set up environment for PRODUCTION (Actual AWS S3)
# Usage: source prod_env_setup.sh

# --- AWS Config ---
# Clear any previous MinIO credentials so we use actual AWS config (from 'aws configure')
unset AWS_ACCESS_KEY_ID
unset AWS_SECRET_ACCESS_KEY
unset S3_ENDPOINT_URL

# We do NOT set Keys here. 
# Please run 'aws configure' to set your credentials securely,
# or export them manually if needed.
# export AWS_ACCESS_KEY_ID=YOUR_REAL_KEY
# export AWS_SECRET_ACCESS_KEY=YOUR_REAL_SECRET
export AWS_DEFAULT_REGION=ap-southeast-1

# Bucket Name (Ensure this exists in your AWS account)
export S3_BUCKET=weather-ai-models-de08370c

# --- JAXA Credentials ---
export JAXA_USER=jinhui.sg_gmail.com
export JAXA_PASS=SP+wari8

# --- App Settings ---
export TRAINING_MODE=DAILY
export CHECK_INTERVAL_REALTIME=300

echo "✅ Environment variables set for PRODUCTION (AWS S3)."
echo "   Bucket: $S3_BUCKET"
echo "   Note: Ensure you have run 'aws configure' with valid credentials."
