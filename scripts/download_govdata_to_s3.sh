#!/bin/bash
# download_govdata_to_s3.sh
# 下载 NEA 政府数据（雨量、温度、湿度、PM2.5）到 S3 存储桶

set -e

# S3 配置
S3_BUCKET="weather-ai-models-de08370c"
S3_PREFIX="govdata"

# 日期参数
START_DATE="${1:-}"
END_DATE="${2:-}"

if [ -z "$START_DATE" ]; then
    echo "用法: $0 START_DATE [END_DATE]"
    echo "  例如: $0 2025-10-01 2025-10-03"
    exit 1
fi

if [ -z "$END_DATE" ]; then
    END_DATE="$START_DATE"
fi

echo "============================================"
echo "📊 NEA 政府数据下载到 S3"
echo "   日期范围: $START_DATE 至 $END_DATE"
echo "   S3 目标: s3://$S3_BUCKET/$S3_PREFIX/"
echo "============================================"

# 临时目录
TEMP_DIR="/tmp/govdata_download"
mkdir -p "$TEMP_DIR"

# API 端点
APIs=(
    "rainfall:https://api.data.gov.sg/v1/environment/rainfall"
    "temperature:https://api.data.gov.sg/v1/environment/air-temperature"
    "humidity:https://api.data.gov.sg/v1/environment/relative-humidity"
    "pm25:https://api.data.gov.sg/v1/environment/pm25"
)

# 日期循环
current="$START_DATE"
while [[ "$current" < "$END_DATE" ]] || [[ "$current" == "$END_DATE" ]]; do
    echo ""
    echo "📅 处理日期: $current"
    
    for api_info in "${APIs[@]}"; do
        api_name="${api_info%%:*}"
        api_url="${api_info#*:}"
        
        output_file="$TEMP_DIR/${api_name}_${current}.json"
        s3_key="$S3_PREFIX/${api_name}_${current}.json"
        
        # 检查 S3 是否已存在
        if aws s3 ls "s3://$S3_BUCKET/$s3_key" > /dev/null 2>&1; then
            echo "   ⏭️ 已存在: ${api_name}_${current}.json"
            continue
        fi
        
        echo "   ⬇️ 下载: $api_name"
        
        # 下载数据 (NEA API 支持 date 参数)
        curl -s "$api_url?date=$current" -o "$output_file" || {
            echo "   ❌ 下载失败: $api_name"
            continue
        }
        
        if [ -f "$output_file" ] && [ -s "$output_file" ]; then
            # 上传到 S3
            aws s3 cp "$output_file" "s3://$S3_BUCKET/$s3_key" --quiet
            rm -f "$output_file"
            echo "   ✅ 完成: $api_name"
        fi
    done
    
    # 下一天
    current=$(date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d" 2>/dev/null || date -d "$current + 1 day" "+%Y-%m-%d")
done

echo ""
echo "============================================"
echo "✅ 下载完成"
echo "============================================"

# 显示 S3 中的文件统计
echo ""
echo "📊 S3 存储统计:"
aws s3 ls "s3://$S3_BUCKET/$S3_PREFIX/" --summarize --human-readable | tail -2
