# AWS 部署实战指南

## 🎯 部署目标

在AWS上部署天气AI系统，包括：
- ✅ API服务（24/7运行）
- ✅ 自动训练（每日执行）
- ✅ 成本优化（~$15-20/月）

---

## 📋 准备工作

### 1. AWS账号准备
- [ ] 注册AWS账号（如果还没有）
- [ ] 配置支付方式
- [ ] 启用MFA（多因素认证）

### 2. 本地准备
```bash
# 安装AWS CLI
# macOS
brew install awscli

# 配置AWS凭证
aws configure
# 输入：
# - AWS Access Key ID
# - AWS Secret Access Key
# - Default region: ap-southeast-1 (新加坡)
# - Default output format: json
```

### 3. 代码准备
```bash
# 确保代码在Git仓库中
cd /Users/jinhui/development/tools/claude-skill
git init
git add .
git commit -m "Initial commit for AWS deployment"

# 推送到GitHub/GitLab（私有仓库）
git remote add origin your-repo-url
git push -u origin main
```

---

## 🚀 部署步骤

### 步骤1: 创建EC2实例

#### 1.1 登录AWS控制台
访问: https://console.aws.amazon.com/ec2/

#### 1.2 启动实例
1. 点击 **"Launch Instance"**
2. 配置如下：

**基本配置**:
```
Name: weather-ai-server
AMI: Ubuntu Server 22.04 LTS (Free tier eligible)
Instance type: t3.medium (2 vCPU, 4 GB RAM)
              或 t3.small (2 vCPU, 2 GB RAM) - 更便宜
```

**密钥对**:
```
- 创建新密钥对
- 名称: weather-ai-key
- 类型: RSA
- 格式: .pem
- 下载并保存到安全位置
```

**网络设置**:
```
- VPC: 默认
- 子网: 默认
- 自动分配公网IP: 启用
- 防火墙规则:
  ✅ SSH (22) - 来源: My IP
  ✅ HTTP (80) - 来源: Anywhere
  ✅ HTTPS (443) - 来源: Anywhere
  ✅ 自定义TCP (8000) - 来源: Anywhere (API端口)
```

**存储配置**:
```
- 大小: 20 GB
- 类型: gp3 (通用SSD)
- 删除终止: 启用
```

#### 1.3 启动实例
点击 **"Launch Instance"**，等待实例启动（约1-2分钟）

---

### 步骤2: 连接到EC2实例

```bash
# 设置密钥权限
chmod 400 ~/Downloads/weather-ai-key.pem

# 连接到实例（替换为您的实例公网IP）
ssh -i ~/Downloads/weather-ai-key.pem ubuntu@YOUR_EC2_PUBLIC_IP

# 示例:
# ssh -i ~/Downloads/weather-ai-key.pem ubuntu@54.123.45.67
```

---

### 步骤3: 服务器环境配置

连接成功后，在EC2实例上执行：

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装Python和依赖
sudo apt install -y python3-pip python3-venv git htop tmux

# 创建工作目录
mkdir -p ~/weather-ai
cd ~/weather-ai

# 克隆代码（使用您的仓库URL）
git clone https://github.com/your-username/singapore-weather-ai.git .

# 或者如果是私有仓库，配置SSH密钥
# ssh-keygen -t rsa -b 4096 -C "your-email@example.com"
# cat ~/.ssh/id_rsa.pub  # 复制并添加到GitHub SSH keys

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt
```

---

### 步骤4: 上传必要文件

在**本地机器**执行：

```bash
# 上传训练好的模型
scp -i ~/Downloads/weather-ai-key.pem \
    weather_fusion_model.pth \
    ubuntu@YOUR_EC2_IP:~/weather-ai/

# 上传传感器数据
scp -i ~/Downloads/weather-ai-key.pem \
    real_sensor_data.csv \
    ubuntu@YOUR_EC2_IP:~/weather-ai/

# 上传预处理图像（如果有）
scp -i ~/Downloads/weather-ai-key.pem -r \
    processed_images/ \
    ubuntu@YOUR_EC2_IP:~/weather-ai/

# 上传环境变量配置
scp -i ~/Downloads/weather-ai-key.pem \
    env.sh \
    ubuntu@YOUR_EC2_IP:~/weather-ai/
```

---

### 步骤5: 配置环境变量

在EC2实例上：

```bash
cd ~/weather-ai

# 编辑环境变量文件
nano env.sh

# 添加以下内容（根据实际情况修改）
export SENDER_EMAIL="your-email@gmail.com"
export SENDER_PASSWORD="your-gmail-app-password"
export RECIPIENT_EMAIL="recipient@example.com"
export JAXA_USER="your-jaxa-username"
export JAXA_PASS="your-jaxa-password"

# 保存并退出（Ctrl+X, Y, Enter）

# 加载环境变量
source env.sh

# 添加到bashrc，使其永久生效
echo "source ~/weather-ai/env.sh" >> ~/.bashrc
```

---

### 步骤6: 测试系统

```bash
cd ~/weather-ai
source venv/bin/activate

# 测试API
python3 api.py &
# 等待几秒后
curl http://localhost:8000/health
# 应该返回: {"status":"ok"}

# 停止测试
pkill -f api.py

# 测试数据集加载
python3 weather_dataset.py

# 如果一切正常，继续下一步
```

---

### 步骤7: 配置API服务（systemd）

```bash
# 创建systemd服务文件
sudo nano /etc/systemd/system/weather-api.service
```

添加以下内容：

```ini
[Unit]
Description=Weather AI API Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/weather-ai
Environment="PATH=/home/ubuntu/weather-ai/venv/bin"
EnvironmentFile=/home/ubuntu/weather-ai/env.sh
ExecStart=/home/ubuntu/weather-ai/venv/bin/python3 /home/ubuntu/weather-ai/api.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
# 重新加载systemd
sudo systemctl daemon-reload

# 启动API服务
sudo systemctl start weather-api

# 设置开机自启
sudo systemctl enable weather-api

# 检查状态
sudo systemctl status weather-api

# 查看日志
sudo journalctl -u weather-api -f
```

---

### 步骤8: 配置自动训练（crontab）

```bash
# 编辑crontab
crontab -e

# 添加以下行（每天凌晨2点执行训练）
0 2 * * * cd /home/ubuntu/weather-ai && /home/ubuntu/weather-ai/venv/bin/python3 auto_train_pipeline.py >> training_logs/cron.log 2>&1

# 添加存储清理任务（每天凌晨3点）
0 3 * * * cd /home/ubuntu/weather-ai && /home/ubuntu/weather-ai/venv/bin/python3 cleanup_storage.py >> training_logs/cleanup.log 2>&1

# 保存并退出
```

---

### 步骤9: 配置Nginx反向代理（可选）

如果想使用域名和HTTPS：

```bash
# 安装Nginx
sudo apt install -y nginx

# 创建配置文件
sudo nano /etc/nginx/sites-available/weather-api
```

添加以下内容：

```nginx
server {
    listen 80;
    server_name your-domain.com;  # 替换为您的域名

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

启用配置：

```bash
# 创建符号链接
sudo ln -s /etc/nginx/sites-available/weather-api /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重启Nginx
sudo systemctl restart nginx

# 配置SSL（Let's Encrypt）
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

### 步骤10: 配置域名（可选）

如果您有域名：

1. 在域名提供商处添加A记录：
   ```
   类型: A
   主机: @ 或 api
   值: YOUR_EC2_PUBLIC_IP
   TTL: 3600
   ```

2. 等待DNS传播（5-30分钟）

3. 访问: http://your-domain.com/health

---

## 📊 监控和维护

### 查看API日志
```bash
# 实时查看API日志
sudo journalctl -u weather-api -f

# 查看最近100行
sudo journalctl -u weather-api -n 100
```

### 查看训练日志
```bash
# 查看cron日志
tail -f ~/weather-ai/training_logs/cron.log

# 查看最新训练日志
ls -lt ~/weather-ai/training_logs/training_*.log | head -1 | xargs tail -f
```

### 查看系统资源
```bash
# CPU和内存使用
htop

# 磁盘使用
df -h

# 存储详情
du -sh ~/weather-ai/*
```

### 手动运行训练
```bash
cd ~/weather-ai
source venv/bin/activate
python3 auto_train_pipeline.py
```

---

## 💰 成本估算

### EC2实例成本（按需定价 - 新加坡区域）

**t3.small** (2 vCPU, 2 GB RAM):
- 按需: $0.0208/小时
- 月成本: ~$15/月
- 适合: 轻量级部署

**t3.medium** (2 vCPU, 4 GB RAM):
- 按需: $0.0416/小时
- 月成本: ~$30/月
- 适合: 标准部署（推荐）

### 存储成本
- EBS gp3: $0.08/GB/月
- 20 GB: ~$1.6/月

### 数据传输
- 出站流量: 前1GB免费，之后$0.12/GB
- 预计: ~$2-5/月

### 总成本估算
- **最低配置**: ~$17/月（t3.small + 存储）
- **推荐配置**: ~$32/月（t3.medium + 存储）

### 成本优化建议
1. **使用预留实例**（1年承诺）: 节省30-40%
2. **使用Spot实例**（训练服务器）: 节省70-90%
3. **定期停止实例**（非生产环境）: 只为运行时间付费

---

## 🔒 安全最佳实践

### 1. 配置防火墙
```bash
# 启用UFW
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8000/tcp
sudo ufw enable
```

### 2. 定期更新系统
```bash
# 创建更新脚本
cat > ~/update.sh << 'EOF'
#!/bin/bash
sudo apt update
sudo apt upgrade -y
sudo apt autoremove -y
EOF

chmod +x ~/update.sh

# 添加到crontab（每周日凌晨4点）
# 0 4 * * 0 /home/ubuntu/update.sh >> /home/ubuntu/update.log 2>&1
```

### 3. 配置备份
```bash
# 备份重要文件到S3（可选）
# 需要先配置AWS CLI和S3 bucket

# 创建备份脚本
cat > ~/backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d)
tar -czf backup_$DATE.tar.gz \
    weather_fusion_model.pth \
    real_sensor_data.csv \
    training_history.json \
    training_state.json

# 上传到S3（如果配置了）
# aws s3 cp backup_$DATE.tar.gz s3://your-bucket/backups/

# 删除7天前的备份
find . -name "backup_*.tar.gz" -mtime +7 -delete
EOF

chmod +x ~/backup.sh

# 添加到crontab（每天凌晨5点）
# 0 5 * * * cd /home/ubuntu/weather-ai && /home/ubuntu/backup.sh
```

---

## ✅ 部署验证清单

完成部署后，验证以下项目：

- [ ] EC2实例正常运行
- [ ] SSH连接正常
- [ ] API服务运行正常（systemctl status weather-api）
- [ ] API健康检查通过（curl http://localhost:8000/health）
- [ ] 可以从外部访问API（http://YOUR_EC2_IP:8000/health）
- [ ] 自动训练任务已配置（crontab -l）
- [ ] 存储清理任务已配置
- [ ] 环境变量正确配置
- [ ] 日志正常输出
- [ ] 域名解析正常（如果配置了）
- [ ] HTTPS证书有效（如果配置了）

---

## 🆘 故障排查

### API无法启动
```bash
# 查看详细错误
sudo journalctl -u weather-api -n 50

# 检查端口占用
sudo lsof -i :8000

# 手动启动测试
cd ~/weather-ai
source venv/bin/activate
python3 api.py
```

### 训练失败
```bash
# 查看训练日志
cat ~/weather-ai/training_logs/cron.log

# 手动运行训练
cd ~/weather-ai
source venv/bin/activate
python3 auto_train_pipeline.py
```

### 存储空间不足
```bash
# 检查磁盘使用
df -h

# 运行清理脚本
cd ~/weather-ai
python3 cleanup_storage.py

# 如果需要扩展EBS卷
# 在AWS控制台修改卷大小，然后：
sudo growpart /dev/xvda 1
sudo resize2fs /dev/xvda1
```

---

## 📞 下一步

部署完成后，您可以：

1. **测试API**: http://YOUR_EC2_IP:8000/docs
2. **查看前端**: 部署React前端到S3 + CloudFront
3. **配置监控**: 使用CloudWatch监控实例
4. **设置告警**: 配置SNS通知

---

**创建时间**: 2026-01-26  
**适用区域**: AWS 新加坡（ap-southeast-1）  
**预计部署时间**: 30-60分钟
