# AWS 服务启动指南

## 快速启动（推荐）

### 方法一：使用自动化脚本

```bash
./start-aws-services.sh
```

这个脚本会：
1. ✅ 启动 EC2 实例
2. ✅ 等待实例完全启动
3. ✅ 自动获取新的公网 IP
4. ✅ 显示更新前端的命令

### 方法二：手动启动

#### 1. 启动 EC2 实例

```bash
aws ec2 start-instances --instance-ids i-004dffd96ed716316 --region ap-southeast-1
```

#### 2. 等待实例启动完成

```bash
aws ec2 wait instance-running --instance-ids i-004dffd96ed716316 --region ap-southeast-1
```

#### 3. 获取新的公网 IP

```bash
aws ec2 describe-instances \
  --instance-ids i-004dffd96ed716316 \
  --region ap-southeast-1 \
  --query 'Reservations[*].Instances[*].PublicIpAddress' \
  --output text
```

---

## ⚠️ 重要：更新前端 API 地址

每次停止后重新启动 EC2，公网 IP 会改变！必须更新前端配置。

### 自动更新（推荐）

```bash
# 假设新 IP 是 3.1.2.3
./update-frontend-api.sh 3.1.2.3
```

这个脚本会自动：
1. 更新 `frontend/.env.production`
2. 重新构建前端
3. 部署到 S3

### 手动更新

#### 1. 更新环境变量

编辑 `frontend/.env.production`：
```bash
VITE_API_BASE_URL=http://新的IP地址
```

#### 2. 重新构建

```bash
cd frontend
npm run build
```

#### 3. 部署到 S3

```bash
aws s3 sync dist/ s3://weather-ai-frontend-jinhui-20260126 --delete --region ap-southeast-1
```

---

## 验证服务

### 检查 EC2 状态

```bash
aws ec2 describe-instances \
  --instance-ids i-004dffd96ed716316 \
  --region ap-southeast-1 \
  --query 'Reservations[*].Instances[*].[InstanceId,State.Name,PublicIpAddress]' \
  --output table
```

### 测试后端 API

```bash
# 替换为实际 IP
curl http://新的IP地址/health
```

应该返回：
```json
{
  "status": "ok"
}
```

### 测试前端

访问：http://weather-ai-frontend-jinhui-20260126.s3-website-ap-southeast-1.amazonaws.com

---

## 完整启动流程

### 步骤 1: 启动 EC2

```bash
./start-aws-services.sh
```

记录输出的新 IP 地址，例如：`3.1.2.3`

### 步骤 2: 更新前端

```bash
./update-frontend-api.sh 3.1.2.3
```

### 步骤 3: 验证

```bash
# 测试后端
curl http://3.1.2.3/health

# 在浏览器访问前端
open http://weather-ai-frontend-jinhui-20260126.s3-website-ap-southeast-1.amazonaws.com
```

---

## 避免 IP 改变的方法

### 方法一：使用 Elastic IP（推荐生产环境）

#### 分配 Elastic IP

```bash
aws ec2 allocate-address --region ap-southeast-1
```

记录返回的 `AllocationId`

#### 关联到实例

```bash
aws ec2 associate-address \
  --instance-id i-004dffd96ed716316 \
  --allocation-id eipalloc-xxxxxxxxx \
  --region ap-southeast-1
```

**优点**：
- ✅ IP 固定，无需每次更新前端
- ✅ 适合生产环境

**缺点**：
- ⚠️ 额外费用：约 $0.005/小时（实例运行时免费，停止时收费）
- ⚠️ 停止实例时仍会产生 Elastic IP 费用

### 方法二：保持实例运行

如果每天都要使用，考虑保持实例运行而不是每天停止/启动。

**费用对比**：
- 每天停止/启动：节省计算费用，但需要每次更新前端
- 持续运行：约 $9/月，但 IP 固定，无需更新

---

## 常见问题

### Q: 启动需要多长时间？
A: 通常 1-2 分钟，脚本会自动等待。

### Q: 如果忘记更新前端会怎样？
A: 前端无法连接到后端 API，会显示错误。

### Q: 可以在 AWS 控制台启动吗？
A: 可以，但仍需要手动获取新 IP 并更新前端。

### Q: 有没有办法自动更新前端？
A: 可以使用 CloudFormation 或 Terraform 自动化，但对于简单项目，使用提供的脚本已经很方便了。

---

## 快速参考

### 启动服务
```bash
./start-aws-services.sh
```

### 更新前端
```bash
./update-frontend-api.sh <新IP>
```

### 停止服务
```bash
./stop-aws-services.sh
```

### 检查状态
```bash
aws ec2 describe-instances \
  --instance-ids i-004dffd96ed716316 \
  --region ap-southeast-1 \
  --query 'Reservations[*].Instances[*].[State.Name,PublicIpAddress]' \
  --output table
```

---

## 总结

✅ **明天启动服务**：运行 `./start-aws-services.sh`  
✅ **更新前端**：运行 `./update-frontend-api.sh <新IP>`  
✅ **验证服务**：访问前端和测试 API  
✅ **晚上停止**：运行 `./stop-aws-services.sh`（选项 1 或 4）

这样可以在不使用时节省费用，需要时快速恢复！
