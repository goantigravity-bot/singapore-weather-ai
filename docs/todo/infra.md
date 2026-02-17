# Infra TODO

## Terraform

- [ ] 清理 tfstate — 当前 state 与实际资源不完全对齐（手动创建的资源）
- [ ] 考虑迁移到新 AWS 账号
  - 备份旧 state
  - 更新 `terraform.tfvars` (bucket name 等)
  - `terraform destroy` 旧账号 或 手动清理
  - 新账号 `terraform init && apply`
- [ ] Terraform 版本升级 (v1.5.7 → v1.14.5)
- [ ] 限制 SSH 允许 IP（目前 `0.0.0.0/0`）

## 服务器

- [ ] 下载完成后关闭 download server (t3.xlarge, ~02-20)
- [ ] API 服务器按需启停（不用时关机省钱）
- [ ] Training server Spot 实例策略确认

## 通知集成

- [x] Telegram Bot 集成 (WeatherAIAlertBot)
  - [x] `telegram_notifier.py` 通知模块
  - [x] API 端点: `/telegram/status`, `/test`, `/alert`
  - [x] 部署到 API 服务器并验证
  - [ ] 定时雨量预警检查任务 (cron)
- [ ] Slack Webhook 集成（后续）

## 监控

- [ ] CloudWatch 告警: CPU > 90%, 磁盘 > 80%
- [ ] 下载进度自动通知 (Telegram)
- [ ] API 健康检查 + 自动重启
- [ ] 成本监控告警 (Budget)

## S3 Bucket 硬编码清理

- [ ] 统一改为从环境变量读取 `S3_BUCKET`，消除硬编码 `weather-ai-models-de08370c`
  - 11 处已有 `os.environ.get()` fallback（可接受）
  - **25 处完全硬编码**（必须修改）：`scan_rainy_dates.py`, `check_s3_sat.py`, `training_scheduler.py`, 多个 `.sh` 脚本等
  - Python: 统一为 `os.environ.get("S3_BUCKET", "weather-ai-models-de08370c")`
  - Shell: 统一为 `S3_BUCKET="${S3_BUCKET:-weather-ai-models-de08370c}"`

## 安全

- [ ] `.env` 中敏感信息迁移到 AWS Secrets Manager 或 SSM Parameter Store
- [ ] EC2 IAM Role 最小权限审查
- [ ] S3 Bucket Policy 审查
