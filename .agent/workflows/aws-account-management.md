---
description: AWS 账号切换和资源管理规则
---

# AWS Account Management Rules

## 默认行为

- **默认 AWS Profile**: `personal`
- 日常操作（SSH、S3、EC2 启停）直接使用 AWS CLI + `personal` profile
- 手动管理资源是可以的

## gcc-jinhui 账号 (108379846317)

> **强制规则**: 当用户明确要求切换到 `gcc-jinhui` 账号时，所有 AWS 资源的创建、修改、删除 **必须通过 Terraform** 执行。

- **Profile**: `gcc-jinhui`
- **Terraform 目录**: `infra/terraform-gcc/`
- **操作流程**:
  1. 修改 `terraform.tfvars` 或 `.tf` 文件
  2. `AWS_PROFILE=gcc-jinhui terraform plan`
  3. 确认后 `AWS_PROFILE=gcc-jinhui terraform apply`
- **禁止**: 直接用 AWS CLI 创建/删除资源（如 `aws ec2 run-instances`）
- **允许**: 用 AWS CLI 做只读操作（如 `aws ec2 describe-instances`）

## 快速参考

| 账号 | Profile | 管理方式 | Terraform 目录 |
|------|---------|---------|---------------|
| Personal | `personal` | AWS CLI / 手动 | `infra/terraform/` |
| GCC | `gcc-jinhui` | **Terraform only** | `infra/terraform-gcc/` |

## EC2 实例管理注意事项

> **重要**: EC2 实例 stop/start 后，公网 IP 会变更（除非绑定了弹性 IP）。

### API Server 重启流程

每次 start API server 实例后，必须先查询新 IP：

```bash
# 查询 API server 当前 IP
aws ec2 describe-instances --profile personal \
  --filters "Name=instance-id,Values=i-004dffd96ed716316" \
  --query "Reservations[0].Instances[0].PublicIpAddress" \
  --output text
```

然后用新 IP 进行 SSH 和部署操作，避免使用旧的硬编码 IP（如 `3.0.28.161`）。

### 已知实例 ID

| 服务 | Instance ID | 说明 |
|------|------------|------|
| API Server | `i-004dffd96ed716316` | stop 后 IP 会变 |
