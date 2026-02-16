#!/bin/bash

# Stop on error
set -e

echo "==========================================="
echo "   Weather Fusion Model - Cloud Pipeline   "
echo "==========================================="
date

# 1. Environment Check (Optional)
if [ -f "requirements.txt" ]; then
    echo "[1/4] Checking Dependencies..."
    pip install -r requirements.txt | grep -v "Requirement already satisfied"
else
    echo "Warning: requirements.txt not found."
fi

# 2. Data Sync (Optional - set UPDATE_DATA=true to enable)
if [ "$UPDATE_DATA" = "true" ]; then
    echo "[2/4] Fetching Data..."
    
    # 2a. Sensor Data
    echo "  > Syncing NEA Sensor Data..."
    python3 fetch_and_process_gov_data.py
    
    # 2b. Satellite Data (JAXA)
    # Requires JAXA_USER and JAXA_PASS env vars to be set
    if [ -n "$JAXA_USER" ] && [ -n "$JAXA_PASS" ]; then
         echo "  > Syncing JAXA Satellite Data (Last 24h example)..."
         # Example: Download last 24 hours. For specific range use --start 2026-01-20 --end 2026-01-21
         python3 download_jaxa_data.py --mode batch --hours 24
         
         echo "  > Preprocessing Satellite Images..."
         python3 preprocess_images.py
    else
         echo "  > Skipping Satellite Download (JAXA_USER/PASS not set)"
    fi
else
    echo "[2/4] Skipping data fetch (Set UPDATE_DATA=true to run)"
fi

# 3. Training
echo "[3/4] Starting Model Training..."
# You can pass arguments to train.py if you modify it to accept args (e.g. --epochs)
python3 train.py

# 4. Evaluation
echo "[4/4] Evaluating Model..."
python3 evaluate.py

echo "==========================================="
echo "   Pipeline Completed Successfully!        "
echo "==========================================="
