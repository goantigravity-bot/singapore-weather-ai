#!/bin/bash
# 停止 AWS 服务以避免产生费用

set -e

echo "🛑 停止 AWS 服务"
echo "=================================================="

# 配置
EC2_INSTANCE_ID="i-004dffd96ed716316"  # 你的实例 ID
S3_BUCKET="weather-ai-frontend-jinhui-20260126"
REGION="ap-southeast-1"

echo ""
echo "请选择要执行的操作："
echo "1. 停止 EC2 实例（保留实例，停止计费）"
echo "2. 终止 EC2 实例（永久删除，完全停止计费）"
echo "3. 清空并删除 S3 Bucket"
echo "4. 停止所有服务（EC2 停止 + S3 保留）"
echo "5. 删除所有服务（EC2 终止 + S3 删除）"
echo ""
read -p "请输入选项 (1-5): " choice

case $choice in
    1)
        echo ""
        echo "📦 停止 EC2 实例..."
        echo "实例 ID: $EC2_INSTANCE_ID"
        echo ""
        read -p "确认停止 EC2 实例？(y/n): " confirm
        if [ "$confirm" = "y" ]; then
            aws ec2 stop-instances --instance-ids $EC2_INSTANCE_ID --region $REGION
            echo "✅ EC2 实例已停止"
            echo "💡 提示：实例已停止但未删除，仍会产生少量 EBS 存储费用"
            echo "💡 重新启动：aws ec2 start-instances --instance-ids $EC2_INSTANCE_ID --region $REGION"
        else
            echo "❌ 操作已取消"
        fi
        ;;
    
    2)
        echo ""
        echo "⚠️  警告：终止 EC2 实例将永久删除实例！"
        echo "实例 ID: $EC2_INSTANCE_ID"
        echo ""
        read -p "确认终止 EC2 实例？(yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            aws ec2 terminate-instances --instance-ids $EC2_INSTANCE_ID --region $REGION
            echo "✅ EC2 实例已终止"
            echo "💡 提示：实例已永久删除，无法恢复"
        else
            echo "❌ 操作已取消"
        fi
        ;;
    
    3)
        echo ""
        echo "🗑️  清空并删除 S3 Bucket..."
        echo "Bucket: $S3_BUCKET"
        echo ""
        read -p "确认删除 S3 Bucket 及所有内容？(yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            echo "清空 Bucket..."
            aws s3 rm s3://$S3_BUCKET --recursive --region $REGION
            echo "删除 Bucket..."
            aws s3api delete-bucket --bucket $S3_BUCKET --region $REGION
            echo "✅ S3 Bucket 已删除"
        else
            echo "❌ 操作已取消"
        fi
        ;;
    
    4)
        echo ""
        echo "🛑 停止所有服务（保留数据）..."
        echo ""
        read -p "确认停止 EC2 实例？(y/n): " confirm
        if [ "$confirm" = "y" ]; then
            aws ec2 stop-instances --instance-ids $EC2_INSTANCE_ID --region $REGION
            echo "✅ EC2 实例已停止"
            echo "✅ S3 Bucket 保留（静态文件托管无运行费用）"
            echo ""
            echo "💰 费用说明："
            echo "   - EC2: 已停止，仅产生少量 EBS 存储费用"
            echo "   - S3: 仅按存储和流量计费"
        else
            echo "❌ 操作已取消"
        fi
        ;;
    
    5)
        echo ""
        echo "⚠️  警告：这将删除所有 AWS 资源！"
        echo "   - EC2 实例将被终止（永久删除）"
        echo "   - S3 Bucket 将被删除（包括所有文件）"
        echo ""
        read -p "确认删除所有服务？(yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            echo ""
            echo "终止 EC2 实例..."
            aws ec2 terminate-instances --instance-ids $EC2_INSTANCE_ID --region $REGION
            echo "✅ EC2 实例已终止"
            
            echo ""
            echo "删除 S3 Bucket..."
            aws s3 rm s3://$S3_BUCKET --recursive --region $REGION
            aws s3api delete-bucket --bucket $S3_BUCKET --region $REGION
            echo "✅ S3 Bucket 已删除"
            
            echo ""
            echo "✅ 所有服务已删除"
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
