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
      Project     = "Singapore Weather AI"
      Environment = var.environment
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

  root_block_device {
    volume_size = var.download_volume_size
    volume_type = "gp3"
    encrypted   = true

    tags = { Name = "${var.project_name}-download-volume" }
  }

  tags = { Name = "${var.project_name}-download-server" }
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
