#!/bin/bash
# 逐年增量训练脚本
# 每年一个批次，控制内存使用：
#   1. 只下载当年 satellite-3ch .npy 到 processed_data/
#   2. 生成当年 govdata CSV
#   3. 训练（首年 30 epochs，后续增量 5 epochs）
#
# 用法: AWS_PROFILE=personal WORK_DIR=$PWD bash train_yearly.sh

set -e

WORK_DIR="${WORK_DIR:-$(dirname "$0")}"
cd "$WORK_DIR"

S3_BUCKET="weather-ai-models-de08370c"
YEARS=(2020 2021 2022 2023 2024 2025 2026)
PYTHON="${PYTHON:-python3}"

echo "============================================"
echo "🚀 逐年增量训练 (${YEARS[0]}-${YEARS[-1]})"
echo "   WORK_DIR: $WORK_DIR"
echo "============================================"

for YEAR in "${YEARS[@]}"; do
    echo ""
    echo "============================================"
    echo "📅 训练年份: $YEAR"
    echo "============================================"

    # 1. 清理 processed_data/ 释放内存
    echo "🗑️  清理上一年卫星数据..."
    find processed_data -name "*.npy" -delete 2>/dev/null || true
    rm -rf processed_data/*/ 2>/dev/null || true

    # 2. 下载当年 satellite-3ch .npy（按日期前缀过滤）
    echo "📡 下载 ${YEAR} 年卫星数据..."
    aws s3 cp "s3://${S3_BUCKET}/processed/satellite-3ch/" processed_data/ \
        --recursive \
        --exclude "*" \
        --include "SAT_B*_${YEAR}*.npy" \
        --quiet

    # 展平子目录（aws s3 cp 保持目录结构）
    find processed_data -mindepth 2 -name "*.npy" -exec mv {} processed_data/ \; 2>/dev/null || true
    find processed_data -type d -empty -delete 2>/dev/null || true

    NPY_COUNT=$(find processed_data -name "*.npy" | wc -l | tr -d ' ')
    echo "   ✅ 已下载 ${NPY_COUNT} 个 .npy 文件"

    # 3. 生成当年 CSV（只处理当年 govdata）
    echo "📊 处理 ${YEAR} 年传感器数据..."
    # 用 --date 参数限定年份范围（process_gov_data_from_s3 按年份前缀匹配）
    START_DATE="${YEAR}-01-01"
    END_DATE="${YEAR}-12-31"
    if [ "$YEAR" = "2026" ]; then
        END_DATE="2026-02-16"
    fi
    $PYTHON process_gov_data_from_s3.py --date "$YEAR" --reset

    # 4. 训练
    if [ ! -f "weather_fusion_model.pth" ]; then
        echo "🆕 首次训练 (${YEAR}): EPOCHS_INITIAL=30"
        EPOCHS_INITIAL=30 $PYTHON train_rolling_window.py
    else
        echo "🔄 增量训练 (${YEAR}): EPOCHS_INCREMENTAL=10"
        EPOCHS_INCREMENTAL=10 $PYTHON train_rolling_window.py
    fi

    echo "✅ ${YEAR} 年训练完成"
done

echo ""
echo "============================================"
echo "🎉 全部训练完成！"
echo "   模型: weather_fusion_model.pth"
echo "============================================"
