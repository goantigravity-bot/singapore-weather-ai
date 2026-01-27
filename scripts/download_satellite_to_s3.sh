#!/bin/bash
# download_satellite_to_s3.sh
# 下载 JAXA 卫星数据到 S3 存储桶
# 设计：先下载到本地临时目录，然后上传到 S3，最后删除本地文件

set -e

# S3 配置
S3_BUCKET="weather-ai-models-de08370c"
S3_PREFIX="satellite"

# JAXA 凭证 (从环境变量读取)
JAXA_USER="${JAXA_USER:-}"
JAXA_PASS="${JAXA_PASS:-}"

# 本地临时目录
TEMP_DIR="/tmp/satellite_download"

# 日期参数
START_DATE="${1:-}"
END_DATE="${2:-}"

if [ -z "$JAXA_USER" ] || [ -z "$JAXA_PASS" ]; then
    echo "❌ 请设置 JAXA_USER 和 JAXA_PASS 环境变量"
    exit 1
fi

if [ -z "$START_DATE" ]; then
    echo "用法: $0 START_DATE [END_DATE]"
    echo "  例如: $0 2025-10-01 2025-10-03"
    exit 1
fi

if [ -z "$END_DATE" ]; then
    END_DATE="$START_DATE"
fi

echo "============================================"
echo "🛰️  JAXA 卫星数据下载到 S3"
echo "   日期范围: $START_DATE 至 $END_DATE"
echo "   S3 目标: s3://$S3_BUCKET/$S3_PREFIX/"
echo "============================================"

# 创建临时目录
mkdir -p "$TEMP_DIR"

# 日期循环
current="$START_DATE"
while [[ "$current" < "$END_DATE" ]] || [[ "$current" == "$END_DATE" ]]; do
    year_month=$(date -j -f "%Y-%m-%d" "$current" "+%Y%m" 2>/dev/null || date -d "$current" "+%Y%m")
    day=$(date -j -f "%Y-%m-%d" "$current" "+%d" 2>/dev/null || date -d "$current" "+%d")
    
    echo ""
    echo "📅 处理日期: $current ($year_month/$day)"
    
    remote_path="/jma/netcdf/$year_month/$day"
    
    # 列出文件
    files=$(curl -s --ftp-ssl -l --user "$JAXA_USER:$JAXA_PASS" "ftp://ftp.ptree.jaxa.jp$remote_path/" 2>/dev/null || echo "")
    
    if [ -z "$files" ]; then
        echo "   ⚠️ 无法获取文件列表，跳过"
        current=$(date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d" 2>/dev/null || date -d "$current + 1 day" "+%Y-%m-%d")
        continue
    fi
    
    # 过滤 Full Disk 文件
    target_files=$(echo "$files" | grep -E "^NC_H09_.*_R21_FLDK\.0[67]001_06001\.nc$" || echo "")
    file_count=$(echo "$target_files" | grep -c "." || echo "0")
    
    echo "   找到 $file_count 个目标文件"
    
    # 下载并上传每个文件
    for file in $target_files; do
        # 检查 S3 是否已存在
        if aws s3 ls "s3://$S3_BUCKET/$S3_PREFIX/$file" > /dev/null 2>&1; then
            echo "   ⏭️ 已存在: $file"
            continue
        fi
        
        local_file="$TEMP_DIR/$file"
        
        # 下载
        echo "   ⬇️ 下载: $file"
        curl -s --ftp-ssl --user "$JAXA_USER:$JAXA_PASS" \
            "ftp://ftp.ptree.jaxa.jp$remote_path/$file" \
            -o "$local_file"
        
        if [ -f "$local_file" ]; then
            # 上传到 S3
            echo "   ⬆️ 上传到 S3..."
            aws s3 cp "$local_file" "s3://$S3_BUCKET/$S3_PREFIX/$file" --quiet
            
            # 删除本地文件
            rm -f "$local_file"
            echo "   ✅ 完成: $file"
        else
            echo "   ❌ 下载失败: $file"
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
