#!/bin/bash
# bulk_download_to_s3_parallel.sh
# 并行批量下载 - 从 JAXA FTP 流式上传到 S3
# 支持多线程下载，显著提升下载速度

# S3 配置
S3_BUCKET="weather-ai-models-de08370c"
SATELLITE_PREFIX="satellite"
ARCHIVED_PREFIX="archived/satellite"  # 已处理的数据归档位置
GOVDATA_PREFIX="govdata"
MIN_FILES_PER_DAY=50  # 每天最少文件数，低于此值不标记为完成

# 并行配置
PARALLEL_JOBS="${PARALLEL_JOBS:-8}"  # 默认 8 个并行下载

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
    
    # 检查是否已完成（同时检查 satellite/ 和 archived/satellite/）
    if aws s3 ls "s3://$S3_BUCKET/$SATELLITE_PREFIX/$date_fmt/.complete" > /dev/null 2>&1; then
        echo "   ⏭️ 日期已完成（satellite/），跳过"
        current=$(date -d "$current + 1 day" "+%Y-%m-%d" 2>/dev/null || date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d")
        continue
    fi
    
    # 检查是否在归档文件夹中
    if aws s3 ls "s3://$S3_BUCKET/$ARCHIVED_PREFIX/$date_fmt/" > /dev/null 2>&1; then
        archived_count=$(aws s3 ls "s3://$S3_BUCKET/$ARCHIVED_PREFIX/$date_fmt/" 2>/dev/null | grep -c ".nc" || echo "0")
        if [ "$archived_count" -ge "$MIN_FILES_PER_DAY" ]; then
            echo "   ⏭️ 日期已归档（archived/，$archived_count 文件），跳过"
            current=$(date -d "$current + 1 day" "+%Y-%m-%d" 2>/dev/null || date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d")
            continue
        fi
    fi
    
    remote_path="/jma/netcdf/$year_month/$day"
    
    # 获取文件列表
    files=$(curl -s --ftp-ssl -l --user "$JAXA_USER:$JAXA_PASS" "ftp://ftp.ptree.jaxa.jp$remote_path/" 2>/dev/null || echo "")
    
    if [ -z "$files" ]; then
        echo "   ⚠️ 无法获取文件列表，跳过"
        current=$(date -d "$current + 1 day" "+%Y-%m-%d" 2>/dev/null || date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d")
        continue
    fi
    
    # 智能文件选择：优先 07001_06001，fallback 到 06001_06001
    # 文件名格式: NC_H0[89]_YYYYMMDD_HHMM_R21_FLDK.0X001_06001.nc
    primary_files=$(echo "$files" | grep -E "^NC_H0[89]_.*_R21_FLDK\.07001_06001\.nc$" || echo "")
    fallback_files=$(echo "$files" | grep -E "^NC_H0[89]_.*_R21_FLDK\.06001_06001\.nc$" || echo "")
    
    # 提取时间戳并选择文件
    target_files=""
    # 从 primary 文件中获取所有时间戳
    primary_timestamps=$(echo "$primary_files" | sed -n 's/NC_H0[89]_\([0-9]*_[0-9]*\)_.*/\1/p' | sort -u)
    fallback_timestamps=$(echo "$fallback_files" | sed -n 's/NC_H0[89]_\([0-9]*_[0-9]*\)_.*/\1/p' | sort -u)
    
    # 对每个 primary 时间戳，只保留 07001 文件
    for ts in $primary_timestamps; do
        file=$(echo "$primary_files" | grep "NC_H0[89]_${ts}_" | head -1)
        if [ -n "$file" ]; then
            target_files="$target_files$file"$'\n'
        fi
    done
    
    # 对于 primary 中没有的时间戳，使用 fallback
    for ts in $fallback_timestamps; do
        if ! echo "$primary_timestamps" | grep -q "^${ts}$"; then
            file=$(echo "$fallback_files" | grep "NC_H0[89]_${ts}_" | head -1)
            if [ -n "$file" ]; then
                target_files="$target_files$file"$'\n'
                echo "   ℹ️ 使用备选: $file"
            fi
        fi
    done
    
    # 去除空行
    target_files=$(echo "$target_files" | grep -v "^$" || echo "")
    file_count=$(echo "$target_files" | grep -c "." || echo "0")
    
    echo "   📁 找到 $file_count 个卫星文件 (优先 07001，fallback 06001)"
    echo "   🚀 卫星数据和政府数据并行下载..."
    
    # 定义政府数据下载函数
    download_govdata() {
        local current_date="$1"
        for api in "rainfall" "temperature" "humidity" "pm25"; do
            s3_key="$GOVDATA_PREFIX/${api}_${current_date}.json"
            
            if aws s3 ls "s3://$S3_BUCKET/$s3_key" > /dev/null 2>&1; then
                continue
            fi
            
            case $api in
                rainfall) url="https://api.data.gov.sg/v1/environment/rainfall" ;;
                temperature) url="https://api.data.gov.sg/v1/environment/air-temperature" ;;
                humidity) url="https://api.data.gov.sg/v1/environment/relative-humidity" ;;
                pm25) url="https://api.data.gov.sg/v1/environment/pm25" ;;
            esac
            
            curl -s "$url?date=$current_date" | aws s3 cp - "s3://$S3_BUCKET/$s3_key" --quiet 2>/dev/null || true
        done
        echo "   ✅ 政府数据完成: $current_date"
    }
    export -f download_govdata
    export S3_BUCKET GOVDATA_PREFIX
    
    # 并行执行：卫星数据 + 政府数据
    (
        # 任务1：并行下载卫星文件
        echo "$target_files" | xargs -P "$PARALLEL_JOBS" -I {} bash -c \
            "download_single_file '{}' '$remote_path' '$date_fmt'"
        echo "   ✅ 卫星数据完成: $current"
    ) &
    satellite_pid=$!
    
    (
        # 任务2：下载政府数据
        download_govdata "$current"
    ) &
    govdata_pid=$!
    
    # 等待两个任务都完成
    wait $satellite_pid
    wait $govdata_pid
    
    # 验证下载的文件数量
    actual_count=$(aws s3 ls "s3://$S3_BUCKET/$SATELLITE_PREFIX/$date_fmt/" 2>/dev/null | grep -c ".nc" || echo "0")
    
    if [ "$actual_count" -ge "$MIN_FILES_PER_DAY" ]; then
        # 创建完成标记（只有达到最低文件数才标记）
        echo "$current" | aws s3 cp - "s3://$S3_BUCKET/$SATELLITE_PREFIX/$date_fmt/.complete" --quiet
        echo "   ✅ 日期完成: $current ($actual_count 文件)"
    else
        echo "   ⚠️ 日期未完成: $current (只有 $actual_count 文件，需要 >= $MIN_FILES_PER_DAY)"
    fi
    
    # 下一天
    current=$(date -d "$current + 1 day" "+%Y-%m-%d" 2>/dev/null || date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d")
done

echo ""
echo "============================================"
echo "📊 下载完成"
echo "   完成时间: $(date)"
echo "============================================"
