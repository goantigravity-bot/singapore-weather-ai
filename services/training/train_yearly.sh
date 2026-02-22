#!/usr/bin/env bash
# GPU 逐年增量训练脚本
#
# 数据路径:
#   S3 卫星源:     s3://weather-ai-models-de08370c/processed/satellite-3ch/{YYYYMMDD}/*.npy
#   S3 传感器源:   s3://weather-ai-models-de08370c/govdata/{YEAR}/*.json
#   本地卫星:      processed/{YEAR}/sat/{MM}/*.npy
#   本地传感器:    processed/{YEAR}/sensor/real_sensor_data.csv
#   训练读取:      SAT_DIR=processed/{YEAR}/sat, CSV_PATH=processed/{YEAR}/sensor/real_sensor_data.csv
#   日志输出:      logs/train_{YEAR}.log, logs/resource_{YEAR}.log
#   评估输出:      processed/{YEAR}/evaluation.json
#
# 用法: WORK_DIR=$PWD bash train_yearly.sh

set +e

WORK_DIR="${WORK_DIR:-$(pwd)}"
cd "$WORK_DIR"

S3_BUCKET="weather-ai-models-de08370c"
YEARS=(2020 2021 2022 2023 2024 2025 2026)
PYTHON="${PYTHON:-$WORK_DIR/venv/bin/python3}"
EPOCHS_INITIAL="${EPOCHS_INITIAL:-30}"
EPOCHS_INCREMENTAL="${EPOCHS_INCREMENTAL:-10}"
LOG_DIR="$WORK_DIR/logs"
TRAIN_START_TIME=$(date '+%Y-%m-%d %H:%M:%S')

# 通知函数（静默失败，不阻塞训练）
notify() {
    $PYTHON notify.py --type "$1" --year "${2:-}" --details "${3:-}" 2>/dev/null &
}

# 资源监控：后台每 30 秒记录 CPU/MEM/GPU
start_resource_monitor() {
    local log_file="$1"
    echo "timestamp,cpu_pct,mem_used_mb,mem_total_mb,gpu_util_pct,gpu_mem_used_mb" > "$log_file"
    while true; do
        TS=$(date '+%Y-%m-%d %H:%M:%S')
        CPU=$(top -bn1 | grep 'Cpu(s)' | awk '{print 100 - $8}')
        MEM=$(free -m | awk '/Mem:/{printf "%s,%s", $3, $2}')
        GPU=$(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits 2>/dev/null | tr ' ' '')
        echo "$TS,$CPU,$MEM,$GPU" >> "$log_file"
        sleep 30
    done
}

stop_resource_monitor() {
    if [ -n "$MONITOR_PID" ]; then
        kill "$MONITOR_PID" 2>/dev/null
        wait "$MONITOR_PID" 2>/dev/null
    fi
}

if [ ! -d "$LOG_DIR" ]; then
    mkdir -p "$LOG_DIR"
    echo "📁 创建日志目录: $LOG_DIR"
fi

# 首次训练前删除旧模型，确保从零开始
if [ -f "$WORK_DIR/weather_fusion_model.pth" ]; then
    echo "🗑️  删除旧模型 weather_fusion_model.pth，从零开始训练"
    rm -f "$WORK_DIR/weather_fusion_model.pth"
fi

echo "============================================" | tee "$LOG_DIR/train_summary.log"
echo "🚀 GPU 逐年增量训练 $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_DIR/train_summary.log"
echo "   WORK_DIR: $WORK_DIR" | tee -a "$LOG_DIR/train_summary.log"
echo "   PYTHON:   $PYTHON" | tee -a "$LOG_DIR/train_summary.log"
echo "   YEARS:    ${YEARS[*]}" | tee -a "$LOG_DIR/train_summary.log"
echo "============================================" | tee -a "$LOG_DIR/train_summary.log"

for YEAR in "${YEARS[@]}"; do
    LOG_FILE="$LOG_DIR/train_${YEAR}.log"
    RESOURCE_LOG="$LOG_DIR/resource_${YEAR}.log"
    SAT_LOG="$LOG_DIR/download_sat_${YEAR}.log"
    CSV_LOG="$LOG_DIR/download_csv_${YEAR}.log"

    echo "" | tee -a "$LOG_FILE"
    echo "============================================" | tee -a "$LOG_FILE"
    echo "📅 训练年份: $YEAR  $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
    echo "============================================" | tee -a "$LOG_FILE"

    YEAR_DIR="$WORK_DIR/processed/$YEAR"
    SAT_DIR="$YEAR_DIR/sat"
    SENSOR_DIR="$YEAR_DIR/sensor"
    CSV_PATH="$SENSOR_DIR/real_sensor_data.csv"

    echo "📂 数据路径:" | tee -a "$LOG_FILE"
    echo "   卫星 (训练读取): $SAT_DIR" | tee -a "$LOG_FILE"
    echo "   传感器 (训练读取): $CSV_PATH" | tee -a "$LOG_FILE"

    # ========== 1. 下载卫星数据（按月目录） ==========
    if [ ! -d "$SAT_DIR" ]; then
        mkdir -p "$SAT_DIR"
        echo "📁 创建卫星目录: $SAT_DIR" | tee -a "$LOG_FILE"
    fi

    # 统计 S3 上该年份的日期目录
    S3_DIRS=$(aws s3 ls "s3://${S3_BUCKET}/processed/satellite-3ch/" 2>/dev/null \
        | awk '{print $NF}' | grep "^${YEAR}" | tr -d '/')
    S3_DIR_COUNT=$(echo "$S3_DIRS" | grep -c "^${YEAR}" || echo 0)

    # 用 .complete 标记追踪已下载完成的日期目录
    LOCAL_COMPLETE=$(find "$SAT_DIR" -name ".complete_*" 2>/dev/null | wc -l | tr -d ' ')
    LOCAL_NPY_COUNT=$(find "$SAT_DIR" -name "*.npy" 2>/dev/null | wc -l | tr -d ' ')

    echo "📡 卫星数据: S3日期目录=$S3_DIR_COUNT, 已完成=$LOCAL_COMPLETE, 本地文件=$LOCAL_NPY_COUNT" | tee -a "$SAT_LOG"

    if [ "$LOCAL_COMPLETE" -lt "$S3_DIR_COUNT" ]; then
        DL_START=$(date '+%Y-%m-%d %H:%M:%S')
        echo "📥 下载 ${YEAR} 年卫星数据..." | tee -a "$SAT_LOG"
        notify download_start "$YEAR" "type=satellite,s3_dirs=$S3_DIR_COUNT,local_complete=$LOCAL_COMPLETE"
        for DIR in $S3_DIRS; do
            MONTH="${DIR:4:2}"
            MONTH_DIR="$SAT_DIR/$MONTH"
            if [ ! -d "$MONTH_DIR" ]; then
                mkdir -p "$MONTH_DIR"
            fi

            # 已完成则跳过
            if [ -f "$MONTH_DIR/.complete_${DIR}" ]; then
                continue
            fi

            # 下载该日期目录的所有 .npy
            S3_FILE_COUNT=$(aws s3 ls "s3://${S3_BUCKET}/processed/satellite-3ch/${DIR}/" 2>/dev/null \
                | grep "\.npy$" | wc -l | tr -d ' ')

            aws s3 cp "s3://${S3_BUCKET}/processed/satellite-3ch/${DIR}/" \
                "$MONTH_DIR/" \
                --recursive --exclude "*" --include "*.npy" \
                --quiet 2>/dev/null || true

            # 完整性检查
            LOCAL_FILE_COUNT=$(find "$MONTH_DIR" -name "SAT_*${DIR}*.npy" 2>/dev/null | wc -l | tr -d ' ')
            if [ "$LOCAL_FILE_COUNT" -ge "$S3_FILE_COUNT" ] && [ "$S3_FILE_COUNT" -gt "0" ]; then
                touch "$MONTH_DIR/.complete_${DIR}"
            else
                echo "   ⚠️ ${DIR}: 期望 ${S3_FILE_COUNT}, 实际 ${LOCAL_FILE_COUNT}" | tee -a "$SAT_LOG"
            fi
        done
        LOCAL_NPY_COUNT=$(find "$SAT_DIR" -name "*.npy" 2>/dev/null | wc -l | tr -d ' ')
        echo "   ✅ 卫星数据下载完成: ${LOCAL_NPY_COUNT} 个 .npy" | tee -a "$SAT_LOG"
        notify download_end "$YEAR" "type=satellite,npy_files=$LOCAL_NPY_COUNT,start=$DL_START,end=$(date '+%H:%M:%S')"
    else
        echo "   ✅ 卫星数据完整，跳过下载" | tee -a "$SAT_LOG"
    fi

    # ========== 2. 并行：卫星下载已在上面完成，生成传感器 CSV ==========
    if [ ! -d "$SENSOR_DIR" ]; then
        mkdir -p "$SENSOR_DIR"
        echo "📁 创建传感器目录: $SENSOR_DIR" | tee -a "$LOG_FILE"
    fi

    if [ ! -f "$CSV_PATH" ] || [ "$(wc -l < "$CSV_PATH" | tr -d ' ')" -le "1" ]; then
        echo "📊 生成 ${YEAR} 年传感器数据（逐天处理）..." | tee -a "$CSV_LOG"
        notify download_start "$YEAR" "type=sensor_csv,source=govdata_json"
        CSV_START=$(date '+%Y-%m-%d %H:%M:%S')
        $PYTHON process_gov_data_from_s3.py --year "$YEAR" --output "$CSV_PATH" 2>&1 | tee -a "$CSV_LOG"

        if [ -f "$CSV_PATH" ] && [ "$(wc -l < "$CSV_PATH" | tr -d ' ')" -gt "1" ]; then
            CSV_ROWS=$(wc -l < "$CSV_PATH" | tr -d ' ')
            CSV_SIZE=$(du -h "$CSV_PATH" | awk '{print $1}')
            echo "   ✅ 传感器数据: $CSV_ROWS 行" | tee -a "$CSV_LOG"
            notify download_end "$YEAR" "type=sensor_csv,rows=$CSV_ROWS,size=$CSV_SIZE,start=$CSV_START,end=$(date '+%H:%M:%S')"
        else
            echo "   ❌ 传感器数据生成失败！跳过 ${YEAR}" | tee -a "$CSV_LOG"
            continue
        fi
    else
        echo "   ✅ 传感器数据已存在: $(wc -l < "$CSV_PATH" | tr -d ' ') 行" | tee -a "$CSV_LOG"
    fi

    # ========== 3. 训练 ==========
    export SAT_DIR CSV_PATH

    # 启动资源监控
    start_resource_monitor "$RESOURCE_LOG" &
    MONITOR_PID=$!
    echo "📊 资源监控启动 (PID=$MONITOR_PID) → $RESOURCE_LOG" | tee -a "$LOG_FILE"

    TRAIN_MODE="initial"
    TRAIN_EPOCHS=$EPOCHS_INITIAL
    if [ -f "$WORK_DIR/weather_fusion_model.pth" ]; then
        TRAIN_MODE="incremental"
        TRAIN_EPOCHS=$EPOCHS_INCREMENTAL
    fi
    echo "🚀 训练 (${YEAR}): mode=$TRAIN_MODE, epochs=$TRAIN_EPOCHS" | tee -a "$LOG_FILE"
    notify train_start "$YEAR" "mode=$TRAIN_MODE,epochs=$TRAIN_EPOCHS,sat_files=$LOCAL_NPY_COUNT"
    EPOCH_START=$(date '+%Y-%m-%d %H:%M:%S')

    if [ "$TRAIN_MODE" = "initial" ]; then
        EPOCHS_INITIAL=$EPOCHS_INITIAL $PYTHON train_rolling_window.py 2>&1 | tee -a "$LOG_FILE"
    else
        EPOCHS_INCREMENTAL=$EPOCHS_INCREMENTAL $PYTHON train_rolling_window.py 2>&1 | tee -a "$LOG_FILE"
    fi

    stop_resource_monitor
    echo "✅ ${YEAR} 年训练完成 $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
    # 提取最后一个 epoch 的指标
    LAST_EPOCH=$(grep 'Epoch \[' "$LOG_FILE" | tail -1 || echo "N/A")
    notify train_end "$YEAR" "mode=$TRAIN_MODE,start=$EPOCH_START,end=$(date '+%H:%M:%S'),last_epoch=$LAST_EPOCH"

    # ========== 4. 逐年评估 ==========
    echo "📋 评估 ${YEAR} 年模型..." | tee -a "$LOG_FILE"
    $PYTHON diagnose_model.py 2>&1 | tee -a "$LOG_FILE"

    if [ -f "$WORK_DIR/diagnosis_results.json" ]; then
        cp "$WORK_DIR/diagnosis_results.json" "$YEAR_DIR/evaluation.json"
        echo "   💾 评估结果: $YEAR_DIR/evaluation.json" | tee -a "$LOG_FILE"
        EVAL_SUMMARY=$(python3 -c "import json;d=json.load(open('$WORK_DIR/diagnosis_results.json'));print(','.join(f'{k}={v}' for k,v in d.items() if isinstance(v,(int,float,str))))" 2>/dev/null || echo "N/A")
        notify eval "$YEAR" "$EVAL_SUMMARY"
    fi

    # ========== 5. 备份模型（本地 + S3）==========
    if [ -f "$WORK_DIR/weather_fusion_model.pth" ]; then
        cp "$WORK_DIR/weather_fusion_model.pth" "$YEAR_DIR/weather_fusion_model_${YEAR}.pth"
        aws s3 cp "$WORK_DIR/weather_fusion_model.pth" \
            "s3://${S3_BUCKET}/models/weather_fusion_model_${YEAR}.pth" --quiet 2>/dev/null
        echo "   💾 模型备份: $YEAR_DIR/ + s3://models/" | tee -a "$LOG_FILE"
    fi

    # 记录到汇总日志
    echo "✅ $YEAR 完成 $(date '+%H:%M:%S') | npy=$LOCAL_NPY_COUNT" >> "$LOG_DIR/train_summary.log"
    echo "" | tee -a "$LOG_FILE"
done

# 清理临时文件
rm -f /tmp/full_sensor_data.csv

echo "============================================" | tee -a "$LOG_DIR/train_summary.log"
echo "🎉 全部训练完成！ $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_DIR/train_summary.log"
echo "   模型: $WORK_DIR/weather_fusion_model.pth" | tee -a "$LOG_DIR/train_summary.log"
echo "   日志: $LOG_DIR/" | tee -a "$LOG_DIR/train_summary.log"
echo "============================================" | tee -a "$LOG_DIR/train_summary.log"

notify complete "" "years=${YEARS[*]},start=$TRAIN_START_TIME,end=$(date '+%Y-%m-%d %H:%M:%S')"
wait  # 等待所有后台通知发送完成
