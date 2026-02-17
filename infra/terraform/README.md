# Terraform AWS基础设施部署指南

## 📋 前提条件

1. **安装Terraform**
```bash
# macOS
brew install terraform

# 验证安装
terraform version
```

2. **配置AWS凭证**
```bash
# 安装AWS CLI
brew install awscli

# 配置凭证
aws configure
# 输入：
# - AWS Access Key ID
# - AWS Secret Access Key  
# - Default region: ap-southeast-1
# - Default output format: json
```

3. **生成SSH密钥对**（如果还没有）
```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa
```

---

## 🚀 快速开始

### 步骤1: 配置变量

```bash
cd terraform

# 复制配置示例
cp terraform.tfvars.example terraform.tfvars

# 编辑配置文件
nano terraform.tfvars
```

**必须修改的配置**:
- `frontend_bucket_name`: 改为全局唯一的名称（如 `weather-ai-frontend-yourname-12345`）
- `ssh_allowed_ips`: 生产环境应改为您的IP地址

### 步骤2: 初始化Terraform

```bash
terraform init
```

这将下载所需的AWS提供商插件。

### 步骤3: 预览变更

```bash
terraform plan
```

查看Terraform将创建的资源。

### 步骤4: 应用配置

```bash
terraform apply
```

输入 `yes` 确认创建资源。

**预计时间**: 3-5分钟

### 步骤5: 查看输出

```bash
terraform output
```

您将看到：
- EC2公网IP
- SSH连接命令
- API URL
- 前端URL
- S3 Bucket名称
- CloudFront域名

---

## 📊 创建的资源

### AWS资源清单

| 资源类型 | 数量 | 用途 |
|---------|------|------|
| EC2实例 | 1 | 运行后端API和训练 |
| 弹性IP | 1 | 固定公网IP地址 |
| 安全组 | 1 | 防火墙规则 |
| SSH密钥对 | 1 | SSH访问 |
| S3存储桶 | 1 | 托管前端静态文件 |
| CloudFront分发 | 1 | CDN加速（可选） |
| Route 53记录 | 2 | DNS解析（如果配置域名） |

### 成本估算

**基础配置** (t3.medium + S3 + CloudFront):
- EC2: ~$30/月
- EBS: ~$2/月
- S3: ~$0.02/月
- CloudFront: ~$1/月
- **总计**: ~$33/月

**节省成本** (t3.small):
- EC2: ~$15/月
- **总计**: ~$18/月

---

## 🔧 常用命令

### 查看当前状态
```bash
terraform show
```

### 查看特定输出
```bash
terraform output ec2_public_ip
terraform output api_url
terraform output frontend_url
```

### 更新基础设施
```bash
# 修改 terraform.tfvars 后
terraform plan
terraform apply
```

### 销毁资源
```bash
terraform destroy
```

⚠️ **警告**: 这将删除所有资源，包括数据！

---

## 📝 配置选项详解

### 实例类型选择

| 类型 | vCPU | 内存 | 适用场景 | 成本 |
|------|------|------|----------|------|
| t3.small | 2 | 2 GB | 轻量级，测试 | ~$15/月 |
| t3.medium | 2 | 4 GB | API 服务器，推荐 | ~$30/月 |
| t3.large | 2 | 8 GB | 高负载 API | ~$60/月 |
| t3.xlarge | 4 | 16 GB | **下载服务器**（8 workers satpy） | ~$120/月 |

### CloudFront配置

**启用CloudFront的优势**:
- ✅ 全球CDN加速
- ✅ HTTPS支持
- ✅ 降低S3成本
- ✅ 提升用户体验

**禁用CloudFront**:
- 成本更低（省$1/月）
- 配置更简单
- 适合内部使用

设置 `enable_cloudfront = false` 来禁用。

### 域名配置

如果您有域名，可以配置自定义域名：

1. 在Route 53创建托管区域
2. 获取Zone ID
3. 在 `terraform.tfvars` 中配置：
```hcl
domain_name     = "example.com"
route53_zone_id = "Z1234567890ABC"
```

Terraform将自动创建：
- `api.example.com` → EC2
- `example.com` → CloudFront

---

## 🔒 安全最佳实践

### 1. 限制SSH访问

**不推荐**（开发环境）:
```hcl
ssh_allowed_ips = ["0.0.0.0/0"]
```

**推荐**（生产环境）:
```hcl
ssh_allowed_ips = ["YOUR_IP/32"]
```

获取您的IP:
```bash
curl ifconfig.me
```

### 2. 使用密钥管理

不要在代码中硬编码敏感信息。使用AWS Secrets Manager或环境变量。

### 3. 启用加密

Terraform配置已默认启用：
- ✅ EBS卷加密
- ✅ S3传输加密

### 4. 定期更新

```bash
# 更新Terraform
brew upgrade terraform

# 更新AWS提供商
terraform init -upgrade
```

---

## 🆘 故障排查

### 问题1: Bucket名称已存在

**错误**: `BucketAlreadyExists`

**解决**: S3 bucket名称必须全局唯一，修改 `frontend_bucket_name`

### 问题2: SSH密钥不存在

**错误**: `file: no such file or directory`

**解决**: 
```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa
```

### 问题3: AWS凭证无效

**错误**: `Error: error configuring Terraform AWS Provider`

**解决**:
```bash
aws configure
# 重新输入凭证
```

### 问题4: 资源已存在

**错误**: `AlreadyExists`

**解决**:
```bash
# 导入现有资源
terraform import aws_instance.weather_api i-1234567890abcdef0

# 或删除现有资源
terraform destroy
```

---

## 📦 部署后步骤

### 1. 连接到EC2

```bash
# 使用Terraform输出的命令
terraform output ssh_command

# 或手动连接
ssh -i ~/.ssh/id_rsa ubuntu@$(terraform output -raw ec2_public_ip)
```

### 2. 部署代码

```bash
# 在本地机器执行
./deploy-all.sh
```

### 3. 验证部署

```bash
# 测试API
curl $(terraform output -raw api_url)/health

# 访问前端
open $(terraform output -raw frontend_url)
```

---

## 🔄 更新和维护

### 修改实例类型

```hcl
# terraform.tfvars
instance_type = "t3.small"  # 降低成本
```

```bash
terraform apply
```

### 增加存储空间

```hcl
# terraform.tfvars
root_volume_size = 30  # 从20GB增加到30GB
```

```bash
terraform apply
```

### 启用/禁用CloudFront

```hcl
# terraform.tfvars
enable_cloudfront = false  # 禁用CDN
```

```bash
terraform apply
```

---

## 📚 进阶配置

### 使用Terraform工作区

```bash
# 创建开发环境
terraform workspace new dev
terraform apply -var="environment=dev"

# 创建生产环境
terraform workspace new prod
terraform apply -var="environment=prod"

# 切换环境
terraform workspace select dev
```

### 远程状态存储

创建 `backend.tf`:
```hcl
terraform {
  backend "s3" {
    bucket = "your-terraform-state-bucket"
    key    = "weather-ai/terraform.tfstate"
    region = "ap-southeast-1"
  }
}
```

### 使用模块

将配置拆分为可重用的模块，便于管理多个环境。

---

## ✅ 检查清单

部署前检查：
- [ ] AWS凭证已配置
- [ ] SSH密钥已生成
- [ ] `terraform.tfvars` 已配置
- [ ] S3 bucket名称全局唯一
- [ ] 已运行 `terraform plan` 预览

部署后检查：
- [ ] EC2实例运行正常
- [ ] 可以SSH连接
- [ ] API健康检查通过
- [ ] S3 bucket已创建
- [ ] CloudFront分发已启用（如果配置）
- [ ] 域名解析正常（如果配置）

---

## 📞 获取帮助

### Terraform文档
- [AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Terraform CLI](https://www.terraform.io/docs/cli/index.html)

### 常用资源
- [Terraform Best Practices](https://www.terraform-best-practices.com/)
- [AWS Well-Architected](https://aws.amazon.com/architecture/well-architected/)

---

**创建时间**: 2026-01-26  
**Terraform版本**: >= 1.0  
**AWS Provider版本**: ~> 5.0
