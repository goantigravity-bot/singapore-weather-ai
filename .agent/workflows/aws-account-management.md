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
