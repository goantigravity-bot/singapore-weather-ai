#!/bin/bash
# 启动 AWS 服务

set -e

echo "🚀 启动 AWS 服务"
echo "=================================================="

# 配置
# 配置
API_INSTANCE_ID="i-004dffd96ed716316"
TRAINING_INSTANCE_ID="i-09f62a4b8f3a0a0b1"
REGION="ap-southeast-1"

echo ""
echo "请选择要执行的操作："
echo "1. 启动所有 EC2 实例 (API + Training)"
echo "2. 仅启动 API Server"
echo "3. 仅启动 Training Server"
echo ""
read -p "请输入选项 (1-3): " choice

start_instances() {
    ids=$1
    name=$2
    echo ""
    echo "📦 启动 $name..."
    aws ec2 start-instances --instance-ids $ids --region $REGION
    
    echo "⏳ 等待启动..."
    aws ec2 wait instance-running --instance-ids $ids --region $REGION
    echo "✅ $name 已启动"
}

get_public_ip() {
    id=$1
    aws ec2 describe-instances \
      --instance-ids $id \
      --region $REGION \
      --query 'Reservations[*].Instances[*].PublicIpAddress' \
      --output text
}

case $choice in
    1)
        start_instances "$API_INSTANCE_ID $TRAINING_INSTANCE_ID" "所有实例"
        API_IP=$(get_public_ip $API_INSTANCE_ID)
        TRAINING_IP=$(get_public_ip $TRAINING_INSTANCE_ID)
        ;;
    2)
        start_instances "$API_INSTANCE_ID" "API Server"
        API_IP=$(get_public_ip $API_INSTANCE_ID)
        ;;
    3)
        start_instances "$TRAINING_INSTANCE_ID" "Training Server"
        TRAINING_IP=$(get_public_ip $TRAINING_INSTANCE_ID)
        ;;
    *)
        echo "❌ 无效选项"
        exit 1
        ;;
esac

echo ""
echo "=================================================="
echo "✅ 服务状态报告"
echo "=================================================="
if [ -n "$API_IP" ]; then
    echo "后端 API Server:"
    echo "  - Public IP: $API_IP"
    echo "  - API URL:   http://$API_IP:8000"
    echo "  - SSH:       ssh -i ~/.ssh/weather-ai-key.pem ubuntu@$API_IP"
fi

if [ -n "$TRAINING_IP" ]; then
    echo ""
    echo "训练服务器 Training Server:"
    echo "  - Public IP: $TRAINING_IP"
    echo "  - SSH:       ssh -i ~/.ssh/weather-ai-key.pem ubuntu@$TRAINING_IP"
fi
echo "=================================================="

if [ -n "$API_IP" ]; then
    echo ""
    echo "⚠️  注意：如果公网 IP 已更改，请更新前端配置："
    echo "   ./update-frontend-api.sh $API_IP"
fi
echo ""
