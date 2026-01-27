#!/bin/bash
# archive_housekeeping.sh
# 清理已归档的数据，释放 S3 存储空间

set -e

S3_BUCKET="weather-ai-models-de08370c"
ARCHIVE_PREFIX="archived"

# 保留天数 (默认 30 天)
RETENTION_DAYS="${1:-30}"

echo "============================================"
echo "🧹 S3 归档清理"
echo "   保留天数: $RETENTION_DAYS"
echo "============================================"

# 计算截止日期
cutoff_date=$(date -d "-$RETENTION_DAYS days" "+%Y%m%d" 2>/dev/null || date -v-${RETENTION_DAYS}d "+%Y%m%d")
echo "   删除 $cutoff_date 之前的数据"

echo ""
echo "📊 清理前统计:"
aws s3 ls "s3://$S3_BUCKET/$ARCHIVE_PREFIX/" --recursive --summarize --human-readable | tail -2

# 列出并删除旧文件
echo ""
echo "🔍 扫描旧文件..."

deleted_count=0

for file in $(aws s3 ls "s3://$S3_BUCKET/$ARCHIVE_PREFIX/" --recursive | awk '{print $4}'); do
    # 从文件名提取日期 (假设格式 NC_H09_YYYYMMDD_...)
    file_date=$(echo "$file" | grep -oE '[0-9]{8}' | head -1)
    
    if [ -n "$file_date" ] && [ "$file_date" -lt "$cutoff_date" ]; then
        echo "  🗑️ 删除: $file"
        aws s3 rm "s3://$S3_BUCKET/$file" --quiet
        ((deleted_count++))
    fi
done

echo ""
echo "============================================"
echo "✅ 清理完成"
echo "   删除文件数: $deleted_count"
echo "============================================"

echo ""
echo "📊 清理后统计:"
aws s3 ls "s3://$S3_BUCKET/$ARCHIVE_PREFIX/" --recursive --summarize --human-readable | tail -2
