#!/bin/bash
# bulk_download_to_s3.sh
# 批量下载作业 - 从 JAXA FTP 流式上传到 S3
# 设计运行在低配机器上（如 t3.micro 或本地电脑）

# 不使用 set -e，使用手动错误检查

# S3 配置
S3_BUCKET="weather-ai-models-de08370c"
SATELLITE_PREFIX="satellite"
GOVDATA_PREFIX="govdata"

# JAXA 凭证
JAXA_USER="${JAXA_USER:-}"
JAXA_PASS="${JAXA_PASS:-}"

# 日期范围参数
START_DATE="${1:-2025-10-01}"
END_DATE="${2:-2026-01-27}"

# 状态文件（跟踪下载进度）
STATE_FILE="/tmp/download_state.json"

if [ -z "$JAXA_USER" ] || [ -z "$JAXA_PASS" ]; then
    echo "❌ 请设置 JAXA_USER 和 JAXA_PASS 环境变量"
    echo "   或加载 .env.production: source .env.production"
    exit 1
fi

echo "============================================"
echo "📥 批量下载到 S3"
echo "   日期范围: $START_DATE 至 $END_DATE"
echo "   S3 存储桶: s3://$S3_BUCKET/"
echo "   时间: $(date)"
echo "============================================"

# 计算总天数
start_ts=$(date -j -f "%Y-%m-%d" "$START_DATE" "+%s" 2>/dev/null || date -d "$START_DATE" "+%s")
end_ts=$(date -j -f "%Y-%m-%d" "$END_DATE" "+%s" 2>/dev/null || date -d "$END_DATE" "+%s")
total_days=$(( (end_ts - start_ts) / 86400 + 1 ))
echo "   总天数: $total_days"

# 统计
downloaded_files=0
skipped_files=0
failed_files=0

# 日期循环
current="$START_DATE"
day_count=0

while [[ "$current" < "$END_DATE" ]] || [[ "$current" == "$END_DATE" ]]; do
    ((day_count++))
    
    # 格式化日期 (Linux 兼容)
    year_month=$(date -d "$current" "+%Y%m" 2>/dev/null || date -j -f "%Y-%m-%d" "$current" "+%Y%m")
    day=$(date -d "$current" "+%d" 2>/dev/null || date -j -f "%Y-%m-%d" "$current" "+%d")
    date_fmt=$(echo "$current" | tr -d '-')
    
    echo ""
    echo "📅 [$day_count/$total_days] 处理: $current"
    
    remote_path="/jma/netcdf/$year_month/$day"
    
    # 获取文件列表
    files=$(curl -s --ftp-ssl -l --user "$JAXA_USER:$JAXA_PASS" "ftp://ftp.ptree.jaxa.jp$remote_path/" 2>/dev/null || echo "")
    
    if [ -z "$files" ]; then
        echo "   ⚠️ 无法获取文件列表，跳过"
        current=$(date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d" 2>/dev/null || date -d "$current + 1 day" "+%Y-%m-%d")
        continue
    fi
    
    # 过滤 Full Disk 文件
    target_files=$(echo "$files" | grep -E "^NC_H09_.*_R21_FLDK\.0[67]001_06001\.nc$" || echo "")
    file_count=$(echo "$target_files" | grep -c "." || echo "0")
    
    echo "   📁 找到 $file_count 个文件"
    
    processed=0
    for file in $target_files; do
        s3_key="$SATELLITE_PREFIX/$date_fmt/$file"
        
        # 检查 S3 是否已存在
        if aws s3 ls "s3://$S3_BUCKET/$s3_key" > /dev/null 2>&1; then
            ((skipped_files++))
            continue
        fi
        
        # 流式下载并上传到 S3
        echo -n "   ⬆️ $file..."
        
        if curl -s --ftp-ssl --user "$JAXA_USER:$JAXA_PASS" \
            "ftp://ftp.ptree.jaxa.jp$remote_path/$file" | \
            aws s3 cp - "s3://$S3_BUCKET/$s3_key" --quiet 2>/dev/null; then
            echo " ✅"
            ((downloaded_files++))
        else
            echo " ❌"
            ((failed_files++))
        fi
        
        ((processed++))
        
        # 每 20 个文件显示进度
        if [ $((processed % 20)) -eq 0 ]; then
            echo "   📊 进度: $processed/$file_count"
        fi
    done
    
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
    
    echo "   ✅ 日期完成"
    
    # 下一天 (Linux 兼容)
    current=$(date -d "$current + 1 day" "+%Y-%m-%d" 2>/dev/null || date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d")
done

echo ""
echo "============================================"
echo "📊 下载统计"
echo "   已下载: $downloaded_files"
echo "   已跳过: $skipped_files"
echo "   失败: $failed_files"
echo "   完成时间: $(date)"
echo "============================================"
