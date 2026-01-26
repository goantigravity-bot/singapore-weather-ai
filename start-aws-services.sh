#!/bin/bash
# 启动 AWS 服务

set -e

echo "🚀 启动 AWS 服务"
echo "=================================================="

# 配置
EC2_INSTANCE_ID="i-004dffd96ed716316"
REGION="ap-southeast-1"

echo ""
echo "📦 启动 EC2 实例..."
echo "实例 ID: $EC2_INSTANCE_ID"
echo ""

# 启动实例
aws ec2 start-instances --instance-ids $EC2_INSTANCE_ID --region $REGION

echo ""
echo "⏳ 等待实例启动..."
aws ec2 wait instance-running --instance-ids $EC2_INSTANCE_ID --region $REGION

echo ""
echo "✅ EC2 实例已启动！"
echo ""

# 获取新的公网 IP
NEW_IP=$(aws ec2 describe-instances \
  --instance-ids $EC2_INSTANCE_ID \
  --region $REGION \
  --query 'Reservations[*].Instances[*].PublicIpAddress' \
  --output text)

echo "=================================================="
echo "✅ 服务启动成功！"
echo "=================================================="
echo ""
echo "📍 新的公网 IP: $NEW_IP"
echo ""
echo "⚠️  重要提示："
echo "   公网 IP 已改变！需要更新前端配置："
echo ""
echo "   1. 更新前端环境变量："
echo "      编辑 frontend/.env.production"
echo "      VITE_API_BASE_URL=http://$NEW_IP"
echo ""
echo "   2. 重新构建并部署前端："
echo "      cd frontend"
echo "      npm run build"
echo "      aws s3 sync dist/ s3://weather-ai-frontend-jinhui-20260126 --delete"
echo ""
echo "   或者运行一键更新脚本："
echo "      ./update-frontend-api.sh $NEW_IP"
echo ""
echo "🔗 访问地址："
echo "   后端 API: http://$NEW_IP"
echo "   API 文档: http://$NEW_IP/docs"
echo "   健康检查: http://$NEW_IP/health"
echo ""
echo "=================================================="
