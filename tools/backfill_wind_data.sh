#!/bin/bash
# backfill_wind_data.sh
# 一次性补下载历史风速/风向数据到 S3
# 数据来源: data.gov.sg v2 API (wind-speed, wind-direction)

S3_BUCKET="weather-ai-models-de08370c"
GOVDATA_PREFIX="govdata"

START_DATE="${1:-2025-10-01}"
END_DATE="${2:-$(date +%Y-%m-%d)}"

echo "============================================"
echo "🌬️ 补下载历史风速/风向数据"
echo "   日期范围: $START_DATE → $END_DATE"
echo "   时间: $(date)"
echo "============================================"

downloaded=0
skipped=0
failed=0

current="$START_DATE"
while [[ "$current" < "$END_DATE" ]] || [[ "$current" == "$END_DATE" ]]; do

    for api in "wind-speed" "wind-direction"; do
        s3_key="$GOVDATA_PREFIX/${api}_${current}.json"

        # 已存在则跳过
        if aws s3 ls "s3://$S3_BUCKET/$s3_key" > /dev/null 2>&1; then
            ((skipped++))
            continue
        fi

        # v2 API 下载
        url="https://api-open.data.gov.sg/v2/real-time/api/${api}?date=${current}"
        response=$(curl -s "$url")

        # 检查响应是否有效（code == 0 表示成功）
        code=$(echo "$response" | python3 -c "import json,sys; print(json.load(sys.stdin).get('code',''))" 2>/dev/null)

        if [ "$code" = "0" ]; then
            echo "$response" | aws s3 cp - "s3://$S3_BUCKET/$s3_key" --quiet 2>/dev/null
            if [ $? -eq 0 ]; then
                ((downloaded++))
                echo "  ✅ $current $api"
            else
                ((failed++))
                echo "  ❌ $current $api (S3 upload failed)"
            fi
        else
            ((failed++))
            echo "  ⚠️ $current $api (API returned code: $code)"
        fi

        # 避免 API 限流
        sleep 0.3
    done

    # 下一天
    current=$(date -d "$current + 1 day" "+%Y-%m-%d" 2>/dev/null || date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d")
done

echo ""
echo "============================================"
echo "📊 统计"
echo "   下载: $downloaded"
echo "   跳过: $skipped (已存在)"
echo "   失败: $failed"
echo "   时间: $(date)"
echo "============================================"
