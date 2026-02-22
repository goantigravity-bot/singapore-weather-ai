"""
训练管道通知工具 — 供 train_yearly.sh 调用发送邮件。

用法:
    python3 notify.py --type download_start --year 2020 --details "sat=135000 npy, csv=366 days"
    python3 notify.py --type download_end --year 2020 --details "sat=135000, csv=3.2M rows, time=15min"
    python3 notify.py --type train_start --year 2020 --details "epochs=30, mode=initial"
    python3 notify.py --type epoch --year 2020 --details "epoch=5/30, loss=0.08, mae=0.21, time=15s"
    python3 notify.py --type train_end --year 2020 --details "epochs=30, best_loss=0.08, time=8min"
    python3 notify.py --type eval --year 2020 --details "rain_acc=65%, f1=0.42, threshold=0.5"
    python3 notify.py --type complete --details "years=2020-2026, total_time=9h, final_loss=0.05"
    python3 notify.py --type error --year 2020 --details "step=training, error=OOM killed"
"""
import os
import sys
import smtplib
import argparse
import logging
import urllib.request
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("notify")

# 从 .env 文件加载（如果存在）
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

SENDER = os.environ.get("SENDER_EMAIL", "")
PASSWORD = os.environ.get("SENDER_PASSWORD", "")
RECIPIENT = os.environ.get("RECIPIENT_EMAIL", "")
CC = [e.strip() for e in os.environ.get("CC_EMAILS", "").split(",") if e.strip()]

# Telegram
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# 通知类型 → emoji + 标题
TYPES = {
    "download_start": ("📥", "数据下载开始"),
    "download_end":   ("✅", "数据下载完成"),
    "train_start":    ("🚀", "训练开始"),
    "epoch":          ("📊", "Epoch 完成"),
    "train_end":      ("🏁", "训练完成"),
    "eval":           ("📋", "模型评估"),
    "complete":       ("🎉", "全部训练完成"),
    "error":          ("❌", "训练失败"),
}


def send_notification(notify_type, year, details):
    """同时发送邮件和 Telegram 通知。"""
    send_email(notify_type, year, details)
    send_telegram(notify_type, year, details)


def send_email(notify_type, year, details):
    """发送 HTML 邮件通知。"""
    if not SENDER or not PASSWORD or not RECIPIENT:
        return False

    emoji, title = TYPES.get(notify_type, ("📌", notify_type))
    year_str = f" [{year}]" if year else ""
    subject = f"{emoji} Weather AI{year_str} — {title}"

    detail_rows = ""
    if details:
        for item in details.split(","):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                detail_rows += f"<tr><td style='padding:4px 12px;font-weight:bold'>{k.strip()}</td><td style='padding:4px 12px'>{v.strip()}</td></tr>"
            else:
                detail_rows += f"<tr><td colspan='2' style='padding:4px 12px'>{item}</td></tr>"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto">
        <h2 style="color:{'#d32f2f' if notify_type == 'error' else '#1976d2'}">{emoji} {title}{year_str}</h2>
        <table style="border-collapse:collapse;width:100%;border:1px solid #ddd">
            <tr><td style='padding:4px 12px;font-weight:bold'>时间</td><td style='padding:4px 12px'>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
            {f"<tr><td style='padding:4px 12px;font-weight:bold'>年份</td><td style='padding:4px 12px'>{year}</td></tr>" if year else ""}
            {detail_rows}
        </table>
    </div>
    """

    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER
        msg["To"] = RECIPIENT
        msg["Cc"] = ", ".join(CC)
        msg["Subject"] = subject
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(SENDER, PASSWORD)
            server.sendmail(SENDER, [RECIPIENT] + CC, msg.as_string())
        logger.info(f"✅ 邮件已发送: {subject}")
        return True
    except Exception as e:
        logger.warning(f"邮件发送失败: {e}")
        return False


def send_telegram(notify_type, year, details):
    """通过 Telegram Bot 发送通知。"""
    if not TG_TOKEN or not TG_CHAT_ID:
        return False

    emoji, title = TYPES.get(notify_type, ("📌", notify_type))
    year_str = f" [{year}]" if year else ""

    # 构建 HTML 消息（比 Markdown 对特殊字符更宽容）
    lines = [f"<b>{emoji} {title}{year_str}</b>"]
    lines.append(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if details:
        for item in details.split(","):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                lines.append(f"• <b>{k.strip()}</b>: {v.strip()}")
            else:
                lines.append(f"• {item}")

    text = "\n".join(lines)
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }).encode()

    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                logger.info(f"✅ Telegram 已发送: {title}{year_str}")
                return True
    except Exception as e:
        logger.warning(f"Telegram 发送失败: {e}")
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True, choices=list(TYPES.keys()))
    parser.add_argument("--year", default="")
    parser.add_argument("--details", default="")
    args = parser.parse_args()
    send_notification(args.type, args.year, args.details)
