#!/bin/bash
# 基础设施验证脚本
# 使用方法: ./verify-infrastructure.sh

set -e

echo "🔍 开始验证AWS基础设施..."
echo "=================================="

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 切换到terraform目录
cd "$(dirname "$0")/terraform"

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
EC2_IP=$(terraform output -raw ec2_public_ip 2>/dev/null || echo "")
API_URL=$(terraform output -raw api_url 2>/dev/null || echo "")
FRONTEND_URL=$(terraform output -raw frontend_url 2>/dev/null || echo "")
S3_BUCKET=$(terraform output -raw s3_bucket_name 2>/dev/null || echo "")

if [ -z "$EC2_IP" ]; then
    echo -e "${RED}❌ 无法获取Terraform输出，请先运行 terraform apply${NC}"
    exit 1
fi

echo "  EC2 IP: $EC2_IP"
echo "  API URL: $API_URL"
echo "  Frontend URL: $FRONTEND_URL"
echo "  S3 Bucket: $S3_BUCKET"

# 3. 检查EC2实例
echo -e "\n${YELLOW}3. 检查EC2实例...${NC}"
INSTANCE_STATE=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=weather-ai-api-server" \
  --query 'Reservations[0].Instances[0].State.Name' \
  --output text 2>/dev/null || echo "unknown")

if [ "$INSTANCE_STATE" == "running" ]; then
    echo -e "${GREEN}✅ EC2实例运行中${NC}"
else
    echo -e "${RED}❌ EC2实例状态: $INSTANCE_STATE${NC}"
fi

# 4. 测试SSH连接
echo -e "\n${YELLOW}4. 测试SSH连接...${NC}"
if timeout 5 bash -c "echo > /dev/tcp/$EC2_IP/22" 2>/dev/null; then
    echo -e "${GREEN}✅ SSH端口(22)可访问${NC}"
else
    echo -e "${RED}❌ SSH端口(22)不可访问${NC}"
fi

# 5. 测试HTTP端口
echo -e "\n${YELLOW}5. 测试HTTP端口...${NC}"
if timeout 5 bash -c "echo > /dev/tcp/$EC2_IP/80" 2>/dev/null; then
    echo -e "${GREEN}✅ HTTP端口(80)可访问${NC}"
else
    echo -e "${RED}❌ HTTP端口(80)不可访问${NC}"
fi

# 6. 测试API端口
echo -e "\n${YELLOW}6. 测试API端口...${NC}"
if timeout 5 bash -c "echo > /dev/tcp/$EC2_IP/8000" 2>/dev/null; then
    echo -e "${GREEN}✅ API端口(8000)可访问${NC}"
else
    echo -e "${RED}❌ API端口(8000)不可访问${NC}"
fi

# 7. 检查S3存储桶
echo -e "\n${YELLOW}7. 检查S3存储桶...${NC}"
if aws s3 ls "s3://$S3_BUCKET" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ S3存储桶可访问${NC}"
else
    echo -e "${RED}❌ S3存储桶不可访问${NC}"
fi

# 8. 检查CloudFront（如果启用）
echo -e "\n${YELLOW}8. 检查CloudFront...${NC}"
if echo "$FRONTEND_URL" | grep -q cloudfront; then
    CF_DOMAIN=$(echo $FRONTEND_URL | sed 's|https://||')
    HTTP_CODE=$(curl -I -s -o /dev/null -w "%{http_code}" "https://$CF_DOMAIN" 2>/dev/null || echo "000")
    
    if [ "$HTTP_CODE" == "403" ] || [ "$HTTP_CODE" == "404" ]; then
        echo -e "${GREEN}✅ CloudFront可访问（HTTP $HTTP_CODE - 等待部署内容）${NC}"
    elif [ "$HTTP_CODE" == "200" ]; then
        echo -e "${GREEN}✅ CloudFront可访问并已部署内容${NC}"
    else
        echo -e "${RED}❌ CloudFront不可访问（HTTP $HTTP_CODE）${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  CloudFront未启用${NC}"
fi

# 9. 资源统计
echo -e "\n${YELLOW}9. 资源统计...${NC}"
RESOURCE_COUNT=$(terraform state list | wc -l | tr -d ' ')
echo "  创建的资源数量: $RESOURCE_COUNT"

echo -e "\n=================================="
echo -e "${GREEN}🎉 基础设施验证完成！${NC}"
echo "=================================="
echo ""
echo "📋 验证摘要:"
echo "  - EC2实例: $INSTANCE_STATE"
echo "  - 公网IP: $EC2_IP"
echo "  - S3存储桶: $S3_BUCKET"
echo "  - 资源总数: $RESOURCE_COUNT"
echo ""
echo "🚀 下一步:"
echo "  1. SSH连接: ssh -i ~/.ssh/weather-ai-key.pem ubuntu@$EC2_IP"
echo "  2. 部署代码: ./deploy-all.sh"
echo "  3. 访问API: $API_URL/health"
echo "  4. 访问前端: $FRONTEND_URL"
echo ""
