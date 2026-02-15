#!/bin/bash
# backfill-govdata.sh
# 分两阶段拉取 data.gov.sg 数据:
#   阶段1 (rainfall-only): 只拉 rainfall → 供 scan_rainy_timestamps.py 识别雨天
#   阶段2 (sensors):        只对雨天拉 temp/humidity/pm25/wind
#
# 用法:
#   ./backfill-govdata.sh 2024-02-15 2025-09-30              # 默认: 只拉 rainfall
#   ./backfill-govdata.sh 2024-02-15 2025-09-30 --all-sensors # 拉全部 6 种传感器

S3_BUCKET="weather-ai-models-de08370c"
GOVDATA_PREFIX="govdata"

START_DATE="${1:-2024-02-15}"
END_DATE="${2:-2025-09-30}"
MODE="${3:---rainfall-only}"

echo "============================================"
echo "📥 Backfill Gov Data to S3"
echo "   Range: $START_DATE → $END_DATE"
echo "   Mode:  $MODE"
echo "   Bucket: s3://$S3_BUCKET/$GOVDATA_PREFIX/"
echo "   Time: $(date)"
echo "============================================"

# 根据模式选择 API 列表
if [ "$MODE" = "--all-sensors" ]; then
    APIS="rainfall temperature humidity pm25 wind-speed wind-direction"
else
    APIS="rainfall"
fi

total=0
skipped=0
downloaded=0
failed=0

current="$START_DATE"
while [[ "$current" < "$END_DATE" ]] || [[ "$current" == "$END_DATE" ]]; do
    ((total++))

    for api in $APIS; do
        s3_key="$GOVDATA_PREFIX/${api}_${current}.json"

        # 已存在则跳过
        if aws s3 ls "s3://$S3_BUCKET/$s3_key" > /dev/null 2>&1; then
            ((skipped++))
            continue
        fi

        # 构建 API URL
        case $api in
            rainfall)    url="https://api.data.gov.sg/v1/environment/rainfall?date=$current" ;;
            temperature) url="https://api.data.gov.sg/v1/environment/air-temperature?date=$current" ;;
            humidity)    url="https://api.data.gov.sg/v1/environment/relative-humidity?date=$current" ;;
            pm25)        url="https://api.data.gov.sg/v1/environment/pm25?date=$current" ;;
            wind-speed|wind-direction)
                url="https://api-open.data.gov.sg/v2/real-time/api/${api}?date=${current}" ;;
        esac

        if curl -s "$url" | aws s3 cp - "s3://$S3_BUCKET/$s3_key" --quiet 2>/dev/null; then
            ((downloaded++))
        else
            ((failed++))
            echo "  ❌ $api $current"
        fi
    done

    # 每 10 天输出进度
    if [ $((total % 10)) -eq 0 ]; then
        echo "  📊 [$total days] $current: downloaded=$downloaded skipped=$skipped failed=$failed"
    fi

    # 下一天
    current=$(date -d "$current + 1 day" "+%Y-%m-%d" 2>/dev/null || date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d")
done

echo ""
echo "============================================"
echo "✅ Backfill Complete ($MODE)"
echo "   Days: $total"
echo "   Downloaded: $downloaded"
echo "   Skipped: $skipped"
echo "   Failed: $failed"
echo "   Time: $(date)"
echo "============================================"
