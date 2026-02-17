# GCC 账号 (108379846317) Terraform 配置
# 仅管理: Download Server + S3 Bucket

# ========== 基础配置 ==========
aws_region             = "ap-southeast-1"
environment            = "staging"
project_name           = "weather-ai"

# ========== Download Server ==========
download_instance_type = "t3.xlarge"  # 4 vCPU / 16GB
download_volume_size   = 50           # GB

# ========== SSH ==========
ssh_public_key_path    = "~/.ssh/id_rsa.pub"
