#!/bin/bash
# cleanup_s3_duplicates.sh
# 清理 S3 上的重复卫星文件：当 07001 存在时删除对应的 06001

S3_BUCKET="weather-ai-models-de08370c"
SATELLITE_PREFIX="satellite"

# 日期范围参数
START_DATE="${1:-2025-10-01}"
END_DATE="${2:-2025-10-10}"

# 模式：dry-run (默认) 或 delete
MODE="${3:-dry-run}"

echo "============================================"
echo "🧹 S3 重复文件清理"
echo "   日期范围: $START_DATE 至 $END_DATE"
echo "   模式: $MODE"
echo "============================================"

total_deleted=0
total_saved_bytes=0

current="$START_DATE"
while [[ "$current" < "$END_DATE" ]] || [[ "$current" == "$END_DATE" ]]; do
    date_fmt=$(echo "$current" | tr -d '-')
    
    echo ""
    echo "📅 处理: $current"
    
    # 获取该日期的所有文件
    files=$(aws s3 ls "s3://$S3_BUCKET/$SATELLITE_PREFIX/$date_fmt/" 2>/dev/null)
    
    if [ -z "$files" ]; then
        echo "   ⚠️ 无文件，跳过"
        current=$(date -d "$current + 1 day" "+%Y-%m-%d" 2>/dev/null || date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d")
        continue
    fi
    
    # 找出所有 07001 文件的时间戳
    primary_timestamps=$(echo "$files" | grep "07001_06001.nc" | awk '{print $4}' | sed -n 's/NC_H09_\([0-9]*_[0-9]*\)_.*/\1/p' | sort -u)
    
    deleted_count=0
    saved_bytes=0
    
    # 对于每个有 07001 的时间戳，删除对应的 06001
    for ts in $primary_timestamps; do
        # 检查是否存在对应的 06001 文件
        fallback_line=$(echo "$files" | grep "NC_H09_${ts}_R21_FLDK.06001_06001.nc")
        
        if [ -n "$fallback_line" ]; then
            file_size=$(echo "$fallback_line" | awk '{print $3}')
            file_name=$(echo "$fallback_line" | awk '{print $4}')
            
            if [ "$MODE" == "delete" ]; then
                aws s3 rm "s3://$S3_BUCKET/$SATELLITE_PREFIX/$date_fmt/$file_name" --quiet
                echo "   🗑️ 删除: $file_name ($(numfmt --to=iec $file_size 2>/dev/null || echo "${file_size}B"))"
            else
                echo "   📋 [DRY-RUN] 将删除: $file_name ($(numfmt --to=iec $file_size 2>/dev/null || echo "${file_size}B"))"
            fi
            
            ((deleted_count++))
            saved_bytes=$((saved_bytes + file_size))
        fi
    done
    
    if [ $deleted_count -gt 0 ]; then
        echo "   📊 该日期: $deleted_count 个文件, 节省 $(numfmt --to=iec $saved_bytes 2>/dev/null || echo "${saved_bytes}B")"
    else
        echo "   ✅ 无重复文件"
    fi
    
    total_deleted=$((total_deleted + deleted_count))
    total_saved_bytes=$((total_saved_bytes + saved_bytes))
    
    # 下一天
    current=$(date -d "$current + 1 day" "+%Y-%m-%d" 2>/dev/null || date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d")
done

echo ""
echo "============================================"
echo "📊 清理总结"
echo "   总文件数: $total_deleted"
echo "   节省存储: $(numfmt --to=iec $total_saved_bytes 2>/dev/null || echo "${total_saved_bytes}B")"
if [ "$MODE" == "dry-run" ]; then
    echo ""
    echo "⚠️ 这是 DRY-RUN 模式，未实际删除文件"
    echo "   使用 '$0 $START_DATE $END_DATE delete' 执行实际删除"
fi
echo "============================================"
