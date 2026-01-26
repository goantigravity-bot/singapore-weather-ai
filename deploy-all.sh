#!/bin/bash
# 前后端一键部署脚本
# 使用方法: ./deploy-all.sh

set -e

echo "🚀 新加坡天气AI - 完整部署脚本"
echo "=================================="

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 配置检查
echo -e "${YELLOW}📋 检查配置...${NC}"

# 检查deploy-config.sh是否存在
if [ ! -f "deploy-config.sh" ]; then
    echo -e "${YELLOW}⚠️  deploy-config.sh 不存在，使用默认配置${NC}"
    # 从Terraform输出生成配置
    cd terraform
    EC2_IP=$(terraform output -raw ec2_public_ip 2>/dev/null || echo "")
    S3_BUCKET=$(terraform output -raw s3_bucket_name 2>/dev/null || echo "")
    CLOUDFRONT_ID=$(terraform output -raw cloudfront_distribution_id 2>/dev/null || echo "")
    cd ..
    
    if [ -z "$EC2_IP" ]; then
        echo -e "${RED}❌ 无法获取Terraform输出，请先运行 terraform apply${NC}"
        exit 1
    fi
    
    # 创建临时配置
    cat > deploy-config.sh << EOF
EC2_IP="$EC2_IP"
EC2_HOST="ubuntu@\${EC2_IP}"
EC2_KEY="~/.ssh/weather-ai-key.pem"
REMOTE_DIR="/home/ubuntu/weather-ai"
S3_BUCKET="$S3_BUCKET"
CLOUDFRONT_ID="$CLOUDFRONT_ID"
FRONTEND_URL="https://\$(cd terraform && terraform output -raw cloudfront_domain)"
AWS_REGION="ap-southeast-1"
EOF
fi

# 加载配置
source deploy-config.sh

echo -e "${GREEN}✅ 配置检查通过${NC}"

# 询问部署选项
echo ""
echo "请选择部署内容:"
echo "1) 仅后端"
echo "2) 仅前端"
echo "3) 前端 + 后端（完整部署）"
read -p "请输入选项 (1-3): " DEPLOY_OPTION

# 部署后端
deploy_backend() {
    echo ""
    echo -e "${YELLOW}🔧 开始部署后端...${NC}"
    
    # 1. 上传代码
    echo "📦 上传代码到EC2..."
    rsync -avz --exclude 'node_modules' --exclude 'frontend/node_modules' --exclude 'frontend/dist' \
      --exclude '.git' --exclude 'satellite_data' --exclude '*.log' \
      -e "ssh -i $EC2_KEY" \
      ./ $EC2_HOST:$REMOTE_DIR/
    
    # 2. 上传环境变量
    echo "🔐 上传环境变量..."
    scp -i $EC2_KEY .env.production $EC2_HOST:$REMOTE_DIR/.env
    
    # 3. 安装依赖并重启服务
    echo "🔄 安装依赖并配置服务..."
    ssh -i $EC2_KEY $EC2_HOST << 'ENDSSH'
        cd /home/ubuntu/weather-ai
        source venv/bin/activate
        pip install -r requirements.txt
        
        # 创建systemd服务文件
        sudo tee /etc/systemd/system/weather-api.service > /dev/null << 'EOF'
[Unit]
Description=Weather AI API Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/weather-ai
Environment="PATH=/home/ubuntu/weather-ai/venv/bin"
EnvironmentFile=-/home/ubuntu/weather-ai/.env
ExecStart=/home/ubuntu/weather-ai/venv/bin/python3 /home/ubuntu/weather-ai/api.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
        
        # 重新加载systemd并启动服务
        sudo systemctl daemon-reload
        sudo systemctl enable weather-api
        sudo systemctl restart weather-api
        sleep 3
        sudo systemctl status weather-api --no-pager
ENDSSH
    
    # 4. 测试API
    echo "🧪 测试API..."
    sleep 2
    HEALTH_CHECK=$(curl -s http://$EC2_IP:8000/health || echo "failed")
    
    if [[ $HEALTH_CHECK == *"ok"* ]]; then
        echo -e "${GREEN}✅ 后端部署成功！${NC}"
        echo "API地址: http://$EC2_IP:8000"
    else
        echo -e "${RED}❌ 后端健康检查失败${NC}"
        exit 1
    fi
}

# 部署前端
deploy_frontend() {
    echo ""
    echo -e "${YELLOW}🎨 开始部署前端...${NC}"
    
    # 1. 构建前端
    echo "🔨 构建前端..."
    cd frontend
    
    # 创建生产环境变量
    echo "VITE_API_URL=http://$EC2_IP:8000" > .env.production
    
    npm install
    npm run build
    
    if [ ! -d "dist" ]; then
        echo -e "${RED}❌ 构建失败: dist目录不存在${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ 前端构建完成${NC}"
    
    # 2. 上传到S3
    if [ -n "$S3_BUCKET" ]; then
        echo "📤 上传到S3..."
        aws s3 sync dist/ s3://$S3_BUCKET/ --delete
        
        # 3. 清除CloudFront缓存
        if [ -n "$CLOUDFRONT_ID" ]; then
            echo "🔄 清除CDN缓存..."
            aws cloudfront create-invalidation \
              --distribution-id $CLOUDFRONT_ID \
              --paths "/*" > /dev/null
        fi
        
        echo -e "${GREEN}✅ 前端部署到S3成功！${NC}"
        if [ -n "$FRONTEND_URL" ]; then
            echo "访问地址: $FRONTEND_URL"
        fi
    else
        # 如果没有S3，上传到EC2
        echo "📤 上传到EC2..."
        cd ..
        scp -i $EC2_KEY -r frontend/dist $EC2_HOST:$REMOTE_DIR/frontend/
        
        echo -e "${GREEN}✅ 前端部署到EC2成功！${NC}"
        echo "访问地址: http://$EC2_IP (需要配置Nginx)"
    fi
    
    cd ..
}

# 执行部署
case $DEPLOY_OPTION in
    1)
        deploy_backend
        ;;
    2)
        deploy_frontend
        ;;
    3)
        deploy_backend
        deploy_frontend
        ;;
    *)
        echo -e "${RED}❌ 无效的选项${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}=================================="
echo "🎉 部署完成！"
echo "==================================${NC}"
echo ""
echo "📝 部署信息:"
echo "  后端API: http://$EC2_IP:8000"
if [ -n "$FRONTEND_URL" ]; then
    echo "  前端地址: $FRONTEND_URL"
else
    echo "  前端地址: http://$EC2_IP"
fi
echo ""
echo "🧪 快速测试:"
echo "  curl http://$EC2_IP:8000/health"
echo ""
