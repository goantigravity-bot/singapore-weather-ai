#!/bin/bash
# 修复 CORS 重复头部问题

set -e

echo "🔧 修复 CORS 配置..."
echo "=================================="

EC2_IP="3.0.28.161"

echo "📝 更新 Nginx 配置（移除 CORS 头部，让 FastAPI 处理）..."

ssh -i ~/.ssh/id_rsa ubuntu@$EC2_IP << 'ENDSSH'
    echo "创建新的 Nginx 配置..."
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
        
        # 不添加 CORS 头部 - 让 FastAPI 处理
    }
}
NGINX_EOF
    
    echo "测试 Nginx 配置..."
    sudo nginx -t
    
    echo "重启 Nginx..."
    sudo systemctl restart nginx
    
    echo "检查 Nginx 状态..."
    sudo systemctl status nginx --no-pager
ENDSSH

echo ""
echo "✅ Nginx 配置已更新！"
echo ""
echo "测试 CORS..."
sleep 2

# 测试 API 并检查 CORS 头部
echo "检查 CORS 头部..."
curl -I http://$EC2_IP/health

echo ""
echo "=================================="
echo "🎉 修复完成！"
echo "=================================="
echo ""
echo "现在可以通过 S3 HTTP 端点访问前端:"
echo "http://weather-ai-frontend-jinhui-20260126.s3-website-ap-southeast-1.amazonaws.com"
echo ""
