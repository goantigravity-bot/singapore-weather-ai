# 云部署完整指南 - 考虑资源限制

## 📊 当前资源使用分析

### 存储需求
```
总项目大小: 79 GB
├── satellite_data/        79 GB  (原始卫星数据 .nc 文件)
├── processed_images/      16 MB  (预处理后的 .npy 文件)
├── real_sensor_data.csv   9.8 MB (传感器数据)
└── weather_fusion_model.pth 320 KB (训练模型)
```

### 关键发现
- ⚠️ **卫星数据占用79GB** - 这是主要存储瓶颈
- ✅ 实际训练只需要：processed_images (16MB) + sensor_data (9.8MB) + model (320KB) ≈ **26MB**
- 💡 **优化策略**：不需要在云端保留所有原始卫星数据

### 计算需求
- **训练时间**（优化后）：
  - 首次训练：~50-60分钟（30 epochs）
  - 增量训练：~8-10分钟（5 epochs）
- **内存需求**：~4-8GB RAM
- **GPU**：可选（MPS/CUDA），CPU也可以训练

---

## 🎯 云部署方案对比

### 方案1：轻量级部署（推荐 ⭐⭐⭐）

**适合**: 资源受限，成本敏感

#### 架构
```
┌─────────────────────────────────────┐
│  云服务器（训练 + API）              │
│  - 只存储必要文件                    │
│  - 按需下载卫星数据                  │
│  - 训练后删除原始数据                │
└─────────────────────────────────────┘
         ↓ 下载
┌─────────────────────────────────────┐
│  JAXA FTP（卫星数据源）              │
│  - 按需下载最近24小时数据            │
│  - 预处理后立即删除原始文件          │
└─────────────────────────────────────┘
```

#### 资源需求
- **存储**: 5-10 GB（包含系统和依赖）
- **内存**: 4 GB RAM
- **CPU**: 2 vCPU
- **成本**: ~$10-20/月

#### 实施步骤
1. 只上传代码和已训练模型
2. 每日自动下载最近24小时卫星数据
3. 预处理后删除原始 .nc 文件
4. 使用30天滑动窗口限制数据增长

---

### 方案2：混合存储部署

**适合**: 需要保留历史数据，但云端资源有限

#### 架构
```
┌─────────────────────────────────────┐
│  云服务器（训练 + API）              │
│  - 代码 + 模型                       │
│  - 最近30天预处理数据                │
└─────────────────────────────────────┘
         ↕ 同步
┌─────────────────────────────────────┐
│  对象存储（S3/OSS）                  │
│  - 历史卫星数据归档                  │
│  - 训练历史和报告                    │
└─────────────────────────────────────┘
```

#### 资源需求
- **云服务器存储**: 10 GB
- **对象存储**: 按需（S3 ~$0.023/GB/月）
- **内存**: 4-8 GB RAM
- **CPU**: 2-4 vCPU
- **成本**: ~$20-40/月

---

### 方案3：分离部署（最优化）

**适合**: 生产环境，高可用性需求

#### 架构
```
┌─────────────────────────────────────┐
│  API服务器（轻量级）                 │
│  - FastAPI应用                       │
│  - 训练好的模型                      │
│  - 传感器数据                        │
│  资源: 1GB存储, 1GB RAM, 1 vCPU     │
│  成本: ~$5/月                        │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  训练服务器（按需启动）              │
│  - 每日定时启动                      │
│  - 下载数据 → 训练 → 上传模型        │
│  - 训练完成后自动关闭                │
│  资源: 10GB存储, 4GB RAM, 2 vCPU    │
│  成本: ~$0.5/天 × 30天 = $15/月     │
└─────────────────────────────────────┘
```

---

## 💰 成本优化策略

### 1. 存储优化

#### 删除原始卫星数据
```python
# 在 preprocess_images.py 中添加
def cleanup_raw_files(sat_dir, keep_days=1):
    """删除N天前的原始.nc文件"""
    cutoff = datetime.now() - timedelta(days=keep_days)
    
    for file in os.listdir(sat_dir):
        if file.endswith('.nc'):
            file_path = os.path.join(sat_dir, file)
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            
            if file_time < cutoff:
                os.remove(file_path)
                print(f"已删除旧文件: {file}")
```

#### 使用压缩
```bash
# 压缩传感器数据
gzip real_sensor_data.csv  # 9.8MB → ~2MB

# 压缩预处理图像
tar -czf processed_images.tar.gz processed_images/  # 16MB → ~8MB
```

### 2. 计算优化

#### 使用Spot实例（AWS/GCP）
- 成本降低70-90%
- 适合可中断的训练任务
- 配合检查点保存

#### 按需启动训练
```bash
# crontab 每日凌晨2点启动实例
0 2 * * * aws ec2 start-instances --instance-ids i-xxxxx

# 训练完成后自动关闭
# 在 auto_train_pipeline.py 末尾添加
os.system("sudo shutdown -h now")
```

---

## 🚀 推荐部署方案（资源受限）

### 配置：AWS/阿里云轻量服务器

**规格**:
- **CPU**: 2 vCPU
- **内存**: 4 GB RAM
- **存储**: 20 GB SSD
- **带宽**: 3-5 Mbps
- **成本**: ~$10-15/月

### 部署步骤

#### 1. 服务器准备
```bash
# 连接服务器
ssh user@your-server-ip

# 安装依赖
sudo apt update
sudo apt install python3-pip python3-venv git -y

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 克隆代码
git clone your-repo.git weather-ai
cd weather-ai
pip install -r requirements.txt
```

#### 2. 上传必要文件
```bash
# 从本地上传（在本地机器执行）
scp real_sensor_data.csv user@server:/path/to/weather-ai/
scp weather_fusion_model.pth user@server:/path/to/weather-ai/
scp -r processed_images/ user@server:/path/to/weather-ai/
```

#### 3. 配置自动清理
```bash
# 创建清理脚本
cat > cleanup.sh << 'EOF'
#!/bin/bash
# 删除3天前的原始卫星数据
find satellite_data/ -name "*.nc" -mtime +3 -delete

# 删除30天前的训练日志
find training_logs/ -name "*.log" -mtime +30 -delete

# 删除旧的训练报告（保留最近10个）
ls -t training_reports/report_*.html | tail -n +11 | xargs rm -f
EOF

chmod +x cleanup.sh

# 添加到crontab（每天凌晨3点执行）
echo "0 3 * * * cd /path/to/weather-ai && ./cleanup.sh" | crontab -
```

#### 4. 配置自动训练
```bash
# 每天凌晨2点自动训练
echo "0 2 * * * cd /path/to/weather-ai && /path/to/venv/bin/python3 auto_train_pipeline.py >> training_logs/cron.log 2>&1" | crontab -
```

#### 5. 启动API服务
```bash
# 使用systemd管理API服务
sudo cat > /etc/systemd/system/weather-api.service << 'EOF'
[Unit]
Description=Weather AI API Service
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/weather-ai
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python3 api.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 启动服务
sudo systemctl daemon-reload
sudo systemctl enable weather-api
sudo systemctl start weather-api
```

---

## 📦 Docker部署（推荐）

### 优势
- ✅ 环境一致性
- ✅ 易于迁移
- ✅ 资源隔离

### Docker Compose配置
```yaml
# docker-compose.yml
version: '3.8'

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    ports:
      - "8000:8000"
    volumes:
      - ./weather_fusion_model.pth:/app/weather_fusion_model.pth
      - ./real_sensor_data.csv:/app/real_sensor_data.csv
      - ./processed_images:/app/processed_images
    restart: always
    mem_limit: 2g
    
  trainer:
    build:
      context: .
      dockerfile: Dockerfile
    volumes:
      - ./data:/app/data
      - ./models:/app/models
    mem_limit: 4g
    # 手动启动训练，不自动运行
    command: /bin/bash
```

### 部署
```bash
# 构建镜像
docker-compose build

# 启动API服务
docker-compose up -d api

# 手动运行训练
docker-compose run --rm trainer python3 auto_train_pipeline.py
```

---

## 🌐 云服务商选择

### AWS
**推荐实例**: t3.medium
- 2 vCPU, 4 GB RAM
- 成本: ~$30/月（按需）
- 成本: ~$20/月（预留1年）

### 阿里云
**推荐**: 轻量应用服务器
- 2 vCPU, 4 GB RAM, 60 GB SSD
- 成本: ~¥70/月 (~$10/月)
- 优势: 国内访问快

### Google Cloud
**推荐**: e2-medium
- 2 vCPU, 4 GB RAM
- 成本: ~$25/月
- 优势: 免费$300额度（新用户）

### 腾讯云
**推荐**: 轻量应用服务器
- 2 vCPU, 4 GB RAM, 60 GB SSD
- 成本: ~¥50/月 (~$7/月)
- 优势: 价格便宜

---

## 📊 资源监控

### 存储监控脚本
```bash
#!/bin/bash
# monitor_storage.sh

echo "=== 存储使用情况 ==="
df -h /

echo -e "\n=== 项目目录大小 ==="
du -sh /path/to/weather-ai/*

echo -e "\n=== 卫星数据文件数 ==="
find satellite_data/ -name "*.nc" | wc -l

echo -e "\n=== 预处理文件数 ==="
find processed_images/ -name "*.npy" | wc -l
```

### 内存监控
```bash
# 查看内存使用
free -h

# 查看进程内存
ps aux --sort=-%mem | head -10
```

---

## ⚠️ 注意事项

### 1. 数据备份
即使删除原始数据，也要保留：
- ✅ 训练好的模型
- ✅ 传感器数据（CSV）
- ✅ 预处理图像（最近30天）

### 2. 网络带宽
- JAXA下载速度可能较慢
- 建议在低峰时段下载
- 考虑使用CDN加速

### 3. 安全配置
```bash
# 配置防火墙
sudo ufw allow 22    # SSH
sudo ufw allow 8000  # API
sudo ufw enable

# 配置SSL（使用Let's Encrypt）
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## 🎯 最终推荐

**对于资源受限场景**:

1. **使用轻量级云服务器**（阿里云/腾讯云 ~$7-10/月）
2. **实施存储优化**（自动删除旧数据）
3. **使用30天滑动窗口**（已实现）
4. **使用增量训练**（已实现）
5. **Docker部署**（易于管理）

**预期资源使用**:
- 存储: 5-10 GB
- 内存: 4 GB
- CPU: 2 vCPU
- 成本: $10-15/月

这个方案可以在资源受限的情况下稳定运行，同时保持良好的性能！

---

**创建时间**: 2026-01-26  
**状态**: 待实施  
**下一步**: 选择云服务商并开始部署
