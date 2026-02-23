"""
notify.py — 统一通知模块（Email + Telegram）

供所有 server 共用（download / training / api）。
CLI 模式供 shell 脚本调用，import 模式供 Python 代码调用。

配置项（从环境变量或 .env 文件读取）：
  SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL, CC_EMAILS
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

用法 (CLI)：
  python3 notify.py --type satellite_done --details "date=2026-02-23, frames=144"
  python3 notify.py --type error --source download --details "NOAA timeout"

用法 (import)：
  from shared.notify import send_notification
  send_notification("satellite_done", details="frames=144", source="download")
"""
import os
import sys
import socket
import smtplib
import argparse
import logging
import urllib.request
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

logger = logging.getLogger(__name__)
HOSTNAME = socket.gethostname()

# === .env 加载（从调用方目录 或 shared/ 目录） ===

def _load_env():
    """从多个候选路径加载 .env"""
    candidates = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())
            break

_load_env()

# === 配置 ===
SENDER = os.environ.get("SENDER_EMAIL", "")
PASSWORD = os.environ.get("SENDER_PASSWORD", "")
RECIPIENT = os.environ.get("RECIPIENT_EMAIL", "")
CC = [e.strip() for e in os.environ.get("CC_EMAILS", "").split(",") if e.strip()]

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# All notification types → emoji + English title
TYPES = {
    # Download Server
    "satellite_done":    ("🛰️", "Satellite Download Complete"),
    "satellite_error":   ("🛰️❌", "Satellite Download Failed"),
    "sensor_done":       ("📡", "Sensor Sync Complete"),
    "backfill_done":     ("🔄", "Backfill Complete"),
    # Training Server
    "download_start":    ("📥", "Data Download Started"),
    "download_end":      ("✅", "Data Download Complete"),
    "train_start":       ("🚀", "Training Started"),
    "epoch":             ("📊", "Epoch Complete"),
    "train_end":         ("🏁", "Training Complete"),
    "eval":              ("📋", "Model Evaluation"),
    "complete":          ("🎉", "All Training Complete"),
    # General
    "info":              ("ℹ️", "Info"),
    "warning":           ("⚠️", "Warning"),
    "error":             ("❌", "Error"),
}


def send_notification(notify_type: str, details: str = "",
                      source: str = "", year: str = "") -> bool:
    """同时发送 Email 和 Telegram 通知。

    Args:
        notify_type: 通知类型（见 TYPES 字典）
        details: 逗号分隔的 key=value 字符串
        source: 来源标识（download / training / api）
        year: 可选年份标签
    """
    email_ok = _send_email(notify_type, details, source, year)
    tg_ok = _send_telegram(notify_type, details, source, year)
    return email_ok or tg_ok


def _send_email(notify_type: str, details: str, source: str, year: str) -> bool:
    if not SENDER or not PASSWORD or not RECIPIENT:
        return False

    emoji, title = TYPES.get(notify_type, ("📌", notify_type))
    source_str = f" [{source}]" if source else ""
    year_str = f" [{year}]" if year else ""
    subject = f"{emoji} Weather AI{source_str}{year_str} — {title}"

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
        <h2 style="color:{'#d32f2f' if 'error' in notify_type else '#1976d2'}">{emoji} {title}{source_str}{year_str}</h2>
        <table style="border-collapse:collapse;width:100%;border:1px solid #ddd">
            <tr><td style='padding:4px 12px;font-weight:bold'>Time</td><td style='padding:4px 12px'>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
            <tr><td style='padding:4px 12px;font-weight:bold'>Host</td><td style='padding:4px 12px'>{HOSTNAME}</td></tr>
            {f"<tr><td style='padding:4px 12px;font-weight:bold'>Source</td><td style='padding:4px 12px'>{source}</td></tr>" if source else ""}
            {f"<tr><td style='padding:4px 12px;font-weight:bold'>Year</td><td style='padding:4px 12px'>{year}</td></tr>" if year else ""}
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
        logger.info(f"✅ Email sent: {subject}")
        return True
    except Exception as e:
        logger.warning(f"Email failed: {e}")
        return False


def _send_telegram(notify_type: str, details: str, source: str, year: str) -> bool:
    if not TG_TOKEN or not TG_CHAT_ID:
        return False

    emoji, title = TYPES.get(notify_type, ("📌", notify_type))
    source_str = f" [{source}]" if source else ""
    year_str = f" [{year}]" if year else ""

    lines = [f"<b>{emoji} {title}{source_str}{year_str}</b>"]
    lines.append(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"🖥 {HOSTNAME}")
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
                logger.info(f"✅ Telegram sent: {title}{source_str}")
                return True
    except Exception as e:
        logger.warning(f"Telegram failed: {e}")
    return False


# === CLI 入口 ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="Weather AI Notification")
    parser.add_argument("--type", required=True, choices=list(TYPES.keys()))
    parser.add_argument("--source", default="", help="Source server (download/training/api)")
    parser.add_argument("--year", default="")
    parser.add_argument("--details", default="")
    args = parser.parse_args()
    send_notification(args.type, args.details, args.source, args.year)
