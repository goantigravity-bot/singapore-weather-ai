#!/bin/bash
# push_training_log.sh
# 将训练日志推送到 S3，供监控仪表盘读取

S3_BUCKET="${S3_BUCKET:-weather-ai-models-de08370c}"
LOG_FILE="$HOME/training_scheduler.log"
S3_KEY="logs/training.log"

# 确保日志文件存在
if [ ! -f "$LOG_FILE" ]; then
    echo "Log file not found: $LOG_FILE"
    exit 0
fi

# 获取最新 1000 行日志并上传
tail -n 1000 "$LOG_FILE" > /tmp/training_latest.log
aws s3 cp /tmp/training_latest.log "s3://$S3_BUCKET/$S3_KEY" --quiet

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Log pushed to s3://$S3_BUCKET/$S3_KEY"
