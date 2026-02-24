---
description: AWS 账号切换和资源管理规则
---

# AWS 账号管理规则

## 默认账号

- **默认使用 `gcc-jinhui` AWS profile**，所有 AWS CLI 和 SDK 操作均使用此账号
- 除非用户明确要求切换到其他账号（如 `personal`），否则一律使用 `gcc-jinhui`

## 账号切换

当需要切换账号时，使用 `--profile` 参数指定：

```bash
# 默认（gcc-jinhui），无需额外参数
aws s3 ls --profile gcc-jinhui

# 临时切换到 personal 账号
aws s3 ls --profile personal
```

## 资源管理规则

- `gcc-jinhui` 账号中的基础设施资源通过 **Terraform** 管理
- 执行 Terraform 操作时，工作目录为 `infra/terraform/`
- `personal` 账号不再作为默认账号使用

## 变更记录

| 日期 | 变更内容 |
|------|---------|
| 2026-02-24 | 默认账号从 `personal` 切换为 `gcc-jinhui` |
