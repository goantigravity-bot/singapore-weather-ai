#!/bin/bash
# 停止 AWS 服务以避免产生费用

set -e

echo "🛑 停止 AWS 服务"
echo "=================================================="

# 配置
# 配置
API_INSTANCE_ID="i-004dffd96ed716316"
TRAINING_INSTANCE_ID="i-09f62a4b8f3a0a0b1"
FRONTEND_BUCKET="weather-ai-frontend-jinhui-20260126"
MODELS_BUCKET="weather-ai-models-de08370c"
REGION="ap-southeast-1"

echo ""
echo "请选择要执行的操作："
echo "1. 停止所有 EC2 实例 (API + Training)"
echo "2. 终止所有 EC2 实例 (永久删除)"
echo "3. 清空并删除所有 S3 Buckets"
echo "4. 停止所有服务 (EC2 停止 + S3 保留)"
echo "5. 删除所有服务 (EC2 终止 + S3 删除 - 危险!)"
echo ""
read -p "请输入选项 (1-5): " choice

case $choice in
    1)
        echo ""
        echo "📦 停止所有 EC2 实例..."
        echo "API Server: $API_INSTANCE_ID"
        echo "Training Server: $TRAINING_INSTANCE_ID"
        
        read -p "确认停止？(y/n): " confirm
        if [ "$confirm" = "y" ]; then
            aws ec2 stop-instances --instance-ids $API_INSTANCE_ID $TRAINING_INSTANCE_ID --region $REGION
            echo "✅ 实例已停止"
        else
            echo "❌ 操作已取消"
        fi
        ;;
    
    2)
        echo ""
        echo "⚠️  警告：终止所有 EC2 实例将永久删除数据！"
        
        read -p "确认终止？(yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            aws ec2 terminate-instances --instance-ids $API_INSTANCE_ID $TRAINING_INSTANCE_ID --region $REGION
            echo "✅ 实例已终止"
        else
            echo "❌ 操作已取消"
        fi
        ;;
    
    3)
        echo ""
        echo "🗑️  清空并删除所有 S3 Buckets..."
        echo "Frontend: $FRONTEND_BUCKET"
        echo "Models: $MODELS_BUCKET"
        
        read -p "确认删除？(yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            echo "删除 Frontend Bucket..."
            aws s3 rm s3://$FRONTEND_BUCKET --recursive --region $REGION
            aws s3api delete-bucket --bucket $FRONTEND_BUCKET --region $REGION
            
            echo "删除 Models Bucket..."
            aws s3 rm s3://$MODELS_BUCKET --recursive --region $REGION
            aws s3api delete-bucket --bucket $MODELS_BUCKET --region $REGION
            
            echo "✅ Buckets 已删除"
        else
            echo "❌ 操作已取消"
        fi
        ;;
    
    4)
        echo ""
        echo "🛑 停止所有服务（保留数据）..."
        read -p "确认停止 EC2？(y/n): " confirm
        if [ "$confirm" = "y" ]; then
            aws ec2 stop-instances --instance-ids $API_INSTANCE_ID $TRAINING_INSTANCE_ID --region $REGION
            echo "✅ EC2 已停止"
            echo "✅ S3 保留"
        else
            echo "❌ 操作已取消"
        fi
        ;;
    
    5)
        echo ""
        echo "⚠️  DANGER: 删除所有资源！"
        read -p "确认全部删除？(yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            echo "终止 EC2..."
            aws ec2 terminate-instances --instance-ids $API_INSTANCE_ID $TRAINING_INSTANCE_ID --region $REGION
            
            echo "删除 S3..."
            aws s3 rm s3://$FRONTEND_BUCKET --recursive --region $REGION
            aws s3api delete-bucket --bucket $FRONTEND_BUCKET --region $REGION
            aws s3 rm s3://$MODELS_BUCKET --recursive --region $REGION
            aws s3api delete-bucket --bucket $MODELS_BUCKET --region $REGION
            
            echo "✅ 所有资源已清理"
        else
            echo "❌ 操作已取消"
        fi
        ;;
    
    *)
        echo "❌ 无效选项"
        exit 1
        ;;
esac

echo ""
echo "=================================================="
echo "操作完成！"
echo "=================================================="
