"""
Gemini Flash NLU — extract structured place, activity, time from user queries.

Returns a dict with:
  - place: normalized place name (e.g. "Botanic Gardens")
  - activity: activity name (e.g. "Cycling") or None
  - time_ref: time reference string (e.g. "tonight", "2pm to 5pm") or None
  - start_hour / end_hour: parsed integers or None

Falls back gracefully: if Gemini is unavailable, returns None so caller
can use regex fallback.
"""
import os
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Load .env from services/api/.env (two levels up from backend/)
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
        logger.debug(f"Loaded .env from {_env_path}")
except ImportError:
    pass

_client = None
_available = None  # tri-state: None = not checked, True/False


def _get_client():
    """Lazy-init Gemini client. Returns None if unavailable."""
    global _client, _available

    if _available is False:
        return None
    if _client is not None:
        return _client

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.info("GEMINI_API_KEY not set — NLU will use regex fallback")
        _available = False
        return None

    try:
        from google import genai
        _client = genai.Client(api_key=api_key)
        _available = True
        logger.info("Gemini Flash NLU initialized (google-genai SDK)")
        return _client
    except Exception as e:
        logger.warning(f"Failed to init Gemini: {e}")
        _available = False
        return None


SYSTEM_PROMPT = """You are a query parser for a Singapore weather app. Extract structured info from user queries.

Rules:
- "place" must be a canonical Singapore place name (proper case, no prefixes like "forecast for", no time words). Examples: "Botanic Gardens", "East Coast Park", "Changi Airport", "Clementi", "Marina Bay Sands".
- If no specific place is mentioned, use null.
- "activity" should be one of: Cycling, Running, Walking, Hiking, Picnic, or null if none mentioned.
- "time_ref" is the raw time expression (e.g. "tonight", "tomorrow 3pm", "2 to 5pm"), or null if none.
- "start_hour" and "end_hour" are 24h integers derived from time_ref. Use current time context if needed.

Respond ONLY with valid JSON, no markdown fences:
{"place": "...", "activity": "...", "time_ref": "...", "start_hour": N, "end_hour": N}"""


def extract(query: str) -> dict | None:
    """
    Call Gemini Flash to extract place/activity/time from a user query.
    Returns parsed dict or None on failure (caller should fall back to regex).
    """
    client = _get_client()
    if client is None:
        return None

    now = datetime.now()
    user_msg = f"Current time: {now.strftime('%Y-%m-%d %H:%M')} SGT\nQuery: {query}"

    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=SYSTEM_PROMPT + "\n\n" + user_msg,
            config={
                "temperature": 0.0,
                "max_output_tokens": 200,
            },
        )
        text = resp.text.strip()
        # Strip markdown fences (```json ... ```) that Gemini 2.5 often adds
        if text.startswith("```"):
            # Remove opening fence line (```json or ```)
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        parsed = json.loads(text)
        logger.debug(f"Gemini NLU: {query!r} → {parsed}")
        return parsed

    except Exception as e:
        logger.warning(f"Gemini NLU failed for {query!r}: {e}")
        return None
