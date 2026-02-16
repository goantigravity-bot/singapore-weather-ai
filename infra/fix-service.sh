#!/bin/bash
# 快速修复脚本 - 创建systemd服务

set -e

echo "🔧 创建weather-api systemd服务..."

# 从Terraform获取EC2 IP
cd terraform
EC2_IP=$(terraform output -raw ec2_public_ip 2>/dev/null)
cd ..

if [ -z "$EC2_IP" ]; then
    echo "❌ 无法获取EC2 IP"
    exit 1
fi

echo "EC2 IP: $EC2_IP"

# SSH到EC2并创建服务文件
ssh -i ~/.ssh/id_rsa ubuntu@$EC2_IP << 'ENDSSH'
    echo "创建systemd服务文件..."
    
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
    
    echo "重新加载systemd..."
    sudo systemctl daemon-reload
    
    echo "启用服务..."
    sudo systemctl enable weather-api
    
    echo "启动服务..."
    sudo systemctl start weather-api
    
    sleep 3
    
    echo "检查服务状态..."
    sudo systemctl status weather-api --no-pager
ENDSSH

echo ""
echo "✅ 服务创建完成！"
echo ""
echo "测试API:"
echo "  curl http://$EC2_IP:8000/health"
