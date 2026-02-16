#!/bin/bash
# run_batch_training.sh
# 完整的批次训练流程：从 S3 获取数据 → 预处理 → 训练 → 同步模型

set -e

WORK_DIR="/home/ubuntu/weather-ai"
cd "$WORK_DIR"

# 日期参数
START_DATE="${1:-}"
END_DATE="${2:-}"
EPOCHS="${3:-100}"

if [ -z "$START_DATE" ]; then
    echo "用法: $0 START_DATE [END_DATE] [EPOCHS]"
    echo "  例如: $0 2025-10-01 2025-10-03 100"
    exit 1
fi

if [ -z "$END_DATE" ]; then
    END_DATE="$START_DATE"
fi

echo "============================================"
echo "🚀 批次训练流程"
echo "   日期范围: $START_DATE 至 $END_DATE"
echo "   训练轮次: $EPOCHS"
echo "   时间: $(date)"
echo "============================================"

source venv/bin/activate

# 步骤 1: 从 S3 处理数据
echo ""
echo "📦 步骤 1: 从 S3 处理数据..."
./scripts/process_batch_from_s3.sh "$START_DATE" "$END_DATE"

# 步骤 2: 运行训练
echo ""
echo "🧠 步骤 2: 运行模型训练 ($EPOCHS epochs)..."
python train_rolling_window.py --epochs "$EPOCHS" 2>&1 | tail -20

# 步骤 3: 同步模型到 S3
echo ""
echo "☁️  步骤 3: 同步模型到 S3..."
./sync_model_to_s3.sh

echo ""
echo "============================================"
echo "✅ 批次训练完成"
echo "   时间: $(date)"
echo "============================================"
