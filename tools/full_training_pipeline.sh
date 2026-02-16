#!/bin/bash
# full_training_pipeline.sh
# 完整的端到端训练流程（含邮件通知）
# 
# 步骤:
# 1. 流式下载并预处理卫星数据
# 2. 下载政府数据
# 3. 运行模型训练
# 4. 同步模型到 S3
# 5. 发送邮件通知

set -e

WORK_DIR="/home/ubuntu/weather-ai"
cd "$WORK_DIR"

# 加载环境变量
if [ -f ".env.production" ]; then
    export $(grep -v '^#' .env.production | xargs)
fi

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

# 日志文件
LOG_FILE="$WORK_DIR/training_logs/training_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$WORK_DIR/training_logs"

# 记录开始时间
START_TIME=$(date +%s)

echo "============================================" | tee -a "$LOG_FILE"
echo "🚀 完整训练流程" | tee -a "$LOG_FILE"
echo "   日期范围: $START_DATE 至 $END_DATE" | tee -a "$LOG_FILE"
echo "   训练轮次: $EPOCHS" | tee -a "$LOG_FILE"
echo "   开始时间: $(date)" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"

# 激活虚拟环境
source venv/bin/activate

# 错误处理函数
handle_error() {
    local step="$1"
    local error_msg="$2"
    
    echo "" | tee -a "$LOG_FILE"
    echo "❌ 训练失败于步骤: $step" | tee -a "$LOG_FILE"
    echo "错误信息: $error_msg" | tee -a "$LOG_FILE"
    
    # 发送失败通知邮件
    python -c "
from notification import send_training_failure_email
send_training_failure_email(
    error_message='$error_msg',
    step_failed='$step',
    log_path='$LOG_FILE'
)
" 2>&1 | tee -a "$LOG_FILE"
    
    exit 1
}

# 步骤 1: 流式下载并预处理卫星数据
echo "" | tee -a "$LOG_FILE"
echo "📡 步骤 1: 下载并预处理卫星数据..." | tee -a "$LOG_FILE"
if ! ./scripts/stream_download_process.sh "$START_DATE" "$END_DATE" 2>&1 | tee -a "$LOG_FILE"; then
    handle_error "卫星数据下载/预处理" "stream_download_process.sh 执行失败"
fi

# 步骤 2: 下载政府数据
echo "" | tee -a "$LOG_FILE"
echo "📊 步骤 2: 下载政府数据..." | tee -a "$LOG_FILE"
if ! ./scripts/download_govdata_to_s3.sh "$START_DATE" "$END_DATE" 2>&1 | tee -a "$LOG_FILE"; then
    handle_error "政府数据下载" "download_govdata_to_s3.sh 执行失败"
fi

# 步骤 3: 获取最新天气数据（用于验证）
echo "" | tee -a "$LOG_FILE"
echo "🌤️ 步骤 3: 获取最新天气数据..." | tee -a "$LOG_FILE"
if ! python fetch_and_process_gov_data.py 2>&1 | tee -a "$LOG_FILE"; then
    handle_error "获取天气数据" "fetch_and_process_gov_data.py 执行失败"
fi

# 步骤 4: 运行模型训练
echo "" | tee -a "$LOG_FILE"
echo "🧠 步骤 4: 运行模型训练 ($EPOCHS epochs)..." | tee -a "$LOG_FILE"
if ! python train_rolling_window.py --epochs "$EPOCHS" 2>&1 | tee -a "$LOG_FILE"; then
    handle_error "模型训练" "train_rolling_window.py 执行失败"
fi

# 步骤 5: 同步模型到 S3
echo "" | tee -a "$LOG_FILE"
echo "☁️ 步骤 5: 同步模型到 S3..." | tee -a "$LOG_FILE"
if ! ./sync_model_to_s3.sh 2>&1 | tee -a "$LOG_FILE"; then
    handle_error "模型同步" "sync_model_to_s3.sh 执行失败"
fi

# 计算总耗时
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
HOURS=$((DURATION / 3600))
MINUTES=$(((DURATION % 3600) / 60))
SECONDS=$((DURATION % 60))

echo "" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"
echo "✅ 训练流程完成" | tee -a "$LOG_FILE"
echo "   总耗时: ${HOURS}h ${MINUTES}m ${SECONDS}s" | tee -a "$LOG_FILE"
echo "   结束时间: $(date)" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"

# 步骤 6: 发送成功通知邮件
echo "" | tee -a "$LOG_FILE"
echo "📧 步骤 6: 发送通知邮件..." | tee -a "$LOG_FILE"
python -c "
from notification import send_training_success_email
import os

# 查找最新的报告和图表
report_dir = 'training_reports'
latest_report = None
latest_plot = None

if os.path.exists(report_dir):
    files = os.listdir(report_dir)
    reports = [f for f in files if f.endswith('.html')]
    plots = [f for f in files if f.endswith('.png')]
    
    if reports:
        latest_report = os.path.join(report_dir, sorted(reports)[-1])
    if plots:
        latest_plot = os.path.join(report_dir, sorted(plots)[-1])

# 读取指标
metrics = {'mae': 0.0, 'rmse': 0.0, 'accuracy': 0.0}
try:
    import json
    with open('training_reports/latest_metrics.json', 'r') as f:
        metrics = json.load(f)
except:
    pass

send_training_success_email(
    report_path=latest_report or '',
    plot_path=latest_plot or '',
    metrics=metrics
)
print('✅ 邮件发送完成')
" 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "🎉 全部完成！" | tee -a "$LOG_FILE"
