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

S3_BUCKET="weather-ai-models-gcc"
if [ -n "$TRAIN_YEARS" ]; then
    IFS=' ' read -ra YEARS <<< "$TRAIN_YEARS"
else
    YEARS=(2020 2021 2022 2023 2024 2025 2026)
fi
PYTHON="${PYTHON:-$WORK_DIR/venv/bin/python3}"
EPOCHS_INITIAL="${EPOCHS_INITIAL:-30}"
EPOCHS_INCREMENTAL="${EPOCHS_INCREMENTAL:-10}"
LOG_DIR="$WORK_DIR/logs"
TRAIN_START_TIME=$(date '+%Y-%m-%d %H:%M:%S')

# 通知函数（静默失败，不阻塞训练）— 使用 shared/ 共用通知模块
NOTIFY_SCRIPT="$(cd "$(dirname "$0")/../shared" && pwd)/notify.py"
notify() {
    $PYTHON "$NOTIFY_SCRIPT" --type "$1" --year "${2:-}" --details "${3:-}" 2>/dev/null &
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

    # ========== 1 & 2. 并行下载卫星 + 生成传感器 CSV ==========

    # --- 任务 A: 卫星下载（后台） ---
    (
        if [ ! -d "$SAT_DIR" ]; then mkdir -p "$SAT_DIR"; fi

        S3_DIRS=$(aws s3 ls "s3://${S3_BUCKET}/processed/satellite-3ch/" 2>/dev/null \
            | awk '{print $NF}' | grep "^${YEAR}" | tr -d '/')
        S3_DIR_COUNT=$(echo "$S3_DIRS" | grep -c "^${YEAR}" || echo 0)
        LOCAL_COMPLETE=$(find "$SAT_DIR" -name ".complete_*" 2>/dev/null | wc -l | awk '{$1=$1};1')

        echo "📡 卫星: S3=$S3_DIR_COUNT 天, 已完成=$LOCAL_COMPLETE" | tee -a "$SAT_LOG"

        if [ "$LOCAL_COMPLETE" -lt "$S3_DIR_COUNT" ]; then
            DL_START=$(date '+%Y-%m-%d %H:%M:%S')
            echo "📥 下载 ${YEAR} 年卫星数据..." | tee -a "$SAT_LOG"
            notify download_start "$YEAR" "type=satellite,s3_dirs=$S3_DIR_COUNT,local_complete=$LOCAL_COMPLETE"
            SAT_DONE=0

            for DIR in $S3_DIRS; do
                MONTH="${DIR:4:2}"
                MONTH_DIR="$SAT_DIR/$MONTH"
                [ ! -d "$MONTH_DIR" ] && mkdir -p "$MONTH_DIR"
                [ -f "$MONTH_DIR/.complete_${DIR}" ] && { SAT_DONE=$((SAT_DONE+1)); continue; }

                S3_FC=$(aws s3 ls "s3://${S3_BUCKET}/processed/satellite-3ch/${DIR}/" 2>/dev/null \
                    | grep "\.npy$" | wc -l | awk '{$1=$1};1')
                aws s3 cp "s3://${S3_BUCKET}/processed/satellite-3ch/${DIR}/" \
                    "$MONTH_DIR/" --recursive --exclude "*" --include "*.npy" \
                    --quiet 2>/dev/null || true
                LOCAL_FC=$(find "$MONTH_DIR" -name "SAT_*${DIR}*.npy" 2>/dev/null | wc -l | awk '{$1=$1};1')
                if [ "$LOCAL_FC" -ge "$S3_FC" ] && [ "$S3_FC" -gt "0" ]; then
                    touch "$MONTH_DIR/.complete_${DIR}"
                else
                    echo "   ⚠️ ${DIR}: 期望 $S3_FC, 实际 $LOCAL_FC" | tee -a "$SAT_LOG"
                fi

                SAT_DONE=$((SAT_DONE+1))
                if [ $((SAT_DONE % 30)) -eq 0 ] || [ "$SAT_DONE" -eq "$S3_DIR_COUNT" ]; then
                    echo "   📡 Progress: $SAT_DONE/$S3_DIR_COUNT days, last: $DIR" | tee -a "$SAT_LOG"
                fi
            done

            LOCAL_NPY_COUNT=$(find "$SAT_DIR" -name "*.npy" 2>/dev/null | wc -l | awk '{$1=$1};1')
            echo "   ✅ 卫星下载完成: ${LOCAL_NPY_COUNT} .npy" | tee -a "$SAT_LOG"
            notify download_end "$YEAR" "type=satellite,npy=$LOCAL_NPY_COUNT,start=$DL_START,end=$(date '+%H:%M:%S')"
        else
            echo "   ✅ 卫星数据完整，跳过" | tee -a "$SAT_LOG"
        fi
    ) &
    SAT_PID=$!

    # --- 任务 B: 传感器 CSV 生成（后台） ---
    # 优先级: 本地缓存 → S3 缓存 → 从 govdata JSON 生成
    S3_CSV_KEY="processed/sensor/${YEAR}/real_sensor_data.csv"
    (
        [ ! -d "$SENSOR_DIR" ] && mkdir -p "$SENSOR_DIR"

        if [ -f "$CSV_PATH" ] && [ "$(wc -l < "$CSV_PATH" 2>/dev/null | tr -d ' \n')" -gt "1" ]; then
            echo "   ✅ CSV 本地已存在: $(wc -l < "$CSV_PATH" | tr -d ' \n') 行" | tee -a "$CSV_LOG"
        elif aws s3 ls "s3://${S3_BUCKET}/${S3_CSV_KEY}" >/dev/null 2>&1; then
            # S3 有缓存，直接下载（比从 JSON 生成快得多）
            echo "📥 从 S3 下载 ${YEAR} 年传感器 CSV 缓存..." | tee -a "$CSV_LOG"
            aws s3 cp "s3://${S3_BUCKET}/${S3_CSV_KEY}" "$CSV_PATH" --quiet 2>/dev/null
            CSV_ROWS=$(wc -l < "$CSV_PATH" 2>/dev/null | tr -d ' \n')
            if [ "$CSV_ROWS" -gt "1" ]; then
                CSV_SIZE=$(du -h "$CSV_PATH" | awk '{print $1}')
                echo "   ✅ S3 缓存下载完成: $CSV_ROWS 行 ($CSV_SIZE)" | tee -a "$CSV_LOG"
            else
                echo "   ⚠️ S3 缓存文件为空，回退到重新生成" | tee -a "$CSV_LOG"
                rm -f "$CSV_PATH"
            fi
        fi

        # 如果以上两步都没拿到有效 CSV，从 govdata JSON 生成
        if [ ! -f "$CSV_PATH" ] || [ "$(wc -l < "$CSV_PATH" 2>/dev/null | tr -d ' \n')" -le "1" ]; then
            echo "📊 从 govdata JSON 生成 ${YEAR} 年传感器 CSV..." | tee -a "$CSV_LOG"
            notify download_start "$YEAR" "type=sensor_csv,source=govdata_json"
            CSV_START=$(date '+%Y-%m-%d %H:%M:%S')
            $PYTHON process_gov_data_from_s3.py --year "$YEAR" --output "$CSV_PATH" 2>&1 | tee -a "$CSV_LOG"

            if [ -f "$CSV_PATH" ] && [ "$(wc -l < "$CSV_PATH" | tr -d ' \n')" -gt "1" ]; then
                CSV_ROWS=$(wc -l < "$CSV_PATH" | tr -d ' \n')
                CSV_SIZE=$(du -h "$CSV_PATH" | awk '{print $1}')
                echo "   ✅ CSV: $CSV_ROWS 行 ($CSV_SIZE)" | tee -a "$CSV_LOG"
                notify download_end "$YEAR" "type=sensor_csv,rows=$CSV_ROWS,size=$CSV_SIZE,start=$CSV_START,end=$(date '+%H:%M:%S')"

                # 上传到 S3 缓存，下次训练可直接下载
                echo "   ☁️ 上传 CSV 到 S3 缓存: s3://${S3_BUCKET}/${S3_CSV_KEY}" | tee -a "$CSV_LOG"
                aws s3 cp "$CSV_PATH" "s3://${S3_BUCKET}/${S3_CSV_KEY}" --quiet 2>/dev/null
            else
                echo "   ❌ CSV 生成失败" | tee -a "$CSV_LOG"
                notify error "$YEAR" "step=csv_generation,error=no_output"
                exit 1
            fi
        fi
    ) &
    CSV_PID=$!

    echo "⏳ 并行执行: 卫星(PID=$SAT_PID) + CSV(PID=$CSV_PID)" | tee -a "$LOG_FILE"

    # 等待两个任务都完成
    wait $SAT_PID
    SAT_EXIT=$?
    wait $CSV_PID
    CSV_EXIT=$?

    LOCAL_NPY_COUNT=$(find "$SAT_DIR" -name "*.npy" 2>/dev/null | wc -l | awk '{$1=$1};1')
    echo "✅ 数据就绪: sat_exit=$SAT_EXIT, csv_exit=$CSV_EXIT, npy=$LOCAL_NPY_COUNT" | tee -a "$LOG_FILE"

    if [ "$CSV_EXIT" -ne "0" ]; then
        echo "❌ CSV 生成失败，跳过 ${YEAR}" | tee -a "$LOG_FILE"
        continue
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
    TRAIN_EXIT=${PIPESTATUS[0]}

    stop_resource_monitor

    if [ "$TRAIN_EXIT" -ne "0" ]; then
        echo "❌ 训练异常退出 (exit=$TRAIN_EXIT) $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
        notify error "$YEAR" "stage=training,exit_code=$TRAIN_EXIT"
        continue
    fi

    echo "✅ ${YEAR} 年训练完成 $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
    # 提取最后一个 epoch 的指标
    LAST_EPOCH=$(grep 'Epoch \[' "$LOG_FILE" | tail -1 || echo "N/A")
    notify train_end "$YEAR" "mode=$TRAIN_MODE,start=$EPOCH_START,end=$(date '+%H:%M:%S'),last_epoch=$LAST_EPOCH"

    # ========== 4. 逐年评估 ==========
    echo "📋 评估 ${YEAR} 年模型..." | tee -a "$LOG_FILE"
    # diagnose_model.py 读取 $WORK_DIR 下的固定文件名，创建 symlink 指向当前年份
    ln -sf "$CSV_PATH" "$WORK_DIR/real_sensor_data.csv"
    ln -sfn "$SAT_DIR" "$WORK_DIR/processed_data"
    CSV_PATH="$CSV_PATH" SAT_DIR="$SAT_DIR" $PYTHON diagnose_model.py 2>&1 | tee -a "$LOG_FILE"

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
