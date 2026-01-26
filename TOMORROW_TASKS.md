# 明天工作任务 - 2026-01-27

## 📋 任务概览

1. **测试增量训练功能**
2. **部署训练模型到新的 EC2 实例**

---

## 任务 1: 测试增量训练功能

### 目标
验证模型的增量训练（incremental training）功能是否正常工作，确保模型可以在现有基础上继续训练而不是从头开始。

### 背景
- 项目中已有自动训练流程 (`auto_train_pipeline.py`)
- 需要验证增量训练是否能正确加载已有模型并继续训练
- 确保训练历史和状态正确保存

### 准备工作

#### 1. 检查现有模型
```bash
# 查看当前模型文件
ls -lh weather_fusion_model.pth

# 查看训练历史
cat training_history.json

# 查看训练状态
cat training_state.json
```

#### 2. 检查训练脚本
需要检查的文件：
- `train.py` - 主训练脚本
- `auto_train_pipeline.py` - 自动训练流程
- `weather_fusion_model.py` - 模型定义

### 测试步骤

#### 步骤 1: 备份现有模型
```bash
# 创建备份目录
mkdir -p model_backups/$(date +%Y%m%d)

# 备份当前模型
cp weather_fusion_model.pth model_backups/$(date +%Y%m%d)/
cp training_history.json model_backups/$(date +%Y%m%d)/
cp training_state.json model_backups/$(date +%Y%m%d)/
```

#### 步骤 2: 运行增量训练测试
```bash
# 激活虚拟环境
source venv/bin/activate

# 运行训练（应该自动检测并加载现有模型）
python train.py

# 或使用自动训练流程
python auto_train_pipeline.py
```

#### 步骤 3: 验证结果
需要验证的内容：
- [ ] 模型是否正确加载了之前的权重
- [ ] 训练是否从上次的 epoch 继续
- [ ] 训练历史是否正确追加
- [ ] 模型性能是否有改善
- [ ] 训练日志是否正确记录

#### 步骤 4: 检查训练日志
```bash
# 查看最新的训练日志
ls -lt training_logs/

# 查看训练报告
ls -lt training_reports/
```

### 预期结果

1. **模型加载**：
   - 日志应显示 "Loading existing model from weather_fusion_model.pth"
   - 不应该显示 "Initializing new model"

2. **训练继续**：
   - Epoch 应该从上次结束的位置继续
   - 例如：如果上次训练到 epoch 10，这次应该从 epoch 11 开始

3. **历史记录**：
   - `training_history.json` 应该包含所有历史训练记录
   - 新的训练记录应该追加到现有记录后面

4. **性能指标**：
   - 损失（loss）应该继续下降或保持稳定
   - 准确率应该保持或提升

### 可能的问题和解决方案

#### 问题 1: 模型未正确加载
**症状**：训练从 epoch 1 开始
**检查**：
```python
# 在 train.py 中检查模型加载逻辑
if os.path.exists('weather_fusion_model.pth'):
    model.load_state_dict(torch.load('weather_fusion_model.pth'))
    print("✅ 模型已加载")
else:
    print("⚠️ 未找到现有模型，从头开始训练")
```

#### 问题 2: 训练历史未保存
**检查**：
```bash
# 查看训练历史文件
cat training_history.json | jq .
```

#### 问题 3: 数据不足
**解决**：
```bash
# 获取最新的天气数据
python fetch_and_process_gov_data.py
```

### 测试清单

- [ ] 备份现有模型和训练历史
- [ ] 运行增量训练
- [ ] 验证模型正确加载
- [ ] 验证训练从正确的 epoch 继续
- [ ] 检查训练历史是否正确追加
- [ ] 验证模型性能指标
- [ ] 查看训练日志和报告
- [ ] 测试预测功能是否正常
- [ ] 记录测试结果

---

## 任务 2: 部署训练模型到新的 EC2 实例

### 目标
创建一个专门用于模型训练的 EC2 实例，将训练任务与 API 服务分离。

### 架构设计

```
当前架构：
┌─────────────────────┐
│   EC2 Instance      │
│  - API 服务 (8000)  │
│  - 训练任务         │
└─────────────────────┘

目标架构：
┌─────────────────────┐     ┌─────────────────────┐
│  EC2 - API Server   │     │ EC2 - Training      │
│  - FastAPI (8000)   │     │ - 模型训练          │
│  - Nginx            │     │ - 数据处理          │
│  - 预测服务         │     │ - 定时任务          │
└─────────────────────┘     └─────────────────────┘
         │                           │
         └───────────────┬───────────┘
                         │
                    ┌────▼────┐
                    │   S3    │
                    │ (模型存储)│
                    └─────────┘
```

### 准备工作

#### 1. 确定实例规格

**API 服务器**（现有）：
- 类型：t2.micro 或 t2.small
- 用途：API 服务、预测
- 费用：~$9/月

**训练服务器**（新建）：
- 类型：建议 t2.medium 或 c5.large（需要更多 CPU/内存）
- 用途：模型训练、数据处理
- 费用：~$30-60/月（可以按需启动/停止）

#### 2. 创建 EC2 实例

##### 方法 1: AWS 控制台
1. 登录 [AWS EC2 控制台](https://ap-southeast-1.console.aws.amazon.com/ec2)
2. 点击 "启动实例"
3. 配置：
   - **名称**：weather-training-server
   - **AMI**：Ubuntu Server 22.04 LTS
   - **实例类型**：t2.medium（2 vCPU, 4GB RAM）
   - **密钥对**：选择现有或创建新的
   - **安全组**：允许 SSH (22)
   - **存储**：30GB gp3（训练数据和模型）

##### 方法 2: AWS CLI
```bash
# 创建训练服务器实例
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t2.medium \
  --key-name your-key-pair \
  --security-group-ids sg-xxxxxxxx \
  --subnet-id subnet-xxxxxxxx \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":30}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=weather-training-server}]' \
  --region ap-southeast-1
```

### 部署步骤

#### 步骤 1: 配置训练服务器

```bash
# 连接到新实例
ssh -i your-key.pem ubuntu@<TRAINING_SERVER_IP>

# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Python 和依赖
sudo apt install -y python3.10 python3.10-venv python3-pip git

# 安装系统依赖
sudo apt install -y build-essential libhdf5-dev libnetcdf-dev
```

#### 步骤 2: 部署训练代码

```bash
# 克隆代码仓库
git clone https://github.com/goantigravity-bot/singapore-weather-ai.git
cd singapore-weather-ai

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
pip install torch torchvision  # 如果需要
```

#### 步骤 3: 配置 S3 模型存储

创建 S3 Bucket 用于存储训练好的模型：

```bash
# 创建 S3 Bucket
aws s3 mb s3://weather-ai-models-jinhui --region ap-southeast-1

# 配置 Bucket 策略（仅允许训练服务器访问）
```

#### 步骤 4: 创建训练脚本

创建 `deploy_training_server.sh`：
```bash
#!/bin/bash
# 部署训练服务器

TRAINING_SERVER_IP="<TRAINING_SERVER_IP>"
KEY_FILE="your-key.pem"

# 上传代码
rsync -avz -e "ssh -i $KEY_FILE" \
  --exclude 'venv' \
  --exclude 'node_modules' \
  --exclude '__pycache__' \
  ./ ubuntu@$TRAINING_SERVER_IP:~/singapore-weather-ai/

# 连接并设置
ssh -i $KEY_FILE ubuntu@$TRAINING_SERVER_IP << 'EOF'
cd singapore-weather-ai
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 运行测试训练
python train.py --test

echo "✅ 训练服务器部署完成"
EOF
```

#### 步骤 5: 配置定时训练任务

在训练服务器上设置 cron 任务：

```bash
# 编辑 crontab
crontab -e

# 添加每日训练任务（每天凌晨 2 点）
0 2 * * * cd /home/ubuntu/singapore-weather-ai && /home/ubuntu/singapore-weather-ai/venv/bin/python auto_train_pipeline.py >> /home/ubuntu/training.log 2>&1

# 添加每周完整训练（每周日凌晨 3 点）
0 3 * * 0 cd /home/ubuntu/singapore-weather-ai && /home/ubuntu/singapore-weather-ai/venv/bin/python train.py --full >> /home/ubuntu/training.log 2>&1
```

#### 步骤 6: 配置模型同步

创建模型同步脚本 `sync_model_to_s3.sh`：
```bash
#!/bin/bash
# 同步模型到 S3

MODEL_FILE="weather_fusion_model.pth"
S3_BUCKET="s3://weather-ai-models-jinhui"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 备份到 S3
aws s3 cp $MODEL_FILE $S3_BUCKET/models/$TIMESTAMP/
aws s3 cp $MODEL_FILE $S3_BUCKET/models/latest.pth

# 同步训练历史
aws s3 cp training_history.json $S3_BUCKET/history/

echo "✅ 模型已同步到 S3"
```

#### 步骤 7: API 服务器获取最新模型

在 API 服务器上创建 `fetch_latest_model.sh`：
```bash
#!/bin/bash
# 从 S3 获取最新模型

S3_BUCKET="s3://weather-ai-models-jinhui"
MODEL_FILE="weather_fusion_model.pth"

# 备份当前模型
if [ -f "$MODEL_FILE" ]; then
    cp $MODEL_FILE ${MODEL_FILE}.backup
fi

# 下载最新模型
aws s3 cp $S3_BUCKET/models/latest.pth $MODEL_FILE

# 重启 API 服务（如果需要）
sudo systemctl restart weather-api

echo "✅ 模型已更新"
```

### 测试清单

#### 训练服务器
- [ ] EC2 实例创建成功
- [ ] SSH 连接正常
- [ ] Python 环境配置完成
- [ ] 代码部署成功
- [ ] 依赖安装完成
- [ ] 训练脚本可以运行
- [ ] S3 访问权限配置正确
- [ ] 定时任务配置成功

#### 模型同步
- [ ] 模型可以上传到 S3
- [ ] API 服务器可以从 S3 下载模型
- [ ] 模型版本管理正常
- [ ] 训练历史同步正常

#### 集成测试
- [ ] 训练服务器完成训练
- [ ] 模型自动同步到 S3
- [ ] API 服务器获取最新模型
- [ ] 预测功能使用新模型正常工作

### 成本优化

#### 按需启动训练服务器
```bash
# 启动训练服务器
aws ec2 start-instances --instance-ids i-xxxxxxxx --region ap-southeast-1

# 运行训练
ssh ubuntu@<IP> "cd singapore-weather-ai && source venv/bin/activate && python auto_train_pipeline.py"

# 训练完成后停止
aws ec2 stop-instances --instance-ids i-xxxxxxxx --region ap-southeast-1
```

**费用对比**：
- 持续运行：~$30/月
- 每天运行 2 小时：~$2/月
- 每周运行一次（2 小时）：~$0.50/月

### 文档和脚本

需要创建的文件：
- [ ] `deploy_training_server.sh` - 部署训练服务器
- [ ] `sync_model_to_s3.sh` - 同步模型到 S3
- [ ] `fetch_latest_model.sh` - API 服务器获取模型
- [ ] `start_training_job.sh` - 启动训练任务
- [ ] `TRAINING_SERVER_GUIDE.md` - 训练服务器使用指南

---

## 时间估算

| 任务 | 预计时间 |
|------|---------|
| 任务 1: 测试增量训练 | 1-2 小时 |
| 任务 2: 创建 EC2 实例 | 30 分钟 |
| 任务 2: 配置训练环境 | 1 小时 |
| 任务 2: 配置 S3 和同步 | 1 小时 |
| 任务 2: 测试和验证 | 1 小时 |
| **总计** | **4.5-5.5 小时** |

---

## 成功标准

### 任务 1
- ✅ 增量训练功能正常工作
- ✅ 模型可以正确加载和继续训练
- ✅ 训练历史正确记录
- ✅ 模型性能有改善或保持稳定

### 任务 2
- ✅ 训练服务器成功部署
- ✅ 训练任务可以自动运行
- ✅ 模型可以自动同步到 S3
- ✅ API 服务器可以获取最新模型
- ✅ 整个流程端到端测试通过

---

## 备注

- 所有操作前记得备份重要数据
- 测试过程中记录详细日志
- 遇到问题及时记录和解决
- 完成后更新文档

## 参考资料

- [AWS EC2 文档](https://docs.aws.amazon.com/ec2/)
- [AWS S3 文档](https://docs.aws.amazon.com/s3/)
- [PyTorch 模型保存和加载](https://pytorch.org/tutorials/beginner/saving_loading_models.html)
