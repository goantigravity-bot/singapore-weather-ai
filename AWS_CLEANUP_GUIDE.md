# AWS 服务停止和清理指南

## 概述

本指南说明如何停止或删除部署在 AWS 上的新加坡天气 AI 应用服务，以避免产生不必要的费用。

## 当前部署的服务

### 1. EC2 实例（后端）
- **实例 ID**: 需要从 AWS 控制台获取
- **类型**: t2.micro 或类似
- **区域**: ap-southeast-1 (新加坡)
- **费用**: 按小时计费（运行时）+ EBS 存储费用

### 2. S3 Bucket（前端）
- **Bucket 名称**: weather-ai-frontend-jinhui-20260126
- **区域**: ap-southeast-1 (新加坡)
- **费用**: 存储费用 + 数据传输费用

---

## 方法一：使用自动化脚本（推荐）

### 准备工作

1. **获取 EC2 实例 ID**:
```bash
aws ec2 describe-instances \
  --region ap-southeast-1 \
  --filters "Name=tag:Name,Values=weather-api" \
  --query 'Reservations[*].Instances[*].[InstanceId,State.Name]' \
  --output table
```

2. **编辑脚本配置**:
打开 `stop-aws-services.sh`，修改以下变量：
```bash
EC2_INSTANCE_ID="i-xxxxxxxxx"  # 替换为你的实例 ID
S3_BUCKET="weather-ai-frontend-jinhui-20260126"
REGION="ap-southeast-1"
```

### 运行脚本

```bash
chmod +x stop-aws-services.sh
./stop-aws-services.sh
```

### 脚本选项说明

#### 选项 1: 停止 EC2 实例
- **操作**: 停止 EC2 实例（不删除）
- **费用影响**: 
  - ✅ 停止计算费用
  - ⚠️ 仍产生少量 EBS 存储费用（约 $0.10/GB/月）
- **恢复**: 可以随时重新启动
- **适用场景**: 临时不使用，但计划稍后恢复

#### 选项 2: 终止 EC2 实例
- **操作**: 永久删除 EC2 实例
- **费用影响**: 
  - ✅ 完全停止所有 EC2 相关费用
- **恢复**: ❌ 无法恢复，需要重新部署
- **适用场景**: 不再需要该服务

#### 选项 3: 删除 S3 Bucket
- **操作**: 清空并删除 S3 Bucket
- **费用影响**: 
  - ✅ 停止所有 S3 相关费用
- **恢复**: ❌ 无法恢复，需要重新部署
- **适用场景**: 不再需要前端服务

#### 选项 4: 停止所有服务（保留数据）
- **操作**: 停止 EC2，保留 S3
- **费用影响**: 
  - ✅ 停止 EC2 计算费用
  - ⚠️ 少量 EBS 和 S3 存储费用
- **适用场景**: 临时停用，保留数据以便恢复

#### 选项 5: 删除所有服务
- **操作**: 终止 EC2 + 删除 S3
- **费用影响**: 
  - ✅ 完全停止所有费用
- **恢复**: ❌ 无法恢复
- **适用场景**: 完全不再需要该项目

---

## 方法二：通过 AWS 控制台手动操作

### 停止/终止 EC2 实例

1. 登录 [AWS EC2 控制台](https://ap-southeast-1.console.aws.amazon.com/ec2)
2. 选择区域：**ap-southeast-1 (新加坡)**
3. 点击左侧菜单 **实例**
4. 找到你的天气 API 实例
5. 选择实例，点击 **实例状态**：
   - **停止实例**: 临时停止，可恢复
   - **终止实例**: 永久删除

### 删除 S3 Bucket

1. 登录 [AWS S3 控制台](https://s3.console.aws.amazon.com/s3)
2. 找到 Bucket: `weather-ai-frontend-jinhui-20260126`
3. 点击 Bucket 名称
4. 点击 **清空** 按钮，删除所有对象
5. 返回 Bucket 列表
6. 选择 Bucket，点击 **删除**

---

## 方法三：使用 AWS CLI 命令

### 获取实例 ID

```bash
aws ec2 describe-instances \
  --region ap-southeast-1 \
  --query 'Reservations[*].Instances[*].[InstanceId,Tags[?Key==`Name`].Value|[0],State.Name]' \
  --output table
```

### 停止 EC2 实例

```bash
aws ec2 stop-instances \
  --instance-ids i-xxxxxxxxx \
  --region ap-southeast-1
```

### 终止 EC2 实例

```bash
aws ec2 terminate-instances \
  --instance-ids i-xxxxxxxxx \
  --region ap-southeast-1
```

### 删除 S3 Bucket

```bash
# 清空 Bucket
aws s3 rm s3://weather-ai-frontend-jinhui-20260126 --recursive --region ap-southeast-1

# 删除 Bucket
aws s3api delete-bucket \
  --bucket weather-ai-frontend-jinhui-20260126 \
  --region ap-southeast-1
```

---

## 费用说明

### EC2 费用（t2.micro 示例）

| 状态 | 计算费用 | EBS 存储费用 | 总费用/月 |
|------|---------|-------------|----------|
| 运行中 | ~$8.50 | ~$0.80 | ~$9.30 |
| 已停止 | $0 | ~$0.80 | ~$0.80 |
| 已终止 | $0 | $0 | $0 |

### S3 费用

| 项目 | 费用 |
|------|------|
| 存储 (前 50TB) | $0.025/GB/月 |
| GET 请求 | $0.0004/1000 请求 |
| 数据传出 | $0.12/GB（前 10TB） |

**示例**：100MB 网站，1000 次访问/月 ≈ $0.01-0.05/月

---

## 重新启动服务

### 重新启动 EC2 实例

```bash
aws ec2 start-instances \
  --instance-ids i-xxxxxxxxx \
  --region ap-southeast-1
```

### 获取新的公网 IP

```bash
aws ec2 describe-instances \
  --instance-ids i-xxxxxxxxx \
  --region ap-southeast-1 \
  --query 'Reservations[*].Instances[*].PublicIpAddress' \
  --output text
```

> ⚠️ **注意**: 停止后重新启动 EC2 实例，公网 IP 会改变！需要更新前端配置中的 API 地址。

---

## 推荐策略

### 开发/测试阶段
- **每日下班后**: 停止 EC2 实例
- **周末**: 停止 EC2 实例
- **S3**: 保持运行（费用极低）

### 长期不使用
- **1 周以上**: 终止 EC2，保留 S3
- **1 个月以上**: 删除所有服务

### 生产环境
- **持续运行**: 考虑使用 Reserved Instances 节省费用
- **自动扩展**: 配置 Auto Scaling 根据流量调整

---

## 检查当前费用

### AWS Cost Explorer

1. 登录 [AWS Billing 控制台](https://console.aws.amazon.com/billing)
2. 点击 **Cost Explorer**
3. 查看当前月份费用
4. 按服务分组查看详细费用

### 设置费用警报

```bash
# 创建 SNS 主题
aws sns create-topic --name billing-alarm --region us-east-1

# 订阅邮箱
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT_ID:billing-alarm \
  --protocol email \
  --notification-endpoint your-email@example.com
```

---

## 常见问题

### Q: 停止 EC2 后还会产生费用吗？
A: 会产生少量 EBS 存储费用（约 $0.80/月），但计算费用会停止。

### Q: 如何完全停止所有费用？
A: 终止 EC2 实例并删除 S3 Bucket。

### Q: 重新启动 EC2 后 IP 会变吗？
A: 是的，公网 IP 会改变。建议使用 Elastic IP（但会产生额外费用）。

### Q: S3 静态网站托管费用高吗？
A: 非常低，小型网站通常每月不到 $0.10。

### Q: 可以只在需要时启动服务吗？
A: 可以，但每次启动后需要更新前端配置中的 API 地址（因为 IP 会变）。

---

## 总结

- ✅ **临时停用**: 使用选项 4（停止 EC2，保留 S3）
- ✅ **完全停用**: 使用选项 5（删除所有服务）
- ✅ **节省费用**: 不使用时及时停止服务
- ✅ **监控费用**: 设置费用警报

**建议**: 如果不是生产环境，建议在不使用时停止或删除服务以节省费用。
