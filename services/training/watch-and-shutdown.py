#!/usr/bin/env python3
"""
本地运行：轮询 Telegram 消息，检测到训练完成通知后自动 stop GPU 实例。

用法:
    python watch-and-shutdown.py

依赖:
    - boto3 (pip install boto3)
    - .env 文件中配置 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID
"""
import os
import sys
import time
import json
import logging
import urllib.request
import subprocess
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# --- 配置 ---
INSTANCE_ID = "i-015b892aee4af2e6d"
REGION = "ap-southeast-1"
POLL_INTERVAL = 30  # 每 30 秒检查一次

# 从 .env 读取 Telegram 配置
ENV_PATH = Path(__file__).parent / ".env"
def loadEnv():
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

env = loadEnv()
TG_TOKEN = env.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID = env.get("TELEGRAM_CHAT_ID", "")

# 训练完成的标志关键词
COMPLETE_KEYWORDS = ["🎉", "全部训练完成", "complete"]
# 训练失败的标志
ERROR_KEYWORDS = ["❌", "error", "异常退出"]


def getLatestTelegramMessages(offset=None):
    """从 Telegram Bot API 获取最新消息"""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates?timeout=10"
    if offset:
        url += f"&offset={offset}"
    
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            if data.get("ok"):
                return data.get("result", [])
    except Exception as e:
        logger.warning(f"Telegram API error: {e}")
    return []


def stopInstance():
    """通过 AWS CLI stop 实例"""
    logger.info(f"🔌 Stopping instance {INSTANCE_ID}...")
    try:
        result = subprocess.run(
            ["aws", "ec2", "stop-instances",
             "--instance-ids", INSTANCE_ID,
             "--region", REGION,
             "--profile", "personal"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            logger.info(f"✅ Instance {INSTANCE_ID} stop 指令已发送")
            logger.info(result.stdout)
            return True
        else:
            logger.error(f"❌ Stop failed: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"❌ Stop error: {e}")
        return False


def main():
    if not TG_TOKEN or not TG_CHAT_ID:
        logger.error("❌ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not found in .env")
        sys.exit(1)

    logger.info("=" * 50)
    logger.info("🔍 Training Completion Watcher")
    logger.info(f"   Instance: {INSTANCE_ID}")
    logger.info(f"   Region: {REGION}")
    logger.info(f"   Poll interval: {POLL_INTERVAL}s")
    logger.info(f"   Watching keywords: {COMPLETE_KEYWORDS + ERROR_KEYWORDS}")
    logger.info("=" * 50)

    # 记录启动时的 offset，只检查新消息
    updates = getLatestTelegramMessages()
    offset = updates[-1]["update_id"] + 1 if updates else None
    logger.info(f"📌 Starting offset: {offset} (ignoring old messages)")

    while True:
        time.sleep(POLL_INTERVAL)
        updates = getLatestTelegramMessages(offset=offset)

        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            text = msg.get("text", "")
            chat_id = str(msg.get("chat", {}).get("id", ""))

            # 只处理来自目标 chat 的消息
            if chat_id != TG_CHAT_ID:
                continue

            logger.info(f"📩 Message: {text[:80]}...")

            # 检查是否包含完成关键词
            isComplete = any(kw in text for kw in COMPLETE_KEYWORDS)
            isError = any(kw in text for kw in ERROR_KEYWORDS)

            if isComplete or isError:
                status = "✅ COMPLETED" if isComplete else "❌ FAILED"
                logger.info(f"🎯 Training {status}! Stopping instance...")
                stopInstance()
                logger.info("👋 Watcher exiting.")
                sys.exit(0)


if __name__ == "__main__":
    main()
