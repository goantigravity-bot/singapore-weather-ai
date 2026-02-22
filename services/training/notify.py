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
    emoji, title = TYPES.get(notify_type, ("📌", notify_type))
    year_str = f" [{year}]" if year else ""
    subject = f"{emoji} Weather AI{year_str} — {title}"

    # 将 details 格式化为 HTML 表格
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

    if not SENDER or not PASSWORD or not RECIPIENT:
        logger.warning(f"邮件未配置，跳过通知: {subject}")
        return False

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True, choices=list(TYPES.keys()))
    parser.add_argument("--year", default="")
    parser.add_argument("--details", default="")
    args = parser.parse_args()
    send_notification(args.type, args.year, args.details)
