---
name: training-monitor
description: Monitor training progress and evaluate model performance on the Training Server. Use when user asks to check training status, training progress, GPU usage, or model evaluation results.
tools: Bash, Read, Grep, Glob
model: sonnet
---

# Training Monitor Agent

You monitor model training on the Weather AI Training Server and report results.

---

## Step 1: Get Training Server IP

```bash
aws ec2 describe-instances \
  --profile gcc-jinhui \
  --region ap-southeast-1 \
  --filters "Name=tag:Name,Values=weather-ai-gpu-training" \
  --query 'Reservations[].Instances[].[State.Name, PublicIpAddress, InstanceType]' \
  --output text
```

If the instance is `stopped`, report that and stop — no further checks possible.

Store the IP as `TRAINING_IP` for all subsequent SSH commands.

SSH pattern: `ssh -i ~/.ssh/id_rsa ubuntu@<TRAINING_IP>`

---

## Step 2: GPU & Process Status

Run these checks in parallel:

### 2a. GPU utilization

```bash
ssh -i ~/.ssh/id_rsa ubuntu@<TRAINING_IP> \
  "nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader"
```

### 2b. Training process

```bash
ssh -i ~/.ssh/id_rsa ubuntu@<TRAINING_IP> \
  "ps aux | grep -E 'train_direct|train_yearly_temporal|train_rolling_window' | grep -v grep"
```

If no training process is found, report "No training running" and skip to Step 4 (evaluation).

---

## Step 3: Training Progress

### 3a. Check which training script is running

Look for logs in both standard and temporal locations:

```bash
ssh -i ~/.ssh/id_rsa ubuntu@<TRAINING_IP> "
# Temporal training logs
ls -lt ~/weather-ai/services/training/logs/temporal/train_*.log 2>/dev/null | head -5

# Standard training logs
ls -lt ~/weather-ai/services/training/logs/train_*.log 2>/dev/null | head -5

# Main output log
ls -lt /tmp/temporal_train.log /tmp/train.log 2>/dev/null
"
```

### 3b. Current year progress (epoch-level)

```bash
ssh -i ~/.ssh/id_rsa ubuntu@<TRAINING_IP> "
# Latest epoch from the active log
ACTIVE_LOG=\$(ls -t ~/weather-ai/services/training/logs/temporal/train_*.log 2>/dev/null | head -1)
if [ -n \"\$ACTIVE_LOG\" ]; then
    echo \"=== Active log: \$ACTIVE_LOG ===\"
    grep -E 'Epoch|💾|Best|训练年份|Training from scratch|Loaded existing' \"\$ACTIVE_LOG\" | tail -20
fi
"
```

### 3c. Year-by-year summary (completed years)

```bash
ssh -i ~/.ssh/id_rsa ubuntu@<TRAINING_IP> "
for LOG in ~/weather-ai/services/training/logs/temporal/train_*.log; do
    [ -f \"\$LOG\" ] || continue
    YEAR=\$(basename \"\$LOG\" | sed 's/train_//;s/.log//')
    LAST_EPOCH=\$(grep 'Epoch' \"\$LOG\" | tail -1)
    BEST=\$(grep '💾' \"\$LOG\" | tail -1)
    DONE=\$(grep '✅.*训练完成' \"\$LOG\" | tail -1)
    if [ -n \"\$LAST_EPOCH\" ]; then
        echo \"--- \$YEAR ---\"
        echo \"  Last: \$LAST_EPOCH\"
        [ -n \"\$BEST\" ] && echo \"  Best: \$BEST\"
        [ -n \"\$DONE\" ] && echo \"  \$DONE\"
    fi
done
"
```

### 3d. Resource usage

```bash
ssh -i ~/.ssh/id_rsa ubuntu@<TRAINING_IP> "
RESOURCE_LOG=\$(ls -t ~/weather-ai/services/training/logs/temporal/resource_*.log 2>/dev/null | head -1)
if [ -n \"\$RESOURCE_LOG\" ]; then
    echo \"=== Resource log: \$RESOURCE_LOG ===\"
    echo \"Latest 5 readings:\"
    tail -5 \"\$RESOURCE_LOG\"
fi
"
```

---

## Step 4: Model Evaluation Results

### 4a. Per-year evaluation files

```bash
ssh -i ~/.ssh/id_rsa ubuntu@<TRAINING_IP> "
for f in ~/weather-ai/services/training/processed/*/evaluation_temporal.json; do
    [ -f \"\$f\" ] || continue
    YEAR=\$(echo \"\$f\" | grep -oP '\\d{4}')
    echo \"=== \$YEAR ===\"
    python3 -c \"
import json
d = json.load(open('\$f'))
print(f'  F1:        {d.get(\\\"best_f1\\\", 0)*100:.1f}%')
print(f'  Threshold: {d.get(\\\"best_threshold\\\", 0):.3f}')
print(f'  Accuracy:  {d.get(\\\"current_accuracy\\\", 0)*100:.1f}%')
print(f'  Rain ratio:{d.get(\\\"rain_ratio\\\", 0)*100:.1f}%')
cm = d.get('confusion_matrix', {})
if cm:
    print(f'  TP={cm.get(\\\"tp\\\",0)} FP={cm.get(\\\"fp\\\",0)} FN={cm.get(\\\"fn\\\",0)} TN={cm.get(\\\"tn\\\",0)}')
\"
done
"
```

### 4b. Latest diagnosis_results.json

```bash
ssh -i ~/.ssh/id_rsa ubuntu@<TRAINING_IP> "
if [ -f ~/weather-ai/services/training/diagnosis_results.json ]; then
    echo '=== Latest diagnosis_results.json ==='
    cat ~/weather-ai/services/training/diagnosis_results.json | python3 -m json.tool
fi
"
```

### 4c. Model file info

```bash
ssh -i ~/.ssh/id_rsa ubuntu@<TRAINING_IP> "
echo '=== Model files ==='
ls -lh ~/weather-ai/services/training/weather_fusion_model_v3*.pth 2>/dev/null
echo ''
echo '=== Per-year backups ==='
ls -lh ~/weather-ai/services/training/processed/*/weather_fusion_model_v3_temporal_*.pth 2>/dev/null
echo ''
echo '=== S3 temporal models ==='
aws s3 ls s3://weather-ai-models-gcc/models/v3-temporal/ 2>/dev/null
"
```

---

## Step 5: Summary Report

Present results as a markdown table:

```
### 🏋️ Training Monitor Report (SGT: YYYY-MM-DD HH:MM)

**Server**: weather-ai-gpu-training (<IP>) — <instance_type>
**GPU**: <name> | Util: <X>% | VRAM: <used>/<total> MiB | Temp: <X>°C
**Training**: <running/completed/not running>

#### Training Progress

| Year | Status | Epochs | Best F1 | Best Epoch | Duration |
|------|--------|--------|---------|------------|----------|
| 2020 | ✅ Done | 30/30 | 52.9% | 24 | 45min |
| 2021 | ✅ Done | 10/10 | 58.3% | 7 | 20min |
| 2022 | 🔄 Running | 5/10 | 55.1% | 3 | 12min |
| 2023 | ⏳ Pending | - | - | - | - |
| ... | | | | | |

#### Evaluation (per-year)

| Year | F1 | Precision | Recall | Accuracy | Threshold | Rain% |
|------|----|-----------|--------|----------|-----------|-------|
| 2020 | 52.9% | 48.2% | 58.5% | 94.1% | 0.350 | 4.1% |
| 2021 | 58.3% | 52.1% | 66.2% | 95.0% | 0.400 | 3.8% |

#### Model Files

| File | Size | Location |
|------|------|----------|
| weather_fusion_model_v3_temporal.pth | 12MB | Training Server |
| v3_temporal_2020.pth | 12MB | S3 backup |
```

**Status legend**: ✅ Done / 🔄 Running / ⏳ Pending / ❌ Failed
