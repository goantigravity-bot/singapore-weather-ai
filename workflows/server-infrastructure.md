---
description: 服务器基础设施信息和健康检查流程
---

# 服务器基础设施

## SSH 连接信息

所有服务器使用同一密钥：`~/.ssh/id_rsa`

| 角色 | IP | 用户 | 备注 |
|------|-----|------|------|
| Download Server | 52.221.178.169 | ubuntu | 数据下载服务 |
| Training Server (Spot) | 54.179.62.87 | ubuntu | GPU 训练，Spot 实例，IP 可能变化 |
| API Server | 13.228.95.52 | ubuntu | 生产 API 服务 |

```bash
# Download Server
ssh -i ~/.ssh/id_rsa ubuntu@52.221.178.169

# Training Server (Spot — IP may change)
ssh -i ~/.ssh/id_rsa ubuntu@54.179.62.87

# API Server
ssh -i ~/.ssh/id_rsa ubuntu@13.228.95.52
```

## 获取最新 IP

IP 地址可能变化（尤其是 Spot 实例），可通过 AWS CLI 获取最新 IP：

```bash
# 使用 gcc-jinhui profile 查询所有运行中的实例
aws ec2 describe-instances \
  --profile gcc-jinhui \
  --filters "Name=instance-state-name,Values=running" \
  --query 'Reservations[].Instances[].[Tags[?Key==`Name`].Value|[0],PublicIpAddress,InstanceType,State.Name]' \
  --output table
```

## 服务端口

| 服务 | 端口 | 健康检查方式 |
|------|------|-------------|
| API Backend | 8000 | `curl http://<API_IP>:8000/health` |
| Download Service | 无（后台服务） | Telegram 通知 + SSH 进程检查 |
| Training Service | — | EC2 实例状态（Spot，按需启停） |

## Routine 健康检查流程

执行健康检查时，按以下三步进行：

### Step 1: API 服务 HTTP 检查

```bash
curl -s -m 10 http://13.228.95.52:8000/health
```

期望返回：`{"status":"ok","version":"x.x.x","service":"api",...}`

### Step 2: EC2 实例状态检查

```bash
aws ec2 describe-instances \
  --profile gcc-jinhui \
  --region ap-southeast-1 \
  --filters "Name=instance-state-name,Values=running,stopped" \
  --query 'Reservations[].Instances[].[Tags[?Key==`Name`].Value|[0],PublicIpAddress,InstanceType,State.Name]' \
  --output table
```

### Step 3: Telegram 通知验证（业务心跳）

通过浏览器工具打开 Telegram Web，检查 **"Weather AI Alert"** bot 的最近消息。

**关键通知类型：**

| 通知消息 | 来源服务器 | 含义 | 正常频率 |
|---------|-----------|------|---------|
| `Sync Cycle Complete [API Server]` | API | 传感器数据刷新、模型加载、PSI 更新 | 每 ~5 分钟 |
| `Sensor Sync Complete [Download Server]` | Download | 从 data.gov.sg 同步传感器数据 | 每 ~5 分钟 |
| `Satellite Image Downloaded [Download Server]` | Download | 卫星云图下载完成 | 每个时段 slot |

**检查要点：**

- 确认最新消息时间在合理范围内（不超过 10-15 分钟）
- API Server 和 Download Server 都应有近期消息
- Download Server 不监听任何端口，Telegram 通知是确认其工作状态的主要方式

### 检查结果汇总模板

```
| 服务器 | EC2 状态 | HTTP 检查 | Telegram 最新通知 | 结论 |
|--------|---------|----------|-----------------|------|
| API    | running | 200 OK   | xx:xx SGT       | ✅   |
| Download | running | N/A    | xx:xx SGT       | ✅   |
| Training | stopped | N/A   | N/A             | 🔴   |
```

## 变更记录

| 日期 | 变更内容 |
|------|---------|
| 2026-02-24 | 新增 Telegram 通知验证（Weather AI Alert bot）作为 Step 3 |
| 2026-02-24 | 修正 Download Server 检查方式（不监听端口，通过 Telegram 确认） |
| 2026-02-24 | 初始记录：Download(52.221.178.169), Training(54.179.62.87), API(13.228.95.52) |
