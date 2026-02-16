#!/bin/bash
# process_batch_from_s3.sh
# 从 S3 下载数据批次，处理，然后归档

set -e

# S3 配置
S3_BUCKET="weather-ai-models-de08370c"
SATELLITE_PREFIX="satellite"
GOVDATA_PREFIX="govdata"
ARCHIVE_PREFIX="archived"

# 本地目录
WORK_DIR="/home/ubuntu/weather-ai"
SATELLITE_DIR="$WORK_DIR/satellite_data"
PROCESSED_DIR="$WORK_DIR/processed_data"

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
echo "🔄 批次处理: $START_DATE 至 $END_DATE"
echo "============================================"

cd "$WORK_DIR"
source venv/bin/activate

mkdir -p "$SATELLITE_DIR"
mkdir -p "$PROCESSED_DIR"

# 日期循环
current="$START_DATE"
while [[ "$current" < "$END_DATE" ]] || [[ "$current" == "$END_DATE" ]]; do
    # 格式化日期为 YYYYMMDD
    date_fmt=$(echo "$current" | tr -d '-')
    
    echo ""
    echo "📅 处理日期: $current ($date_fmt)"
    
    # 1. 从 S3 下载当天的卫星数据
    echo "  ⬇️ 下载卫星数据..."
    aws s3 cp "s3://$S3_BUCKET/$SATELLITE_PREFIX/" "$SATELLITE_DIR/" \
        --recursive --exclude "*" --include "NC_H09_${date_fmt}*" \
        --quiet 2>/dev/null || echo "  ⚠️ 没有卫星数据"
    
    file_count=$(ls "$SATELLITE_DIR"/NC_H09_${date_fmt}*.nc 2>/dev/null | wc -l || echo "0")
    echo "  📁 下载了 $file_count 个卫星文件"
    
    if [ "$file_count" -gt 0 ]; then
        # 2. 预处理卫星数据
        echo "  🔧 预处理卫星数据..."
        python preprocess_images.py 2>&1 | tail -5
        
        # 3. 删除本地原始文件
        echo "  🗑️ 清理本地原始文件..."
        rm -f "$SATELLITE_DIR"/NC_H09_${date_fmt}*.nc
        
        # 4. 移动 S3 文件到归档
        echo "  📦 归档 S3 数据..."
        for file in $(aws s3 ls "s3://$S3_BUCKET/$SATELLITE_PREFIX/NC_H09_${date_fmt}" --recursive 2>/dev/null | awk '{print $4}' || echo ""); do
            if [ -n "$file" ]; then
                filename=$(basename "$file")
                aws s3 mv "s3://$S3_BUCKET/$file" "s3://$S3_BUCKET/$ARCHIVE_PREFIX/satellite/$filename" --quiet
            fi
        done
    fi
    
    # 5. 下载政府数据 (如果在 S3 中)
    echo "  ⬇️ 下载政府数据..."
    aws s3 cp "s3://$S3_BUCKET/$GOVDATA_PREFIX/" "$WORK_DIR/govdata/" \
        --recursive --exclude "*" --include "*_${current}.json" \
        --quiet 2>/dev/null || echo "  ⚠️ 没有政府数据"
    
    # 下一天
    current=$(date -d "$current + 1 day" "+%Y-%m-%d" 2>/dev/null || date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d")
done

echo ""
echo "============================================"
echo "📊 预处理数据统计"
echo "============================================"
ls -lh "$PROCESSED_DIR"/*.npy 2>/dev/null | wc -l
du -sh "$PROCESSED_DIR"

echo ""
echo "✅ 批次处理完成"
