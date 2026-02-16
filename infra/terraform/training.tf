# training.tf
# Resources for the Training Server

# ========== S3 Bucket for Models ==========
resource "aws_s3_bucket" "models" {
  bucket = "${var.project_name}-models-${random_id.bucket_suffix.hex}"
  tags = {
    Name = "${var.project_name}-models"
  }
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# ========== IAM Role for Training Server ==========
resource "aws_iam_role" "training_role" {
  name = "${var.project_name}-training-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "training_s3_access" {
  name = "${var.project_name}-training-s3-access"
  role = aws_iam_role.training_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Effect   = "Allow"
        Resource = [
          aws_s3_bucket.models.arn,
          "${aws_s3_bucket.models.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_instance_profile" "training_profile" {
  name = "${var.project_name}-training-profile"
  role = aws_iam_role.training_role.name
}

# ========== Security Group for Training Server ==========
resource "aws_security_group" "training_sg" {
  name        = "${var.project_name}-training-sg"
  description = "Security group for Training Server"
  vpc_id      = data.aws_vpc.default.id

  # SSH access (Restrict to your IP in production!)
  ingress {
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
  
  tags = {
    Name = "${var.project_name}-training-sg"
  }
}

# ========== EC2 Instance ==========
resource "aws_instance" "training_server" {
  # Deep Learning AMI with NVIDIA drivers pre-installed (PyTorch 2.9, Ubuntu 24.04)
  ami           = "ami-081296c6e1ebbba80"
  instance_type = "g4dn.xlarge"  # Tesla T4 GPU, 4 vCPU, 16GB RAM
  key_name      = aws_key_pair.weather_api.key_name
  
  vpc_security_group_ids = [aws_security_group.training_sg.id]
  iam_instance_profile   = aws_iam_instance_profile.training_profile.name

  # Spot Instance — 比 On-Demand 便宜 ~60%
  instance_market_options {
    market_type = "spot"
    spot_options {
      spot_instance_type = "one-time"
    }
  }

  root_block_device {
    volume_size = 200  # 容纳卫星原始 .nc 和预处理 .npy
    volume_type = "gp3"
    encrypted   = true
    tags = {
      Name = "${var.project_name}-training-root-volume"
    }
  }

  tags = {
    Name = "${var.project_name}-gpu-training"
    Role = "training"
  }
}

# ========== Outputs ==========
output "training_server_ip" {
  value = aws_instance.training_server.public_ip
}

output "models_bucket_name" {
  value = aws_s3_bucket.models.bucket
}

output "training_server_id" {
  value = aws_instance.training_server.id
}
