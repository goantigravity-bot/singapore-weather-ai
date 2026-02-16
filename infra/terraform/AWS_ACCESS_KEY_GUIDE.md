# 如何获取AWS Access Key

## 📋 前提条件

您需要有一个AWS账号。如果还没有，请先注册：https://aws.amazon.com/

---

## 🔑 获取Access Key步骤

### 方法1: 使用IAM用户（推荐）

#### 步骤1: 登录AWS控制台

访问: https://console.aws.amazon.com/

#### 步骤2: 进入IAM服务

1. 在搜索框输入 "IAM"
2. 点击 "IAM" 服务

或直接访问: https://console.aws.amazon.com/iam/

#### 步骤3: 创建IAM用户

1. 在左侧菜单点击 **"Users"（用户）**
2. 点击 **"Create user"（创建用户）**
3. 输入用户名，例如: `terraform-deploy`
4. 点击 **"Next"（下一步）**

#### 步骤4: 设置权限

**选项A: 使用管理员权限（简单，适合测试）**
1. 选择 **"Attach policies directly"（直接附加策略）**
2. 搜索并勾选 **"AdministratorAccess"**
3. 点击 **"Next"（下一步）**

**选项B: 使用最小权限（推荐，生产环境）**
1. 选择 **"Attach policies directly"**
2. 勾选以下策略：
   - `AmazonEC2FullAccess`
   - `AmazonS3FullAccess`
   - `CloudFrontFullAccess`
   - `AmazonRoute53FullAccess`（如果使用域名）
3. 点击 **"Next"**

#### 步骤5: 审核并创建

1. 检查配置
2. 点击 **"Create user"（创建用户）**

#### 步骤6: 创建Access Key

1. 点击刚创建的用户名
2. 选择 **"Security credentials"（安全凭证）**标签
3. 滚动到 **"Access keys"（访问密钥）**部分
4. 点击 **"Create access key"（创建访问密钥）**
5. 选择用例: **"Command Line Interface (CLI)"**
6. 勾选确认框
7. 点击 **"Next"**
8. （可选）添加描述标签，例如: "Terraform deployment"
9. 点击 **"Create access key"**

#### 步骤7: 保存Access Key

⚠️ **重要**: 这是唯一一次可以查看Secret Access Key的机会！

您将看到：
```
Access key ID: AKIAIOSFODNN7EXAMPLE
Secret access key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

**保存方式**:
1. 点击 **"Download .csv file"（下载.csv文件）**
2. 将文件保存到安全位置
3. 或者复制到密码管理器

---

### 方法2: 使用Root用户（不推荐）

⚠️ **警告**: 不推荐在生产环境使用Root用户凭证

1. 登录AWS控制台
2. 点击右上角的账户名
3. 选择 **"Security credentials"**
4. 滚动到 **"Access keys"**
5. 点击 **"Create access key"**
6. 下载或复制凭证

---

## 🔧 配置AWS CLI

### 方法1: 使用aws configure（推荐）

```bash
aws configure
```

按提示输入：
```
AWS Access Key ID [None]: AKIAIOSFODNN7EXAMPLE
AWS Secret Access Key [None]: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
Default region name [None]: ap-southeast-1
Default output format [None]: json
```

### 方法2: 手动编辑配置文件

创建或编辑 `~/.aws/credentials`:
```ini
[default]
aws_access_key_id = AKIAIOSFODNN7EXAMPLE
aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

创建或编辑 `~/.aws/config`:
```ini
[default]
region = ap-southeast-1
output = json
```

### 方法3: 使用环境变量

```bash
export AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"
export AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
export AWS_DEFAULT_REGION="ap-southeast-1"
```

---

## ✅ 验证配置

### 测试AWS CLI

```bash
# 查看当前用户身份
aws sts get-caller-identity

# 应该返回类似：
# {
#     "UserId": "AIDAI...",
#     "Account": "123456789012",
#     "Arn": "arn:aws:iam::123456789012:user/terraform-deploy"
# }
```

### 测试Terraform

```bash
cd terraform
terraform init
terraform plan
```

如果配置正确，应该能看到Terraform计划输出。

---

## 🔒 安全最佳实践

### 1. 使用IAM用户，不要使用Root用户

❌ **不要**: 使用Root账户的Access Key  
✅ **要**: 创建专门的IAM用户

### 2. 启用MFA（多因素认证）

1. 在IAM用户页面
2. 选择 **"Security credentials"**
3. 点击 **"Assign MFA device"**
4. 使用Google Authenticator或其他MFA应用

### 3. 定期轮换Access Key

建议每90天更换一次Access Key：
1. 创建新的Access Key
2. 更新所有使用旧Key的地方
3. 测试新Key工作正常
4. 删除旧Key

### 4. 使用最小权限原则

只授予必要的权限，不要使用AdministratorAccess（除非必要）。

### 5. 不要提交到Git

确保 `.gitignore` 包含：
```
.aws/
*.pem
*.key
terraform.tfvars
.env*
```

### 6. 使用AWS Secrets Manager（高级）

对于生产环境，考虑使用AWS Secrets Manager存储敏感信息。

---

## 🆘 常见问题

### Q: 忘记了Secret Access Key怎么办？

**A**: Secret Access Key无法找回，只能：
1. 创建新的Access Key
2. 更新配置
3. 删除旧的Access Key

### Q: Access Key泄露了怎么办？

**A**: 立即采取行动：
1. 登录AWS控制台
2. 进入IAM → Users → 选择用户
3. 在"Security credentials"中删除泄露的Key
4. 创建新的Access Key
5. 检查CloudTrail日志查看是否有异常活动

### Q: 如何限制Access Key的权限？

**A**: 
1. 进入IAM → Users → 选择用户
2. 在"Permissions"标签中
3. 移除不需要的策略
4. 只保留必要的权限

### Q: 可以创建多个Access Key吗？

**A**: 可以，每个IAM用户最多可以有2个活跃的Access Key。这样可以实现无缝轮换。

---

## 📱 使用多个AWS账号

如果您有多个AWS账号，可以配置多个profile：

### 配置多个profile

编辑 `~/.aws/credentials`:
```ini
[default]
aws_access_key_id = KEY1
aws_secret_access_key = SECRET1

[work]
aws_access_key_id = KEY2
aws_secret_access_key = SECRET2

[personal]
aws_access_key_id = KEY3
aws_secret_access_key = SECRET3
```

### 使用特定profile

```bash
# AWS CLI
aws s3 ls --profile work

# Terraform
export AWS_PROFILE=work
terraform plan

# 或在terraform.tfvars中
# provider "aws" {
#   profile = "work"
# }
```

---

## 🎓 推荐资源

- [AWS IAM最佳实践](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [AWS CLI配置指南](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html)
- [Terraform AWS Provider文档](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)

---

## ✅ 快速检查清单

完成后检查：
- [ ] 已创建IAM用户
- [ ] 已下载Access Key
- [ ] 已配置AWS CLI (`aws configure`)
- [ ] 已验证配置 (`aws sts get-caller-identity`)
- [ ] 已启用MFA（推荐）
- [ ] Access Key已安全保存
- [ ] 已添加到`.gitignore`

---

**创建时间**: 2026-01-26  
**适用于**: AWS新用户和Terraform部署
