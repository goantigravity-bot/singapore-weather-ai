# 应用部署快速指南

## 🚀 快速部署（推荐）

### 前提条件
- ✅ AWS基础设施已创建（Terraform已完成）
- ✅ 有EC2 SSH密钥文件
- ✅ 已配置AWS CLI

### 一键部署

```bash
# 1. 配置环境变量（可选，如果需要邮件通知和自动训练）
cp .env.production.template .env.production
nano .env.production  # 填写实际值

# 2. 运行部署脚本
./deploy-all.sh

# 3. 选择部署选项
# 选择 3) 前端 + 后端（完整部署）
```

---

## 📝 手动部署步骤

### 步骤1: 部署后端到EC2

#### 1.1 连接到EC2

```bash
ssh -i ~/.ssh/weather-ai-key.pem ubuntu@3.0.28.161
```

#### 1.2 克隆代码

```bash
cd /home/ubuntu/weather-ai

# 如果代码在GitHub
git clone https://github.com/your-username/singapore-weather-ai.git .

# 或者从本地上传（在本地机器执行）
rsync -avz --exclude 'node_modules' --exclude '.git' \
  -e "ssh -i ~/.ssh/weather-ai-key.pem" \
  /Users/jinhui/development/tools/claude-skill/ \
  ubuntu@3.0.28.161:/home/ubuntu/weather-ai/
```

#### 1.3 安装Python依赖

```bash
cd /home/ubuntu/weather-ai
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 1.4 上传必要文件

在本地机器执行：

```bash
# 上传训练好的模型
scp -i ~/.ssh/weather-ai-key.pem \
    weather_fusion_model.pth \
    ubuntu@3.0.28.161:/home/ubuntu/weather-ai/

# 上传传感器数据
scp -i ~/.ssh/weather-ai-key.pem \
    real_sensor_data.csv \
    ubuntu@3.0.28.161:/home/ubuntu/weather-ai/

# 上传预处理图像（如果有）
scp -i ~/.ssh/weather-ai-key.pem -r \
    processed_images/ \
    ubuntu@3.0.28.161:/home/ubuntu/weather-ai/

# 上传环境变量（如果需要）
scp -i ~/.ssh/weather-ai-key.pem \
    .env.production \
    ubuntu@3.0.28.161:/home/ubuntu/weather-ai/.env
```

#### 1.5 配置systemd服务

在EC2上执行：

```bash
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

# 启动服务
sudo systemctl daemon-reload
sudo systemctl start weather-api
sudo systemctl enable weather-api

# 检查状态
sudo systemctl status weather-api
```

#### 1.6 测试API

```bash
# 在EC2上测试
curl http://localhost:8000/health

# 在本地测试
curl http://3.0.28.161:8000/health
```

---

### 步骤2: 部署前端到S3

#### 2.1 配置API端点

```bash
cd frontend

# 创建生产环境变量
echo "VITE_API_URL=http://3.0.28.161:8000" > .env.production
```

#### 2.2 构建前端

```bash
npm install
npm run build
```

#### 2.3 上传到S3

```bash
aws s3 sync dist/ s3://weather-ai-frontend-jinhui-20260126/ --delete
```

#### 2.4 清除CloudFront缓存

```bash
aws cloudfront create-invalidation \
  --distribution-id E3NTCXM5BZ2EUY \
  --paths "/*"
```

---

## ✅ 验证部署

### 后端验证

```bash
# 健康检查
curl http://3.0.28.161:8000/health
# 预期: {"status":"ok"}

# 获取站点列表
curl http://3.0.28.161:8000/stations
# 预期: 返回站点列表JSON

# 测试预测
curl "http://3.0.28.161:8000/predict?location=Changi"
# 预期: 返回预测结果
```

### 前端验证

```bash
# 访问前端
open https://d1em23i2wkbin3.cloudfront.net

# 或使用curl测试
curl -I https://d1em23i2wkbin3.cloudfront.net
# 预期: HTTP 200
```

### 完整功能测试

1. 打开前端URL
2. 地图应该正常加载
3. 点击地图上的位置
4. 应该显示天气预测结果

---

## 🔧 配置自动训练（可选）

如果您想启用每日自动训练：

```bash
# SSH到EC2
ssh -i ~/.ssh/weather-ai-key.pem ubuntu@3.0.28.161

# 编辑crontab
crontab -e

# 添加以下行（每天凌晨2点执行）
0 2 * * * cd /home/ubuntu/weather-ai && /home/ubuntu/weather-ai/venv/bin/python3 auto_train_pipeline.py >> training_logs/cron.log 2>&1

# 添加存储清理（每天凌晨3点）
0 3 * * * cd /home/ubuntu/weather-ai && /home/ubuntu/weather-ai/venv/bin/python3 cleanup_storage.py >> training_logs/cleanup.log 2>&1
```

---

## 🆘 故障排查

### API无法启动

```bash
# 查看服务日志
sudo journalctl -u weather-api -f

# 检查端口占用
sudo lsof -i :8000

# 手动启动测试
cd /home/ubuntu/weather-ai
source venv/bin/activate
python3 api.py
```

### 前端显示空白

```bash
# 检查S3文件
aws s3 ls s3://weather-ai-frontend-jinhui-20260126/

# 检查CloudFront状态
aws cloudfront get-distribution \
  --id E3NTCXM5BZ2EUY \
  --query 'Distribution.Status'

# 检查浏览器控制台错误
```

### API调用失败（CORS错误）

检查 `api.py` 中的CORS配置：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://d1em23i2wkbin3.cloudfront.net",
        "http://localhost:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 📊 部署后检查清单

- [ ] 后端API健康检查通过
- [ ] 前端页面可以访问
- [ ] 地图正常加载
- [ ] 可以获取天气预测
- [ ] API响应时间<500ms
- [ ] 前端加载时间<3秒
- [ ] 移动端显示正常
- [ ] CORS配置正确

---

## 🔄 更新部署

### 更新后端

```bash
# 在本地
./deploy-all.sh
# 选择选项1（仅后端）

# 或手动
ssh -i ~/.ssh/weather-ai-key.pem ubuntu@3.0.28.161
cd /home/ubuntu/weather-ai
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart weather-api
```

### 更新前端

```bash
# 在本地
cd frontend
npm run build
aws s3 sync dist/ s3://weather-ai-frontend-jinhui-20260126/ --delete
aws cloudfront create-invalidation --distribution-id E3NTCXM5BZ2EUY --paths "/*"
```

---

**创建时间**: 2026-01-26  
**EC2 IP**: 3.0.28.161  
**前端URL**: https://d1em23i2wkbin3.cloudfront.net
