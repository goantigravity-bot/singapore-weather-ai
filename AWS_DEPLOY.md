# AWS Deployment Guide for Weather Fusion Model

This guide explains how to deploy and run your training pipeline on an **AWS EC2** instance.

## Option 1: Quick Start (Deep Learning AMI)

The easiest way to get started without installing drivers manually.

### 1. Launch EC2 Instance
1.  Go to **EC2 Dashboard** > **Launch Instance**.
2.  **Name**: `Weather-Model-Trainer`
3.  **AMI**: Search for **"Deep Learning AMI (Ubuntu) PyTorch"**.
    *   *Why? It comes pre-installed with Python, PyTorch, CUDA drivers.*
4.  **Instance Type**:
    *   **t3.medium** (CPU only, cheap) - Good for debugging/small data.
    *   **g4dn.xlarge** (GPU T4) - Recommended for actual training.
5.  **Key Pair**: Create or select an existing `.pem` key.
6.  **Network**: Allow SSH (Port 22).

### 2. Connect to Instance
```bash
ssh -i "your-key.pem" ubuntu@your-ec2-public-ip
```

### 3. Setup Project
Inside the EC2 terminal:

```bash
# 1. Clone your code (or upload it via scp)
# Assumption: You put your code in a git repo
git clone https://github.com/your-username/your-repo.git weather-project
cd weather-project

# 2. Install Dependencies
# (The AMI has PyTorch, but we need pandas, etc)
pip install -r requirements.txt

# 3. Download Data
# Option A: Run the fetch script
python3 fetch_and_process_gov_data.py
# Option B (Recommended): Upload your local .csv/.npy files to S3 and download them here
# aws s3 cp s3://your-bucket/data/ ./ --recursive

### 3b. S3 Integration (Optional)
If you want to automatically upload downloaded JAXA files to S3 (to save space on EC2):
1. Create an S3 Bucket (e.g., `my-weather-data`).
2. Attach an IAM Role to your EC2 instance with `AmazonS3FullAccess` (or specific bucket access).
3. Set the environment variable:
   ```bash
   export S3_BUCKET="my-weather-data"
   ```

```

### 4. Run Pipeline
```bash
chmod +x run_pipeline.sh
./run_pipeline.sh
```

---

## Option 2: Docker Deployment (Best for Production)

If you prefer using the Dockerfile we created.

1.  **Install Docker** (If not on DL AMI):
    ```bash
    sudo apt-get update && sudo apt install docker.io
    ```
2.  **Build Image**:
    ```bash
    docker build -t weather-model .
    ```
3.  **Run**:
    ```bash
    # Run and mount current dir to save outputs (models/plots) back to host
    docker run -v $(pwd):/app weather-model
    ```

## ⚠️ Important Notes for AWS

1.  **Background Running**:
    If training takes hours, use `tmux` or `nohup` so it doesn't stop if you disconnect SSH.
    ```bash
    nohup ./run_pipeline.sh > training.log 2>&1 &
    ```
2.  **Cost**:
    Remember to **Stop** the instance when training ends to avoid billing!
