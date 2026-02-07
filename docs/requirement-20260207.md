# 需求文档 — 2026-02-07

## 邮件通知多收件人支持

**需求日期**: 2026-02-07  
**状态**: ✅ 已实现  

---

### 需求描述

训练完成/失败的邮件通知需支持发送给多个收件人，收件人列表可通过环境变量配置，无需修改代码。

### 配置方式

在训练服务器的 `.env.production` 文件中设置：

```bash
# 主收件人
RECIPIENT_EMAIL="jinhui.sg@gmail.com"

# 额外收件人（逗号分隔，可添加多个）
CC_EMAILS="go.antigravity@gmail.com,another@example.com"
```

- 修改 `CC_EMAILS` 后无需重启服务，下一个训练批次会自动生效
- `CC_EMAILS` 为空时只发送给 `RECIPIENT_EMAIL`

### 涉及文件

| 文件 | 变更 |
|------|------|
| `notification.py` | 新增 `CC_EMAILS` 环境变量解析，`send_email()` 支持多收件人 |
| `.env.production` | 新增 `CC_EMAILS` 配置项 |

### 实现细节

```python
# notification.py
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", SENDER_EMAIL)
CC_EMAILS = [e.strip() for e in os.environ.get("CC_EMAILS", "").split(",") if e.strip()]
ALL_RECIPIENTS = list(set(filter(None, [RECIPIENT_EMAIL] + CC_EMAILS)))
```

邮件通过 `server.sendmail(SENDER_EMAIL, ALL_RECIPIENTS, text)` 发送给所有收件人。

---

## 服务器时区统一为新加坡时间

**需求日期**: 2026-02-07  
**状态**: ✅ 已实现  

### 需求描述

所有服务器日志和时间戳应显示新加坡本地时间（UTC+8），而非 UTC，方便运维团队阅读和排查问题。

### 实施范围

| 服务器 | IP | 用途 |
|--------|-----|------|
| 训练服务器 | 46.137.236.8 | 模型训练 |
| API 服务器 | 3.0.28.161 | 预测 API / 监控仪表盘 |
| 下载服务器 | 18.142.90.30 | 卫星数据下载 |

### 配置命令

```bash
sudo timedatectl set-timezone Asia/Singapore
```

- 立即生效，无需重启服务
- Python `logging` 模块自动使用系统时区

