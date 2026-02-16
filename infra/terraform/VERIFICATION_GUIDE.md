# Terraform资源验证指南

## 🎯 验证目标

确保所有AWS资源已正确创建并可以正常工作。

---

## ✅ 第一步：Terraform验证

### 1. 查看Terraform状态

```bash
cd terraform

# 查看所有创建的资源
terraform show

# 查看资源列表
terraform state list
```

**预期输出**（应该看到这些资源）:
```
aws_cloudfront_distribution.frontend[0]
aws_eip.weather_api[0]
aws_instance.weather_api
aws_key_pair.weather_api
aws_route53_record.api[0]
aws_route53_record.frontend[0]
aws_s3_bucket.frontend
aws_s3_bucket_policy.frontend
aws_s3_bucket_public_access_block.frontend
aws_s3_bucket_website_configuration.frontend
aws_security_group.weather_api
```

### 2. 查看输出值

```bash
# 查看所有输出
terraform output

# 查看特定输出
terraform output ec2_public_ip
terraform output api_url
terraform output frontend_url
```

**示例输出**:
```
ec2_public_ip = "54.123.45.67"
api_url = "http://54.123.45.67:8000"
frontend_url = "https://d1234567890abc.cloudfront.net"
```

### 3. 验证配置一致性

```bash
# 检查配置是否与实际状态一致
terraform plan

# 应该显示: No changes. Your infrastructure matches the configuration.
```

---

## 🌐 第二步：AWS控制台验证

### 1. 验证EC2实例

**访问**: https://console.aws.amazon.com/ec2/

**检查项目**:
- [ ] 实例状态: `running`
- [ ] 实例类型: `t3.medium` (或您配置的类型)
- [ ] 公网IP: 与 `terraform output ec2_public_ip` 一致
- [ ] 安全组: 允许端口 22, 80, 443, 8000
- [ ] 密钥对: `weather-ai-key` 存在

**验证命令**:
```bash
# 使用AWS CLI验证
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=weather-ai-api-server" \
  --query 'Reservations[0].Instances[0].[InstanceId,State.Name,PublicIpAddress,InstanceType]' \
  --output table
```

### 2. 验证弹性IP

**访问**: EC2 → Elastic IPs

**检查项目**:
- [ ] 弹性IP已分配
- [ ] 关联到EC2实例
- [ ] IP地址与输出一致

**验证命令**:
```bash
aws ec2 describe-addresses \
  --filters "Name=tag:Name,Values=weather-ai-eip" \
  --query 'Addresses[0].[PublicIp,InstanceId,AllocationId]' \
  --output table
```

### 3. 验证安全组

**访问**: EC2 → Security Groups

**检查项目**:
- [ ] 入站规则包含:
  - SSH (22) - 您的IP
  - HTTP (80) - 0.0.0.0/0
  - HTTPS (443) - 0.0.0.0/0
  - Custom TCP (8000) - 0.0.0.0/0
- [ ] 出站规则: All traffic allowed

**验证命令**:
```bash
aws ec2 describe-security-groups \
  --filters "Name=tag:Name,Values=weather-ai-api-sg" \
  --query 'SecurityGroups[0].IpPermissions' \
  --output table
```

### 4. 验证S3存储桶

**访问**: https://console.aws.amazon.com/s3/

**检查项目**:
- [ ] 存储桶已创建
- [ ] 存储桶名称正确
- [ ] 静态网站托管已启用
- [ ] 公开访问已配置
- [ ] Bucket策略正确

**验证命令**:
```bash
# 列出存储桶
aws s3 ls

# 检查存储桶配置
aws s3api get-bucket-website \
  --bucket $(terraform output -raw s3_bucket_name)

# 检查公开访问配置
aws s3api get-public-access-block \
  --bucket $(terraform output -raw s3_bucket_name)
```

### 5. 验证CloudFront（如果启用）

**访问**: https://console.aws.amazon.com/cloudfront/

**检查项目**:
- [ ] 分发状态: `Deployed`
- [ ] 域名可访问
- [ ] 源设置正确（指向S3）
- [ ] 默认缓存行为已配置

**验证命令**:
```bash
aws cloudfront list-distributions \
  --query 'DistributionList.Items[?Comment==`weather-ai-cdn`].[Id,DomainName,Status]' \
  --output table
```

### 6. 验证Route 53（如果配置域名）

**访问**: https://console.aws.amazon.com/route53/

**检查项目**:
- [ ] A记录 `api.your-domain.com` → EC2 IP
- [ ] A记录 `your-domain.com` → CloudFront

**验证命令**:
```bash
# 检查DNS记录
dig api.your-domain.com
dig your-domain.com
```

---

## 🧪 第三步：功能测试

### 1. SSH连接测试

```bash
# 获取SSH命令
terraform output ssh_command

# 或手动连接
ssh -i ~/.ssh/weather-ai-key.pem ubuntu@$(terraform output -raw ec2_public_ip)
```

**预期结果**: 成功连接到EC2实例

**如果失败**:
- 检查密钥文件权限: `chmod 400 ~/.ssh/weather-ai-key.pem`
- 检查安全组是否允许您的IP
- 检查实例状态是否为running

### 2. EC2实例健康检查

连接到EC2后，检查：

```bash
# 检查系统信息
uname -a
df -h

# 检查初始化日志
cat /var/log/user-data.log

# 检查项目目录
ls -la /home/ubuntu/weather-ai/
```

### 3. S3网站访问测试

```bash
# 获取S3网站端点
terraform output s3_website_endpoint

# 测试访问（应该返回404或默认页面，因为还没上传文件）
curl -I http://$(terraform output -raw s3_website_endpoint)
```

**预期结果**: HTTP 404（正常，因为还没部署前端）

### 4. CloudFront访问测试

```bash
# 获取CloudFront域名
terraform output cloudfront_domain

# 测试访问
curl -I https://$(terraform output -raw cloudfront_domain)
```

**预期结果**: HTTP 403或404（正常，等待部署）

### 5. 网络连通性测试

```bash
# 测试EC2端口开放情况
EC2_IP=$(terraform output -raw ec2_public_ip)

# 测试SSH端口
nc -zv $EC2_IP 22

# 测试HTTP端口
nc -zv $EC2_IP 80

# 测试API端口
nc -zv $EC2_IP 8000
```

**预期结果**: 所有端口都应该显示 `succeeded` 或 `open`

---

## 📋 第四步：完整验证脚本

创建自动化验证脚本：

```bash
#!/bin/bash
# verify-infrastructure.sh

set -e

echo "🔍 开始验证AWS基础设施..."
echo "=================================="

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

cd terraform

# 1. Terraform状态检查
echo -e "\n${YELLOW}1. 检查Terraform状态...${NC}"
if terraform show > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Terraform状态正常${NC}"
else
    echo -e "${RED}❌ Terraform状态异常${NC}"
    exit 1
fi

# 2. 获取输出值
echo -e "\n${YELLOW}2. 获取资源信息...${NC}"
EC2_IP=$(terraform output -raw ec2_public_ip)
API_URL=$(terraform output -raw api_url)
FRONTEND_URL=$(terraform output -raw frontend_url)
S3_BUCKET=$(terraform output -raw s3_bucket_name)

echo "EC2 IP: $EC2_IP"
echo "API URL: $API_URL"
echo "Frontend URL: $FRONTEND_URL"
echo "S3 Bucket: $S3_BUCKET"

# 3. 检查EC2实例
echo -e "\n${YELLOW}3. 检查EC2实例...${NC}"
INSTANCE_STATE=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=weather-ai-api-server" \
  --query 'Reservations[0].Instances[0].State.Name' \
  --output text)

if [ "$INSTANCE_STATE" == "running" ]; then
    echo -e "${GREEN}✅ EC2实例运行中${NC}"
else
    echo -e "${RED}❌ EC2实例状态: $INSTANCE_STATE${NC}"
fi

# 4. 测试SSH连接
echo -e "\n${YELLOW}4. 测试SSH连接...${NC}"
if nc -zv -w 5 $EC2_IP 22 2>&1 | grep -q succeeded; then
    echo -e "${GREEN}✅ SSH端口可访问${NC}"
else
    echo -e "${RED}❌ SSH端口不可访问${NC}"
fi

# 5. 测试HTTP端口
echo -e "\n${YELLOW}5. 测试HTTP端口...${NC}"
if nc -zv -w 5 $EC2_IP 80 2>&1 | grep -q succeeded; then
    echo -e "${GREEN}✅ HTTP端口可访问${NC}"
else
    echo -e "${RED}❌ HTTP端口不可访问${NC}"
fi

# 6. 测试API端口
echo -e "\n${YELLOW}6. 测试API端口...${NC}"
if nc -zv -w 5 $EC2_IP 8000 2>&1 | grep -q succeeded; then
    echo -e "${GREEN}✅ API端口可访问${NC}"
else
    echo -e "${RED}❌ API端口不可访问${NC}"
fi

# 7. 检查S3存储桶
echo -e "\n${YELLOW}7. 检查S3存储桶...${NC}"
if aws s3 ls s3://$S3_BUCKET > /dev/null 2>&1; then
    echo -e "${GREEN}✅ S3存储桶可访问${NC}"
else
    echo -e "${RED}❌ S3存储桶不可访问${NC}"
fi

# 8. 检查CloudFront（如果启用）
echo -e "\n${YELLOW}8. 检查CloudFront...${NC}"
if echo "$FRONTEND_URL" | grep -q cloudfront; then
    CF_DOMAIN=$(echo $FRONTEND_URL | sed 's|https://||')
    if curl -I -s -o /dev/null -w "%{http_code}" https://$CF_DOMAIN | grep -q "403\|404"; then
        echo -e "${GREEN}✅ CloudFront可访问（等待部署内容）${NC}"
    else
        echo -e "${RED}❌ CloudFront不可访问${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  CloudFront未启用${NC}"
fi

echo -e "\n=================================="
echo -e "${GREEN}🎉 基础设施验证完成！${NC}"
echo "=================================="
echo ""
echo "下一步："
echo "1. 部署后端代码到EC2"
echo "2. 部署前端文件到S3"
echo "3. 测试完整功能"
echo ""
```

**使用方法**:
```bash
chmod +x verify-infrastructure.sh
./verify-infrastructure.sh
```

---

## 🔍 第五步：详细检查清单

### EC2实例检查清单
- [ ] 实例ID存在
- [ ] 状态为 `running`
- [ ] 公网IP已分配
- [ ] 弹性IP已关联（如果启用）
- [ ] 安全组规则正确
- [ ] SSH密钥对已创建
- [ ] 可以SSH连接
- [ ] User data脚本已执行
- [ ] 磁盘空间充足（20GB）

### S3存储桶检查清单
- [ ] 存储桶已创建
- [ ] 存储桶名称唯一
- [ ] 静态网站托管已启用
- [ ] 索引文档设置为 `index.html`
- [ ] 错误文档设置为 `index.html`
- [ ] 公开访问已配置
- [ ] Bucket策略正确
- [ ] 可以通过网站端点访问

### CloudFront检查清单（如果启用）
- [ ] 分发已创建
- [ ] 状态为 `Deployed`
- [ ] 源设置指向S3
- [ ] 默认缓存行为已配置
- [ ] 自定义错误响应已配置
- [ ] HTTPS重定向已启用
- [ ] 可以通过CloudFront域名访问

### 网络检查清单
- [ ] 端口22可访问（SSH）
- [ ] 端口80可访问（HTTP）
- [ ] 端口443可访问（HTTPS）
- [ ] 端口8000可访问（API）
- [ ] 安全组规则正确
- [ ] VPC配置正确

### DNS检查清单（如果配置域名）
- [ ] Route 53托管区域存在
- [ ] A记录 `api.domain.com` 指向EC2
- [ ] A记录 `domain.com` 指向CloudFront
- [ ] DNS解析正常
- [ ] TTL设置合理

---

## 🆘 常见问题排查

### 问题1: EC2实例无法SSH连接

**可能原因**:
1. 安全组未允许您的IP
2. 密钥文件权限不正确
3. 实例未完全启动

**解决方法**:
```bash
# 检查安全组
aws ec2 describe-security-groups \
  --group-ids $(terraform output -raw security_group_id)

# 修复密钥权限
chmod 400 ~/.ssh/weather-ai-key.pem

# 检查实例状态
aws ec2 describe-instance-status \
  --instance-ids $(terraform output -raw ec2_instance_id)
```

### 问题2: S3网站无法访问

**可能原因**:
1. 公开访问被阻止
2. Bucket策略不正确
3. 静态网站托管未启用

**解决方法**:
```bash
# 检查公开访问设置
aws s3api get-public-access-block \
  --bucket $(terraform output -raw s3_bucket_name)

# 检查Bucket策略
aws s3api get-bucket-policy \
  --bucket $(terraform output -raw s3_bucket_name)
```

### 问题3: CloudFront返回403

**可能原因**:
1. S3源配置不正确
2. 还没有上传文件
3. 分发未完全部署

**解决方法**:
```bash
# 检查分发状态
aws cloudfront get-distribution \
  --id $(terraform output -raw cloudfront_distribution_id) \
  --query 'Distribution.Status'

# 等待部署完成（可能需要10-15分钟）
```

---

## ✅ 验证成功标准

所有检查项都应该通过：
- ✅ Terraform状态一致
- ✅ EC2实例运行中
- ✅ SSH可以连接
- ✅ 所有端口可访问
- ✅ S3存储桶已创建
- ✅ CloudFront已部署（如果启用）
- ✅ DNS解析正常（如果配置）

**下一步**: 部署应用代码
```bash
./deploy-all.sh
```

---

**创建时间**: 2026-01-26  
**适用于**: Terraform部署后的资源验证
