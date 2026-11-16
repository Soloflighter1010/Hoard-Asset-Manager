"""Public reference rates for optional wishlist estimates; no account or product data is sent."""
from __future__ import annotations
import math
import re
import threading
import time
import requests

URL = "https://api.frankfurter.dev/v1/latest"
_lock = threading.Lock()
_cache = None
_checked = 0.0
_retry_after = 0.0


def validate(raw):
    if not isinstance(raw, dict) or raw.get("base") != "EUR" or not isinstance(raw.get("date"), str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw["date"]):
        raise ValueError("Invalid exchange rates.")
    rates = {"EUR": 1.0}
    for code, value in (raw.get("rates") or {}).items():
        if isinstance(code, str) and re.fullmatch(r"[A-Z]{3}", code) and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0:
            rates[code] = float(value)
    if len(rates) < 2:
        raise ValueError("Invalid exchange rates.")
    return {"base": "EUR", "date": raw["date"], "rates": rates}


def latest():
    """Cache for an hour; retain known rates with a stale flag if a refresh fails."""
    global _cache, _checked, _retry_after
    with _lock:
        if _cache is not None and time.monotonic() - _checked < 3600:
            return {**_cache, "stale": False}
        if time.monotonic() < _retry_after:
            if _cache is not None:
                return {**_cache, "stale": True}
            raise ValueError("Exchange rates are unavailable. Original prices are still shown.")
        try:
            with requests.get(URL, timeout=8, allow_redirects=False, stream=True) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError("No exchange rates returned.")
                content = bytearray()
                for chunk in response.iter_content(8192):
                    content.extend(chunk)
                    if len(content) > 65536:
                        raise ValueError("Exchange response too large.")
                import json
                clean = validate(json.loads(content))
            _cache, _checked, _retry_after = clean, time.monotonic(), 0.0
            return {**clean, "stale": False}
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            _retry_after = time.monotonic() + 60
            if _cache is not None:
                return {**_cache, "stale": True}
            raise ValueError("Exchange rates are unavailable. Original prices are still shown.") from None
