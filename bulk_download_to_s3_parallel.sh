#!/bin/bash
# bulk_download_to_s3_parallel.sh
# 并行批量下载 - 从 JAXA FTP 流式上传到 S3
# 支持多线程下载，显著提升下载速度

# S3 配置
S3_BUCKET="weather-ai-models-de08370c"
SATELLITE_PREFIX="satellite"
GOVDATA_PREFIX="govdata"

# 并行配置
PARALLEL_JOBS="${PARALLEL_JOBS:-4}"  # 默认 4 个并行下载

# JAXA 凭证
JAXA_USER="${JAXA_USER:-}"
JAXA_PASS="${JAXA_PASS:-}"

# 日期范围参数
START_DATE="${1:-2025-10-01}"
END_DATE="${2:-2026-01-27}"

# 日志文件
LOG_FILE="download_parallel.log"
PROGRESS_FILE="/tmp/download_progress.txt"

if [ -z "$JAXA_USER" ] || [ -z "$JAXA_PASS" ]; then
    echo "❌ 请设置 JAXA_USER 和 JAXA_PASS 环境变量"
    exit 1
fi

echo "============================================"
echo "📥 并行批量下载到 S3"
echo "   日期范围: $START_DATE 至 $END_DATE"
echo "   S3 存储桶: s3://$S3_BUCKET/"
echo "   并行数: $PARALLEL_JOBS"
echo "   时间: $(date)"
echo "============================================"

# 计算总天数
start_ts=$(date -d "$START_DATE" "+%s" 2>/dev/null || date -j -f "%Y-%m-%d" "$START_DATE" "+%s")
end_ts=$(date -d "$END_DATE" "+%s" 2>/dev/null || date -j -f "%Y-%m-%d" "$END_DATE" "+%s")
total_days=$(( (end_ts - start_ts) / 86400 + 1 ))
echo "   总天数: $total_days"

# 单文件下载函数
download_single_file() {
    local file="$1"
    local remote_path="$2"
    local date_fmt="$3"
    local s3_key="$SATELLITE_PREFIX/$date_fmt/$file"
    
    # 检查 S3 是否已存在
    if aws s3 ls "s3://$S3_BUCKET/$s3_key" > /dev/null 2>&1; then
        echo "   ⏭️ $file (已存在)"
        return 0
    fi
    
    # 流式下载并上传到 S3
    if curl -s --ftp-ssl --user "$JAXA_USER:$JAXA_PASS" \
        "ftp://ftp.ptree.jaxa.jp$remote_path/$file" | \
        aws s3 cp - "s3://$S3_BUCKET/$s3_key" --quiet 2>/dev/null; then
        echo "   ✅ $file"
        return 0
    else
        echo "   ❌ $file"
        return 1
    fi
}

export -f download_single_file
export S3_BUCKET SATELLITE_PREFIX JAXA_USER JAXA_PASS

# 统计
downloaded_files=0
skipped_files=0

# 日期循环
current="$START_DATE"
day_count=0

while [[ "$current" < "$END_DATE" ]] || [[ "$current" == "$END_DATE" ]]; do
    ((day_count++))
    
    # 格式化日期
    year_month=$(date -d "$current" "+%Y%m" 2>/dev/null || date -j -f "%Y-%m-%d" "$current" "+%Y%m")
    day=$(date -d "$current" "+%d" 2>/dev/null || date -j -f "%Y-%m-%d" "$current" "+%d")
    date_fmt=$(echo "$current" | tr -d '-')
    
    echo ""
    echo "📅 [$day_count/$total_days] 处理: $current"
    
    # 检查是否已完成
    if aws s3 ls "s3://$S3_BUCKET/$SATELLITE_PREFIX/$date_fmt/.complete" > /dev/null 2>&1; then
        echo "   ⏭️ 日期已完成，跳过"
        current=$(date -d "$current + 1 day" "+%Y-%m-%d" 2>/dev/null || date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d")
        continue
    fi
    
    remote_path="/jma/netcdf/$year_month/$day"
    
    # 获取文件列表
    files=$(curl -s --ftp-ssl -l --user "$JAXA_USER:$JAXA_PASS" "ftp://ftp.ptree.jaxa.jp$remote_path/" 2>/dev/null || echo "")
    
    if [ -z "$files" ]; then
        echo "   ⚠️ 无法获取文件列表，跳过"
        current=$(date -d "$current + 1 day" "+%Y-%m-%d" 2>/dev/null || date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d")
        continue
    fi
    
    # 过滤 Full Disk 文件
    target_files=$(echo "$files" | grep -E "^NC_H09_.*_R21_FLDK\.0[67]001_06001\.nc$" || echo "")
    file_count=$(echo "$target_files" | grep -c "." || echo "0")
    
    echo "   📁 找到 $file_count 个文件，使用 $PARALLEL_JOBS 并行下载"
    
    # 并行下载
    echo "$target_files" | xargs -P "$PARALLEL_JOBS" -I {} bash -c \
        "download_single_file '{}' '$remote_path' '$date_fmt'"
    
    # 下载政府数据
    echo "   📊 下载政府数据..."
    for api in "rainfall" "temperature" "humidity" "pm25"; do
        s3_key="$GOVDATA_PREFIX/${api}_${current}.json"
        
        if aws s3 ls "s3://$S3_BUCKET/$s3_key" > /dev/null 2>&1; then
            continue
        fi
        
        case $api in
            rainfall) url="https://api.data.gov.sg/v1/environment/rainfall" ;;
            temperature) url="https://api.data.gov.sg/v1/environment/air-temperature" ;;
            humidity) url="https://api.data.gov.sg/v1/environment/relative-humidity" ;;
            pm25) url="https://api.data.gov.sg/v1/environment/pm25" ;;
        esac
        
        curl -s "$url?date=$current" | aws s3 cp - "s3://$S3_BUCKET/$s3_key" --quiet 2>/dev/null || true
    done
    
    # 创建完成标记
    echo "$current" | aws s3 cp - "s3://$S3_BUCKET/$SATELLITE_PREFIX/$date_fmt/.complete" --quiet
    
    echo "   ✅ 日期完成: $current"
    
    # 下一天
    current=$(date -d "$current + 1 day" "+%Y-%m-%d" 2>/dev/null || date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d")
done

echo ""
echo "============================================"
echo "📊 下载完成"
echo "   完成时间: $(date)"
echo "============================================"
