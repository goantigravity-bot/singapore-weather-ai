#!/bin/bash
# 修复Mixed Content问题 - 配置Nginx反向代理

set -e

echo "🔧 修复Mixed Content问题..."
echo "=================================="

EC2_IP="3.0.28.161"

# 1. 在EC2上配置Nginx
echo "📦 在EC2上安装和配置Nginx..."

ssh -i ~/.ssh/id_rsa ubuntu@$EC2_IP << 'ENDSSH'
    echo "安装Nginx..."
    sudo apt update
    sudo apt install -y nginx
    
    echo "创建Nginx配置..."
    sudo tee /etc/nginx/sites-available/weather-api > /dev/null << 'NGINX_EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # CORS headers
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization' always;
        add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range' always;
        
        if ($request_method = 'OPTIONS') {
            return 204;
        }
    }
}
NGINX_EOF
    
    echo "启用配置..."
    sudo ln -sf /etc/nginx/sites-available/weather-api /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
    
    echo "测试Nginx配置..."
    sudo nginx -t
    
    echo "重启Nginx..."
    sudo systemctl restart nginx
    sudo systemctl enable nginx
    
    echo "检查Nginx状态..."
    sudo systemctl status nginx --no-pager
ENDSSH

echo ""
echo "✅ Nginx配置完成！"
echo ""
echo "现在API可以通过以下方式访问:"
echo "  - 直接: http://$EC2_IP"
echo "  - 原端口: http://$EC2_IP:8000"
echo ""
echo "测试:"
echo "  curl http://$EC2_IP/health"
echo ""

# 2. 测试Nginx
echo "🧪 测试Nginx反向代理..."
sleep 2
HEALTH=$(curl -s http://$EC2_IP/health || echo "failed")

if [[ $HEALTH == *"ok"* ]]; then
    echo "✅ Nginx反向代理工作正常！"
else
    echo "❌ Nginx测试失败，请检查配置"
    exit 1
fi

echo ""
echo "=================================="
echo "🎉 修复完成！"
echo "=================================="
echo ""
echo "下一步:"
echo "1. 前端现在可以正常调用API了"
echo "2. 访问: https://d1em23i2wkbin3.cloudfront.net"
echo "3. 或使用S3 HTTP端点测试:"
echo "   http://weather-ai-frontend-jinhui-20260126.s3-website-ap-southeast-1.amazonaws.com"
echo ""
