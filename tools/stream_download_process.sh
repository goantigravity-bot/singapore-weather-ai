#!/bin/bash
# stream_download_process.sh
# 流式下载并处理卫星数据：下载一个文件 → 预处理 → 上传预处理结果到 S3 → 删除原始文件
# 设计用于训练服务器上运行，避免存储空间不足

set -e

WORK_DIR="/home/ubuntu/weather-ai"
cd "$WORK_DIR"

# S3 配置
S3_BUCKET="weather-ai-models-de08370c"
SATELLITE_PREFIX="satellite"
PROCESSED_PREFIX="preprocessed"

# JAXA 凭证
JAXA_USER="${JAXA_USER:-}"
JAXA_PASS="${JAXA_PASS:-}"

# 目录
SATELLITE_DIR="$WORK_DIR/satellite_data"
PROCESSED_DIR="$WORK_DIR/processed_data"

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
echo "🔄 流式下载并处理卫星数据"
echo "   日期范围: $START_DATE 至 $END_DATE"
echo "   时间: $(date)"
echo "============================================"

source venv/bin/activate

mkdir -p "$SATELLITE_DIR"
mkdir -p "$PROCESSED_DIR"

# 统计
total_downloaded=0
total_processed=0
total_failed=0

# 日期循环
current="$START_DATE"
while [[ "$current" < "$END_DATE" ]] || [[ "$current" == "$END_DATE" ]]; do
    # 格式化日期
    year_month=$(date -d "$current" "+%Y%m" 2>/dev/null || date -j -f "%Y-%m-%d" "$current" "+%Y%m")
    day=$(date -d "$current" "+%d" 2>/dev/null || date -j -f "%Y-%m-%d" "$current" "+%d")
    date_fmt=$(echo "$current" | tr -d '-')
    
    echo ""
    echo "📅 处理日期: $current ($year_month/$day)"
    
    remote_path="/jma/netcdf/$year_month/$day"
    
    # 列出文件
    files=$(curl -s --ftp-ssl -l --user "$JAXA_USER:$JAXA_PASS" "ftp://ftp.ptree.jaxa.jp$remote_path/" 2>/dev/null || echo "")
    
    if [ -z "$files" ]; then
        echo "   ⚠️ 无法获取文件列表，跳过"
        current=$(date -d "$current + 1 day" "+%Y-%m-%d" 2>/dev/null || date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d")
        continue
    fi
    
    # 过滤 Full Disk 文件
    target_files=$(echo "$files" | grep -E "^NC_H09_.*_R21_FLDK\.0[67]001_06001\.nc$" || echo "")
    file_count=$(echo "$target_files" | grep -c "." || echo "0")
    
    echo "   📁 找到 $file_count 个目标文件"
    
    # 处理每个文件
    processed_count=0
    for file in $target_files; do
        # 提取时间戳
        timestamp=$(echo "$file" | grep -oE '[0-9]{8}_[0-9]{4}')
        processed_file="$PROCESSED_DIR/${file%.nc}.npy"
        
        # 检查是否已处理
        if [ -f "$processed_file" ]; then
            echo "   ⏭️ 已处理: $file"
            continue
        fi
        
        # 检查 S3 是否有预处理文件
        if aws s3 ls "s3://$S3_BUCKET/$PROCESSED_PREFIX/${file%.nc}.npy" > /dev/null 2>&1; then
            echo "   ⏭️ S3 已有: $file"
            continue
        fi
        
        local_file="$SATELLITE_DIR/$file"
        
        # 1. 下载
        echo "   ⬇️ 下载: $file"
        curl -s --ftp-ssl --user "$JAXA_USER:$JAXA_PASS" \
            "ftp://ftp.ptree.jaxa.jp$remote_path/$file" \
            -o "$local_file"
        
        if [ ! -f "$local_file" ]; then
            echo "   ❌ 下载失败"
            ((total_failed++))
            continue
        fi
        
        ((total_downloaded++))
        
        # 2. 预处理（只处理这一个文件）
        echo "   🔧 预处理..."
        python -c "
import netCDF4 as nc
import numpy as np
import os

file_path = '$local_file'
output_path = '$processed_file'

try:
    ds = nc.Dataset(file_path, 'r')
    # 提取新加坡区域 (约 1.1°N-1.5°N, 103.6°E-104.1°E)
    # 根据实际数据结构调整
    if 'tbb' in ds.variables:
        data = ds.variables['tbb'][:]
    elif 'B13_TEMP' in ds.variables:
        data = ds.variables['B13_TEMP'][:]
    else:
        # 获取第一个数据变量
        for var in ds.variables:
            if ds.variables[var].ndim >= 2:
                data = ds.variables[var][:]
                break
    
    # 裁剪到新加坡区域 (假设数据已经是子集)
    # 保存预处理数据
    np.save(output_path, data.astype(np.float32))
    ds.close()
    print('OK')
except Exception as e:
    print(f'ERROR: {e}')
" 2>&1 | tail -1
        
        if [ -f "$processed_file" ]; then
            ((total_processed++))
            echo "   ✅ 预处理完成"
            
            # 3. 上传预处理文件到 S3
            aws s3 cp "$processed_file" "s3://$S3_BUCKET/$PROCESSED_PREFIX/$(basename $processed_file)" --quiet
        else
            echo "   ⚠️ 预处理失败"
        fi
        
        # 4. 删除原始文件（节省空间）
        rm -f "$local_file"
        
        ((processed_count++))
        
        # 每 10 个文件显示进度
        if [ $((processed_count % 10)) -eq 0 ]; then
            echo "   📊 进度: $processed_count / $file_count"
            df -h "$WORK_DIR" | tail -1 | awk '{print "   💾 剩余空间: "$4}'
        fi
    done
    
    echo "   ✅ 日期完成: 处理了 $processed_count 个文件"
    
    # 下一天
    current=$(date -d "$current + 1 day" "+%Y-%m-%d" 2>/dev/null || date -j -v+1d -f "%Y-%m-%d" "$current" "+%Y-%m-%d")
done

echo ""
echo "============================================"
echo "📊 统计"
echo "   下载: $total_downloaded"
echo "   处理: $total_processed"
echo "   失败: $total_failed"
echo "   时间: $(date)"
echo "============================================"

# 显示存储使用
echo ""
echo "💾 存储使用:"
du -sh "$PROCESSED_DIR"
df -h "$WORK_DIR"
