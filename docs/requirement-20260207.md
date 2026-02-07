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
