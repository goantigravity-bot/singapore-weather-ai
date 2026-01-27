#!/bin/bash
# deploy_training_server.sh
# Usage: ./deploy_training_server.sh <TRAINING_SERVER_IP> <KEY_FILE>

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <TRAINING_SERVER_IP> <KEY_FILE>"
    exit 1
fi

TRAINING_SERVER_IP=$1
KEY_FILE=$2

echo "Deploying to $TRAINING_SERVER_IP..."

# 1. Sync Code
echo "Syncing code..."
rsync -avz -e "ssh -i $KEY_FILE -o StrictHostKeyChecking=no" \
  --exclude 'venv' \
  --exclude 'node_modules' \
  --exclude '__pycache__' \
  --exclude '.git' \
  --exclude 'processed_data' \
  --exclude 'training_logs' \
  ./ ubuntu@$TRAINING_SERVER_IP:~/singapore-weather-ai/

# 2. Setup Remote Environment
echo "Setting up remote environment..."
ssh -i $KEY_FILE -o StrictHostKeyChecking=no ubuntu@$TRAINING_SERVER_IP << 'EOF'
    set -e
    
    # System Deps
    sudo apt-get update
    sudo apt-get install -y python3.10 python3.10-venv python3-pip libhdf5-dev libnetcdf-dev awscli
    
    cd ~/singapore-weather-ai
    
    # Python Venv
    if [ ! -d "venv" ]; then
        python3.10 -m venv venv
    fi
    
    source venv/bin/activate
    
    # Install Python Deps
    pip install -r requirements.txt
    # Ensure Torch is installed (CPU version likely for t2/micro unless specified otherwise, but script handles CUDA checks)
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    
    echo "✅ Setup Complete. "
    echo "To start training manually: "
    echo "  cd ~/singapore-weather-ai && source venv/bin/activate && python3 auto_train_pipeline.py"
EOF
