# AWS 资源成本估算

## 概述

本文档记录 Weather AI 项目的 AWS 资源成本估算，基于 ap-southeast-1 (新加坡) 区域定价。

---

## EC2 实例成本

| 实例名称 | 实例 ID | 类型 | 每小时 | 用途 |
|----------|---------|------|--------|------|
| weather-ai-download-server | i-0edc956bf2dc0c197 | t3.micro | $0.0116 | 批量下载 |
| weather-ai-training-server | i-09f62a4b8f3a0a0b1 | t3.large | $0.0928 | 模型训练 |
| weather-ai-api-server | i-004dffd96ed716316 | t3.medium | $0.0464 | API 服务 |

### 运行成本计算

| 实例 | 运行模式 | 每日成本 | 每周成本 | 每月成本 |
|------|----------|----------|----------|----------|
| 下载服务器 (t3.micro) | 临时 (7天) | $0.28 | **$2** | - |
| 训练服务器 (t3.large) | 训练期 (7天) | $2.23 | **$16** | - |
| API 服务器 (t3.medium) | 持续运行 | $1.11 | $7.78 | **$34** |

---

## S3 存储成本

| 存储类型 | 数据量 | 单价 (GB/月) | 月成本 |
|----------|--------|--------------|--------|
| 模型文件 | ~100 MB | $0.025 | ~$0 |
| 传感器数据 | ~10 MB | $0.025 | ~$0 |
| 归档数据 (可选) | ~500 GB | $0.025 | ~$13 |
| **总计** | | | **~$13** |

---

## S3 数据传输成本

| 传输类型 | 价格/GB | 说明 |
|----------|---------|------|
| 入站 (Internet → S3) | **免费** | JAXA 下载到 S3 |
| 同区 (EC2 ↔ S3) | **免费** | 训练服务器读取 S3 |
| 出站 (S3 → Internet) | $0.12 | API 外部访问 |

> ⚠️ **重要**：所有资源在同一区域 (ap-southeast-1)，区内传输免费。

---

## 总成本估算

### 训练期间 (首周)

| 资源 | 成本 |
|------|------|
| 下载服务器 (7天) | $2 |
| 训练服务器 (7天) | $16 |
| API 服务器 (7天) | $8 |
| S3 存储 | ~$1 |
| **总计** | **~$27** |

### 训练完成后 (每月)

| 资源 | 成本 |
|------|------|
| API 服务器 (持续) | $34 |
| S3 存储 | ~$1 |
| **总计** | **~$35/月** |

---

## 成本优化建议

### 立即可做

1. **停止闲置实例**
   ```bash
   # 训练完成后停止训练服务器
   aws ec2 stop-instances --instance-ids i-09f62a4b8f3a0a0b1 --region ap-southeast-1
   
   # 下载完成后停止下载服务器
   aws ec2 stop-instances --instance-ids i-0edc956bf2dc0c197 --region ap-southeast-1
   ```

2. **删除临时数据**
   ```bash
   # 清理已归档的原始数据
   aws s3 rm s3://weather-ai-models-de08370c/archived/ --recursive
   ```

### 长期优化

| 方案 | 节省 | 说明 |
|------|------|------|
| 使用 Spot 实例训练 | ~70% | 训练服务器可中断 |
| Reserved Instance (API) | ~40% | 1年预付 |
| S3 Glacier 归档 | ~80% | 冷存储 |

---

## 账单监控

### 设置预算警报

```bash
aws budgets create-budget \
  --account-id YOUR_ACCOUNT_ID \
  --budget '{
    "BudgetName": "weather-ai-monthly",
    "BudgetLimit": {"Amount": "50", "Unit": "USD"},
    "TimeUnit": "MONTHLY",
    "BudgetType": "COST"
  }'
```

### 查看当前成本

```bash
aws ce get-cost-and-usage \
  --time-period Start=2026-01-01,End=2026-01-31 \
  --granularity MONTHLY \
  --metrics BlendedCost
```

---

## 更新记录

| 日期 | 更新内容 |
|------|----------|
| 2026-01-27 | 初始版本，基于分离式训练架构 |
