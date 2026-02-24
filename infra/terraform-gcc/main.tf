# GCC 账号 Terraform 配置
# Account: 108379846317 (gcc-jinhui-dev)
# 仅管理: Download Server + S3 Bucket

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "weather-ai"
      Owner       = "jin_hui@customs.gov.sg"
      Environment = "dev"
      ExpiryDate  = "31-march-2026"
      ManagedBy   = "Terraform"
      Account     = "gcc-jinhui"
    }
  }
}

# ========== 变量 ==========

variable "aws_region" {
  type    = string
  default = "ap-southeast-1"
}

variable "environment" {
  type    = string
  default = "staging"
}

variable "project_name" {
  type    = string
  default = "weather-ai"
}

variable "api_instance_type" {
  description = "API 服务器实例类型"
  type        = string
  default     = "t3.medium"
}

variable "api_volume_size" {
  description = "API 服务器根卷大小 (GB)"
  type        = number
  default     = 20
}

variable "download_instance_type" {
  description = "下载服务器实例类型"
  type        = string
  default     = "t3.xlarge"
}

variable "download_volume_size" {
  description = "下载服务器磁盘大小 (GB)"
  type        = number
  default     = 50
}

variable "training_instance_type" {
  description = "训练服务器实例类型 — GPU"
  type        = string
  default     = "g4dn.2xlarge"
}

variable "training_volume_size" {
  description = "训练服务器根卷大小 (GB)"
  type        = number
  default     = 200
}

variable "ssh_public_key_path" {
  type    = string
  default = "~/.ssh/id_rsa.pub"
}

# ========== 网络 ==========

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# ========== SSH 密钥 ==========
# 同一个公钥可在多个 AWS 账号注册，私钥保持在本地

resource "aws_key_pair" "main" {
  key_name   = "${var.project_name}-key"
  public_key = file(var.ssh_public_key_path)

  tags = { Name = "${var.project_name}-key" }
}

# ========== 安全组 ==========

resource "aws_security_group" "download" {
  name        = "${var.project_name}-download-sg"
  description = "Security group for download server"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-download-sg" }
}

# ========== EC2: Download Server ==========

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_instance" "download_server" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = var.download_instance_type
  key_name      = aws_key_pair.main.key_name

  vpc_security_group_ids = [aws_security_group.download.id]
  iam_instance_profile   = aws_iam_instance_profile.download_profile.name

  user_data = <<-EOF
    #!/bin/bash
    set -e
    exec > /var/log/user-data.log 2>&1
    timedatectl set-timezone Asia/Singapore

    # Python venv + 依赖
    apt-get update -qq
    apt-get install -y python3.10-venv git
    su - ubuntu -c '
      cd /home/ubuntu
      git clone https://github.com/goantigravity-bot/singapore-weather-ai.git weather-ai || true
      cd weather-ai
      python3 -m venv venv
      venv/bin/pip install -q boto3 requests pandas numpy netCDF4

      # .env 配置
      echo "S3_BUCKET=weather-ai-models-gcc" > services/download/.env

      # 日志推送脚本（boto3，无需 aws CLI）
      cat > /home/ubuntu/push_log.py << "PYEOF"
import boto3, os
s3 = boto3.client("s3")
bucket = os.environ.get("S3_BUCKET", "weather-ai-models-gcc")
log = "/home/ubuntu/weather-ai/download.log"
if os.path.exists(log):
    s3.upload_file(log, bucket, "logs/download.log")
PYEOF

      # 每 5 分钟推送日志到 S3
      (crontab -l 2>/dev/null; echo "*/5 * * * * /home/ubuntu/weather-ai/venv/bin/python3 /home/ubuntu/push_log.py > /dev/null 2>&1") | crontab -
    '
    echo "Setup complete at $(date)"
  EOF

  root_block_device {
    volume_size = var.download_volume_size
    volume_type = "gp3"
    encrypted   = true

    tags = { Name = "${var.project_name}-download-volume" }
  }

  tags = { Name = "${var.project_name}-download-server" }
}

# ========== 安全组: API Server ==========

resource "aws_security_group" "api" {
  name        = "${var.project_name}-api-sg"
  description = "Security group for API server"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "API"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-api-sg" }
}

# ========== 安全组: Training Server ==========

resource "aws_security_group" "training" {
  name        = "${var.project_name}-training-sg"
  description = "Security group for Training server"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "MLflow UI"
    from_port   = 5000
    to_port     = 5000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-training-sg" }
}

# ========== EC2: API Server ==========

resource "aws_instance" "api_server" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = var.api_instance_type
  key_name      = aws_key_pair.main.key_name

  vpc_security_group_ids = [aws_security_group.api.id]
  iam_instance_profile   = aws_iam_instance_profile.api_profile.name

  user_data = <<-EOF
    #!/bin/bash
    set -e
    exec > /var/log/user-data.log 2>&1
    timedatectl set-timezone Asia/Singapore

    # Python venv + 依赖
    apt-get update -qq
    apt-get install -y python3.10-venv git npm
    su - ubuntu -c '
      cd /home/ubuntu
      git clone https://github.com/goantigravity-bot/singapore-weather-ai.git weather-ai || true
      cd weather-ai
      python3 -m venv venv
      venv/bin/pip install -q fastapi uvicorn python-multipart boto3 pandas torch numpy scipy xarray netCDF4 requests
      cd services/api/frontend && npm install && npm run build
    '
    echo "Setup complete at $(date)"
  EOF

  root_block_device {
    volume_size = var.api_volume_size
    volume_type = "gp3"
    encrypted   = true

    tags = { Name = "${var.project_name}-api-volume" }
  }

  tags = { Name = "${var.project_name}-api-server" }
}

# 弹性 IP — API Server 需要固定 IP
resource "aws_eip" "api" {
  instance = aws_instance.api_server.id
  domain   = "vpc"

  tags = { Name = "${var.project_name}-api-eip" }
}

# ========== EC2: Training Server ==========

resource "aws_instance" "training_server" {
  # Deep Learning AMI (PyTorch 2.9, Ubuntu 24.04, NVIDIA drivers)
  ami           = "ami-081296c6e1ebbba80"
  instance_type = var.training_instance_type
  key_name      = aws_key_pair.main.key_name

  vpc_security_group_ids = [aws_security_group.training.id]
  iam_instance_profile   = aws_iam_instance_profile.training_profile.name

  user_data = <<-EOF
    #!/bin/bash
    set -e
    exec > /var/log/user-data.log 2>&1
    timedatectl set-timezone Asia/Singapore

    # Training server 使用 Deep Learning AMI — PyTorch 已预装
    # 仅需补充项目特有依赖
    su - ubuntu -c '
      cd /home/ubuntu
      git clone https://github.com/goantigravity-bot/singapore-weather-ai.git weather-ai || true
      cd weather-ai
      python3 -m venv venv
      venv/bin/pip install -q boto3 pandas torch numpy scipy xarray netCDF4
    '
    echo "Setup complete at $(date)"
  EOF

  root_block_device {
    volume_size = var.training_volume_size
    volume_type = "gp3"
    encrypted   = true

    tags = { Name = "${var.project_name}-training-volume" }
  }

  tags = {
    Name = "${var.project_name}-gpu-training"
    Role = "training"
  }
}

# ========== IAM: Download Server → S3 ==========

resource "aws_iam_role" "download_role" {
  name = "${var.project_name}-download-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "download_s3_access" {
  name = "${var.project_name}-download-s3"
  role = aws_iam_role.download_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
      Effect   = "Allow"
      Resource = [aws_s3_bucket.models.arn, "${aws_s3_bucket.models.arn}/*"]
    }]
  })
}

resource "aws_iam_instance_profile" "download_profile" {
  name = "${var.project_name}-download-profile"
  role = aws_iam_role.download_role.name
}

# ========== S3: Models Bucket ==========

resource "aws_s3_bucket" "models" {
  bucket = "${var.project_name}-models-gcc"

  tags = { Name = "${var.project_name}-models" }
}

resource "aws_s3_bucket_public_access_block" "models" {
  bucket = aws_s3_bucket.models.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ========== CloudFront: API Server 代理（HTTPS） ==========

resource "aws_cloudfront_distribution" "api" {
  enabled = true
  comment = "HTTPS proxy for Weather AI API Server"

  origin {
    domain_name = aws_instance.api_server.public_dns
    origin_id   = "api-server"

    custom_origin_config {
      http_port              = 8000
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    # API 需要支持所有 HTTP 方法
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "api-server"

    forwarded_values {
      query_string = true
      headers      = ["Origin", "Access-Control-Request-Headers", "Access-Control-Request-Method"]
      cookies {
        forward = "all"
      }
    }

    # API 响应不缓存
    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = { Name = "${var.project_name}-api-cdn" }
}

# ========== Outputs ==========

output "download_server_id" {
  value = aws_instance.download_server.id
}

output "download_server_ip" {
  value = aws_instance.download_server.public_ip
}

output "models_bucket_name" {
  value = aws_s3_bucket.models.bucket
}

output "ssh_command" {
  value = "ssh ubuntu@${aws_instance.download_server.public_ip}"
}

# ========== IAM: API Server → S3 只读 ==========

resource "aws_iam_role" "api_role" {
  name = "${var.project_name}-api-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "api_s3_readonly" {
  name = "${var.project_name}-api-s3-readonly"
  role = aws_iam_role.api_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ListBucket"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.models.arn
      },
      {
        Sid      = "ReadObjects"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.models.arn}/*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "api_profile" {
  name = "${var.project_name}-api-profile"
  role = aws_iam_role.api_role.name
}

# ========== IAM: Training Server → S3 读写 ==========

resource "aws_iam_role" "training_role" {
  name = "${var.project_name}-training-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "training_s3_readwrite" {
  name = "${var.project_name}-training-s3-readwrite"
  role = aws_iam_role.training_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ListBucket"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.models.arn
      },
      {
        Sid      = "ReadWriteObjects"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.models.arn}/*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "training_profile" {
  name = "${var.project_name}-training-profile"
  role = aws_iam_role.training_role.name
}

# ========== IAM User: jeremy.gan（只读） ==========

resource "aws_iam_user" "jeremy" {
  name = "jeremy.gan"
  tags = { Name = "Jeremy Gan" }
}

resource "aws_iam_user_policy_attachment" "jeremy_readonly" {
  user       = aws_iam_user.jeremy.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# Console 登录需通过 GCC 管理员门户设置（组织 SCP 禁止 API 创建 LoginProfile）

output "api_instance_profile" {
  value = aws_iam_instance_profile.api_profile.name
}

output "training_instance_profile" {
  value = aws_iam_instance_profile.training_profile.name
}

output "api_server_ip" {
  value = aws_eip.api.public_ip
}

output "api_server_id" {
  value = aws_instance.api_server.id
}

output "training_server_ip" {
  value = aws_instance.training_server.public_ip
}

output "training_server_id" {
  value = aws_instance.training_server.id
}

output "ssh_api" {
  value = "ssh ubuntu@${aws_eip.api.public_ip}"
}

output "ssh_training" {
  value = "ssh ubuntu@${aws_instance.training_server.public_ip}"
}

output "api_cloudfront_url" {
  value = "https://${aws_cloudfront_distribution.api.domain_name}"
}
