#!/bin/bash
# push_log_to_s3.sh
# 将下载日志推送到 S3，供监控仪表盘读取

S3_BUCKET="${S3_BUCKET:-weather-ai-models-de08370c}"
LOG_FILE="$HOME/download_parallel.log"
S3_KEY="logs/download.log"

# 确保日志文件存在
touch "$LOG_FILE"

# 获取最新 1000 行日志并上传
tail -n 1000 "$LOG_FILE" > /tmp/download_latest.log
aws s3 cp /tmp/download_latest.log "s3://$S3_BUCKET/$S3_KEY" --quiet

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Log pushed to s3://$S3_BUCKET/$S3_KEY"
