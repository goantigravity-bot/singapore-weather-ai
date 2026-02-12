"""
Geocoding Provider 模块 — 策略模式封装 Nominatim / OneMap 双 provider。

为什么独立模块：将 geocoding 逻辑从 predict.py 解耦，
支持通过环境变量或运行时 API 切换 provider，不影响核心预测逻辑。
"""

import os
import time
import logging
import requests
import threading

logger = logging.getLogger(__name__)

# ─── Provider 配置 ───────────────────────────────────────────────────────────
# 运行时可通过 /config/geocoding API 切换，优先级：runtime > env > default
_current_provider = os.environ.get("GEOCODING_PROVIDER", "nominatim").lower()
_provider_lock = threading.Lock()

# ─── OneMap Token 管理 ───────────────────────────────────────────────────────
# Token 有效期 3 天，过期自动续签
_onemap_token: str | None = None
_onemap_token_expiry: float = 0  # epoch seconds


def get_provider() -> str:
    """返回当前 geocoding provider 名称"""
    return _current_provider


def set_provider(provider: str) -> str:
    """运行时切换 provider，返回切换后的值"""
    global _current_provider
    provider = provider.lower().strip()
    if provider not in ("nominatim", "onemap"):
        raise ValueError(f"Unknown provider: {provider}. Use 'nominatim' or 'onemap'.")
    with _provider_lock:
        _current_provider = provider
    logger.info(f"Geocoding provider switched to: {provider}")
    return _current_provider


def geocode(address: str) -> tuple[float | None, float | None]:
    """
    统一 geocoding 入口，根据当前 provider 分发。
    不含缓存逻辑 — 缓存由调用方（predict.py）管理。
    """
    provider = _current_provider
    if provider == "onemap":
        return _geocode_onemap(address)
    return _geocode_nominatim(address)


# ─── Nominatim ───────────────────────────────────────────────────────────────

def _geocode_nominatim(address: str) -> tuple[float | None, float | None]:
    """OpenStreetMap Nominatim — 全球覆盖，限速 1 req/s"""
    headers = {"User-Agent": "SingaporeWeatherAI/0.7"}
    url = "https://nominatim.openstreetmap.org/search"

    search_addr = address
    if "singapore" not in address.lower():
        search_addr = address + ", Singapore"

    params = {"q": search_addr, "format": "json", "limit": 1}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        data = resp.json()

        if data:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            logger.info(f"[Nominatim] Geocoded '{search_addr}': ({lat:.4f}, {lon:.4f})")
            return lat, lon
        else:
            logger.warning(f"[Nominatim] No results for '{search_addr}'")
            return None, None

    except Exception as e:
        logger.error(f"[Nominatim] Error: {e}")
        return None, None


# ─── OneMap ──────────────────────────────────────────────────────────────────

def _get_onemap_token() -> str | None:
    """获取或续签 OneMap API token（有效期 3 天）"""
    global _onemap_token, _onemap_token_expiry

    # Token 仍在有效期内（提前 1 小时续签）
    if _onemap_token and time.time() < _onemap_token_expiry - 3600:
        return _onemap_token

    email = os.environ.get("ONEMAP_EMAIL", "")
    password = os.environ.get("ONEMAP_PASSWORD", "")
    if not email or not password:
        logger.error("[OneMap] ONEMAP_EMAIL / ONEMAP_PASSWORD not configured")
        return None

    try:
        resp = requests.post(
            "https://www.onemap.gov.sg/api/auth/post/getToken",
            json={"email": email, "password": password},
            timeout=10,
        )
        data = resp.json()
        token = data.get("access_token")
        # OneMap token 有效期为 expiry_timestamp (epoch ms)
        expiry = data.get("expiry_timestamp")
        if token:
            _onemap_token = token
            # expiry 是字符串格式的 epoch seconds
            _onemap_token_expiry = float(expiry) if expiry else time.time() + 259200
            logger.info(f"[OneMap] Token obtained, expires at {_onemap_token_expiry}")
            return token

        logger.error(f"[OneMap] Token request failed: {data}")
        return None
    except Exception as e:
        logger.error(f"[OneMap] Token error: {e}")
        return None


def _geocode_onemap(address: str) -> tuple[float | None, float | None]:
    """OneMap Singapore — SLA 官方数据，新加坡地址精度最高"""
    token = _get_onemap_token()
    if not token:
        # Token 失败时降级到 Nominatim
        logger.warning("[OneMap] Token unavailable, falling back to Nominatim")
        return _geocode_nominatim(address)

    url = "https://www.onemap.gov.sg/api/common/elastic/search"
    params = {
        "searchVal": address,
        "returnGeom": "Y",
        "getAddrDetails": "Y",
        "pageNum": 1,
    }
    headers = {"Authorization": token}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        data = resp.json()

        results = data.get("results", [])
        if results:
            lat = float(results[0]["LATITUDE"])
            lon = float(results[0]["LONGITUDE"])
            logger.info(f"[OneMap] Geocoded '{address}': ({lat:.4f}, {lon:.4f})")
            return lat, lon
        else:
            logger.warning(f"[OneMap] No results for '{address}'")
            return None, None

    except Exception as e:
        logger.error(f"[OneMap] Error: {e}")
        return None, None
