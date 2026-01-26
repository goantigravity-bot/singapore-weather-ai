#!/bin/bash
# 自动更新前端 API 地址并重新部署

set -e

if [ -z "$1" ]; then
    echo "❌ 错误：请提供新的 API IP 地址"
    echo "用法: $0 <NEW_IP>"
    echo "示例: $0 3.0.28.161"
    exit 1
fi

NEW_IP=$1
S3_BUCKET="weather-ai-frontend-jinhui-20260126"
REGION="ap-southeast-1"

echo "🔄 更新前端 API 配置"
echo "=================================================="
echo "新的 API 地址: http://$NEW_IP"
echo ""

# 更新环境变量
echo "📝 更新 .env.production..."
cat > frontend/.env.production << EOF
VITE_API_BASE_URL=http://$NEW_IP
EOF

echo "✅ 环境变量已更新"
echo ""

# 重新构建
echo "🔨 重新构建前端..."
cd frontend
npm run build
cd ..

echo "✅ 构建完成"
echo ""

# 部署到 S3
echo "☁️  部署到 S3..."
aws s3 sync frontend/dist/ s3://$S3_BUCKET --delete --region $REGION

echo ""
echo "=================================================="
echo "✅ 前端更新完成！"
echo "=================================================="
echo ""
echo "🔗 访问地址："
echo "   前端: http://$S3_BUCKET.s3-website-$REGION.amazonaws.com"
echo "   后端: http://$NEW_IP"
echo ""
echo "🧪 测试连接："
echo "   curl http://$NEW_IP/health"
echo ""
echo "=================================================="
