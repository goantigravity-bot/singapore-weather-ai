#!/bin/bash
# server-health-check.sh — Weather AI 三台服务器健康检查
# Usage: ./scripts/server-health-check.sh [download|training|api|all]

SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_rsa}"
SSH_OPTS="-o ConnectTimeout=10 -o StrictHostKeyChecking=no -i $SSH_KEY"

DOWNLOAD_HOST="ubuntu@18.142.90.30"
TRAINING_HOST="ubuntu@46.137.236.8"
API_HOST="ubuntu@3.0.28.161"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

header() {
    echo -e "\n${CYAN}${BOLD}════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}${BOLD}  $1${NC}"
    echo -e "${CYAN}${BOLD}════════════════════════════════════════════════════════${NC}"
}

icon() {
    case "$1" in
        ok)   echo -e "${GREEN}✅${NC}" ;;
        warn) echo -e "${YELLOW}⚠️${NC}" ;;
        *)    echo -e "${RED}❌${NC}" ;;
    esac
}

disk_status() {
    local pct=$1
    if [ "$pct" -gt 90 ] 2>/dev/null; then echo "fail"
    elif [ "$pct" -gt 75 ] 2>/dev/null; then echo "warn"
    else echo "ok"; fi
}

# Parse KEY=VALUE lines from SSH output, handling values with spaces
parse_val() {
    local key=$1
    echo "$SSH_OUT" | grep "^${key}=" | head -1 | sed "s/^${key}=//"
}

check_download_server() {
    header "Download Server — 18.142.90.30 (t3.micro)"

    SSH_OUT=$(ssh $SSH_OPTS "$DOWNLOAD_HOST" '
        echo "DISK_PCT=$(df / | tail -1 | awk "{print \$5}" | tr -d "%")"
        echo "DISK_AVAIL=$(df -h / | tail -1 | awk "{print \$4}")"
        echo "SERVICE=$(systemctl is-active weather-download 2>/dev/null || echo inactive)"
        echo "UPTIME=$(uptime -p 2>/dev/null || uptime)"
        if [ -f ~/download_manager.log ]; then
            echo "LAST_LOG=$(tail -1 ~/download_manager.log | cut -d" " -f1-2)"
        else
            echo "LAST_LOG=N/A"
        fi
        echo "FILES=$(ls ~/weather-ai/*.py 2>/dev/null | wc -l | tr -d " ")"
    ' 2>/dev/null) || { echo -e "  $(icon fail) ${RED}Cannot connect${NC}"; return; }

    local disk_pct=$(parse_val DISK_PCT)
    local disk_avail=$(parse_val DISK_AVAIL)
    local service=$(parse_val SERVICE)
    local uptime_str=$(parse_val UPTIME)
    local last_log=$(parse_val LAST_LOG)
    local files=$(parse_val FILES)

    local d_status=$(disk_status "$disk_pct")
    local s_status="fail"; [ "$service" = "active" ] && s_status="ok"

    echo -e "  $(icon $s_status) Service:    weather-download = ${BOLD}$service${NC}"
    echo -e "  $(icon $d_status) Disk:       ${BOLD}${disk_pct}%${NC} used (${disk_avail} free)"
    echo -e "  ℹ️  Uptime:     $uptime_str"
    echo -e "  ℹ️  Last Log:   $last_log"
    echo -e "  ℹ️  Scripts:    $files .py files"
}

check_training_server() {
    header "Training Server — 46.137.236.8 (t3.large)"

    SSH_OUT=$(ssh $SSH_OPTS "$TRAINING_HOST" '
        echo "DISK_PCT=$(df / | tail -1 | awk "{print \$5}" | tr -d "%")"
        echo "DISK_AVAIL=$(df -h / | tail -1 | awk "{print \$4}")"
        echo "TRAIN_PID=$(pgrep -f training_scheduler 2>/dev/null | head -1)"
        STATE=~/weather-ai/training_state.json
        if [ -f "$STATE" ]; then
            echo "LAST_DATE=$(python3 -c "import json; print(json.load(open(\"$STATE\")).get(\"last_processed_date\",\"N/A\"))" 2>/dev/null)"
            echo "BATCHES=$(python3 -c "import json; print(json.load(open(\"$STATE\")).get(\"total_batches_completed\",0))" 2>/dev/null)"
            echo "EPOCHS=$(python3 -c "import json; print(json.load(open(\"$STATE\")).get(\"total_epochs\",0))" 2>/dev/null)"
        else
            echo "LAST_DATE=N/A"; echo "BATCHES=0"; echo "EPOCHS=0"
        fi
        echo "SAT_COUNT=$(find ~/weather-ai/satellite_data -name "*.nc" 2>/dev/null | wc -l | tr -d " ")"
        echo "NPY_COUNT=$(find ~/weather-ai/processed_data -name "*.npy" 2>/dev/null | wc -l | tr -d " ")"
        echo "UPTIME=$(uptime -p 2>/dev/null || uptime)"
        if [ -f ~/training_scheduler.log ]; then
            echo "LAST_LOG=$(tail -1 ~/training_scheduler.log | cut -d" " -f1-2)"
        else
            echo "LAST_LOG=N/A"
        fi
    ' 2>/dev/null) || { echo -e "  $(icon fail) ${RED}Cannot connect${NC}"; return; }

    local disk_pct=$(parse_val DISK_PCT)
    local disk_avail=$(parse_val DISK_AVAIL)
    local train_pid=$(parse_val TRAIN_PID)
    local last_date=$(parse_val LAST_DATE)
    local batches=$(parse_val BATCHES)
    local epochs=$(parse_val EPOCHS)
    local sat_count=$(parse_val SAT_COUNT)
    local npy_count=$(parse_val NPY_COUNT)
    local uptime_str=$(parse_val UPTIME)
    local last_log=$(parse_val LAST_LOG)

    local d_status=$(disk_status "$disk_pct")
    local t_status="warn"; local t_msg="not running"
    if [ -n "$train_pid" ]; then t_status="ok"; t_msg="running (PID $train_pid)"; fi

    echo -e "  $(icon $t_status) Scheduler:  ${BOLD}$t_msg${NC}"
    echo -e "  $(icon $d_status) Disk:       ${BOLD}${disk_pct}%${NC} used (${disk_avail} free)"
    echo -e "  ℹ️  Progress:   ${BOLD}$batches batches${NC}, $epochs epochs, last: $last_date"
    echo -e "  ℹ️  Data:       $sat_count .nc, $npy_count .npy"
    echo -e "  ℹ️  Uptime:     $uptime_str"
    echo -e "  ℹ️  Last Log:   $last_log"
}

check_api_server() {
    header "API Server — 3.0.28.161 (t3.medium)"

    SSH_OUT=$(ssh $SSH_OPTS "$API_HOST" '
        echo "DISK_PCT=$(df / | tail -1 | awk "{print \$5}" | tr -d "%")"
        echo "DISK_AVAIL=$(df -h / | tail -1 | awk "{print \$4}")"
        echo "API_STATUS=$(systemctl is-active weather-api 2>/dev/null || echo inactive)"
        echo "NGINX_STATUS=$(systemctl is-active nginx 2>/dev/null || echo inactive)"
        echo "HEALTH=$(curl -s --max-time 5 http://localhost:8000/health 2>/dev/null || echo unreachable)"
        if [ -f ~/weather-ai/weather_fusion_model.pth ]; then
            echo "MODEL_SIZE=$(stat -c%s ~/weather-ai/weather_fusion_model.pth 2>/dev/null || echo 0)"
            echo "MODEL_DATE=$(stat -c%y ~/weather-ai/weather_fusion_model.pth 2>/dev/null | cut -d. -f1)"
        else
            echo "MODEL_SIZE=0"; echo "MODEL_DATE=N/A"
        fi
        echo "NPY_COUNT=$(find ~/weather-ai/processed_data -name "*.npy" 2>/dev/null | wc -l | tr -d " ")"
        echo "NC_COUNT=$(find ~/weather-ai/satellite_data -name "*.nc" 2>/dev/null | wc -l | tr -d " ")"
        echo "UPTIME=$(uptime -p 2>/dev/null || uptime)"
    ' 2>/dev/null) || { echo -e "  $(icon fail) ${RED}Cannot connect${NC}"; return; }

    local disk_pct=$(parse_val DISK_PCT)
    local disk_avail=$(parse_val DISK_AVAIL)
    local api_status=$(parse_val API_STATUS)
    local nginx_status=$(parse_val NGINX_STATUS)
    local health=$(parse_val HEALTH)
    local model_size=$(parse_val MODEL_SIZE)
    local model_date=$(parse_val MODEL_DATE)
    local npy_count=$(parse_val NPY_COUNT)
    local nc_count=$(parse_val NC_COUNT)
    local uptime_str=$(parse_val UPTIME)

    local d_status=$(disk_status "$disk_pct")
    local a_status="fail"; [ "$api_status" = "active" ] && a_status="ok"
    local n_status="fail"; [ "$nginx_status" = "active" ] && n_status="ok"
    local h_status="fail"; echo "$health" | grep -q '"status":"ok"' && h_status="ok"

    # Model size in MB
    local model_mb="?"
    if [ "$model_size" -gt 0 ] 2>/dev/null; then
        model_mb=$(awk "BEGIN {printf \"%.1f\", $model_size/1048576}")
    fi

    echo -e "  $(icon $a_status) Service:    weather-api = ${BOLD}$api_status${NC}"
    echo -e "  $(icon $n_status) Nginx:      ${BOLD}$nginx_status${NC}"
    echo -e "  $(icon $h_status) Health:     $health"
    echo -e "  $(icon $d_status) Disk:       ${BOLD}${disk_pct}%${NC} used (${disk_avail} free)"
    echo -e "  ℹ️  Model:      ${model_mb}MB (updated: $model_date)"
    echo -e "  ℹ️  Data:       $npy_count .npy (processed), $nc_count .nc (legacy)"
    echo -e "  ℹ️  Uptime:     $uptime_str"
}

# --- Main ---
TARGET="${1:-all}"

echo -e "${BOLD}Weather AI Server Health Check${NC}"
echo -e "Time: $(date '+%Y-%m-%d %H:%M:%S %Z')"

case "$TARGET" in
    download) check_download_server ;;
    training) check_training_server ;;
    api)      check_api_server ;;
    all)
        check_download_server
        check_training_server
        check_api_server
        echo -e "\n${CYAN}${BOLD}════════════════════════════════════════════════════════${NC}"
        echo -e "${GREEN}${BOLD}  Done${NC}"
        echo -e "${CYAN}${BOLD}════════════════════════════════════════════════════════${NC}\n"
        ;;
    *)
        echo "Usage: $0 [download|training|api|all]"
        exit 1
        ;;
esac
