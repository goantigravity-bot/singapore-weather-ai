#!/bin/bash
# backfill-sensor-parallel.sh
# 多线程只为雨天拉取其他传感器数据 (temp/humidity/pm25/wind)
# 依赖 rainy_timestamps.json 中识别的雨天日期
#
# 用法: ./backfill-sensor-parallel.sh [并行数] [rainy_timestamps.json路径]

S3_BUCKET="weather-ai-models-de08370c"
GOVDATA_PREFIX="govdata"
PARALLEL="${1:-8}"
TIMESTAMPS_FILE="${2:-$(dirname "$0")/data/rainy_timestamps.json}"

# 从 rainy_timestamps.json 提取雨天日期列表
if [ ! -f "$TIMESTAMPS_FILE" ]; then
    echo "❌ Missing $TIMESTAMPS_FILE — run scan_rainy_timestamps.py first"
    exit 1
fi

# 提取日期列表
RAIN_DATES=$(python3 -c "
import json, sys
with open('$TIMESTAMPS_FILE') as f:
    data = json.load(f)
for day in data['days']:
    print(day['date'])
")

TOTAL_DATES=$(echo "$RAIN_DATES" | wc -l | tr -d ' ')

echo "============================================"
echo "📥 Parallel Sensor Backfill (rain days only)"
echo "   Rain days: $TOTAL_DATES"
echo "   APIs: temperature, humidity, pm25, wind-speed, wind-direction"
echo "   Parallel: $PARALLEL"
echo "   Time: $(date)"
echo "============================================"

# 单日下载函数 — 由 xargs 并行调用
download_day() {
    local current="$1"
    local result=""

    for api in temperature humidity pm25 wind-speed wind-direction; do
        s3_key="$GOVDATA_PREFIX/${api}_${current}.json"

        # 已存在则跳过
        if aws s3 ls "s3://$S3_BUCKET/$s3_key" > /dev/null 2>&1; then
            continue
        fi

        case $api in
            temperature) url="https://api.data.gov.sg/v1/environment/air-temperature?date=$current" ;;
            humidity)    url="https://api.data.gov.sg/v1/environment/relative-humidity?date=$current" ;;
            pm25)        url="https://api.data.gov.sg/v1/environment/pm25?date=$current" ;;
            wind-speed|wind-direction)
                url="https://api-open.data.gov.sg/v2/real-time/api/${api}?date=${current}" ;;
        esac

        if ! curl -s "$url" | aws s3 cp - "s3://$S3_BUCKET/$s3_key" --quiet 2>/dev/null; then
            echo "  ❌ $api $current"
        fi
    done
    echo "  ✅ $current"
}

export -f download_day
export S3_BUCKET GOVDATA_PREFIX

echo "$RAIN_DATES" | xargs -P "$PARALLEL" -I {} bash -c 'download_day "$@"' _ {}

echo ""
echo "============================================"
echo "✅ Sensor Backfill Complete"
echo "   Rain days processed: $TOTAL_DATES"
echo "   Parallel: $PARALLEL"
echo "   Time: $(date)"
echo "============================================"
