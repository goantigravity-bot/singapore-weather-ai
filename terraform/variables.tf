# Terraform变量定义

variable "aws_region" {
  description = "AWS区域"
  type        = string
  default     = "ap-southeast-1"
}

variable "environment" {
  description = "环境名称"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "项目名称"
  type        = string
  default     = "weather-ai"
}

# ========== EC2配置 ==========

variable "instance_type" {
  description = "EC2实例类型"
  type        = string
  default     = "t3.medium"
  
  validation {
    condition     = contains(["t3.small", "t3.medium", "t3.large"], var.instance_type)
    error_message = "实例类型必须是 t3.small, t3.medium 或 t3.large"
  }
}

variable "root_volume_size" {
  description = "根卷大小（GB）"
  type        = number
  default     = 20
}

variable "ssh_public_key_path" {
  description = "SSH公钥文件路径"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

variable "ssh_allowed_ips" {
  description = "允许SSH访问的IP地址列表（CIDR格式）"
  type        = list(string)
  default     = ["0.0.0.0/0"]  # 生产环境应限制为特定IP
}

variable "use_elastic_ip" {
  description = "是否使用弹性IP（固定IP地址）"
  type        = bool
  default     = true
}

# ========== S3和CloudFront配置 ==========

variable "frontend_bucket_name" {
  description = "前端S3存储桶名称（必须全局唯一）"
  type        = string
  
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]*[a-z0-9]$", var.frontend_bucket_name))
    error_message = "存储桶名称只能包含小写字母、数字和连字符"
  }
}

variable "enable_cloudfront" {
  description = "是否启用CloudFront CDN"
  type        = bool
  default     = true
}

# ========== 域名配置 ==========

variable "domain_name" {
  description = "域名（留空则不配置DNS）"
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  description = "Route 53托管区域ID（如果使用域名）"
  type        = string
  default     = ""
}
