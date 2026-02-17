"""
telegram_notifier.py — Telegram Bot 通知集成

通过 Telegram Bot API 发送天气预警和系统通知。
配置: .env 中设置 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID。

用法:
  1. 找 @BotFather 创建 Bot → 获取 TOKEN
  2. 给 Bot 发一条消息
  3. 访问 https://api.telegram.org/bot<TOKEN>/getUpdates → 获取 CHAT_ID
  4. 设置环境变量: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

import logging
import os
from datetime import datetime, timezone, timedelta

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SGT = timezone(timedelta(hours=8))

# 避免短时间内重复发送同一地点的预警
_recent_alerts: dict[str, datetime] = {}
COOLDOWN_MINUTES = 30


def is_configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def send_message(text: str, chat_id: str | None = None) -> bool:
    """发送 Telegram 消息 (同步)

    Args:
        text: 消息内容 (支持 Markdown)
        chat_id: 目标 chat_id, 默认使用环境变量
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not configured, skipping")
        return False

    target = chat_id or TELEGRAM_CHAT_ID
    if not target:
        logger.warning("TELEGRAM_CHAT_ID not configured, skipping")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": target,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        resp = httpx.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info(f"Telegram message sent to {target}")
            return True
        else:
            logger.error(f"Telegram API error: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


def send_rain_alert(location: str, probability: float, rainfall_mm: float,
                    lat: float, lon: float) -> bool:
    """发送降雨预警

    内置 30 分钟冷却期，同一地点不会重复发送。
    """
    # 冷却检查
    now = datetime.now(SGT)
    key = f"{lat:.2f},{lon:.2f}"
    if key in _recent_alerts:
        elapsed = (now - _recent_alerts[key]).total_seconds() / 60
        if elapsed < COOLDOWN_MINUTES:
            logger.debug(f"Rain alert for {location} suppressed (cooldown {elapsed:.0f}min)")
            return False

    time_str = now.strftime("%H:%M SGT")
    text = (
        f"🌧 *Rain Alert*\n\n"
        f"📍 *{location}*\n"
        f"⏰ {time_str}\n"
        f"🌧 Rainfall: {rainfall_mm:.1f} mm\n"
        f"📊 Probability: {probability:.0%}\n\n"
        f"_Source: Weather AI API Service_"
    )

    success = send_message(text)
    if success:
        _recent_alerts[key] = now
    return success


def send_system_alert(title: str, details: str) -> bool:
    """发送系统告警 (训练完成、服务异常等)"""
    now = datetime.now(SGT).strftime("%Y-%m-%d %H:%M SGT")
    text = (
        f"⚙️ *{title}*\n\n"
        f"⏰ {now}\n"
        f"{details}\n\n"
        f"_Source: Weather AI API Service_"
    )
    return send_message(text)


def send_test_message() -> bool:
    """发送测试消息验证配置"""
    return send_message(
        "✅ *Weather AI Telegram Bot*\n\n"
        "Connection test successful\\!\n"
        f"Time: {datetime.now(SGT).strftime('%Y-%m-%d %H:%M SGT')}\n\n"
        "_Source: Weather AI API Service_"
    )
