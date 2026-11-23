"""Institutional Real-Time Economic News Filter.

Fetches and caches High-Impact macroeconomic events (Forex Factory API).
Enforces trading pauses around major volatility catalysts (NFP, CPI, FOMC, Rate Decisions)
to protect proprietary trading firm accounts from spread blowouts and slippage spikes.
"""

import json
import logging
import os
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any

from core.config import (
    NEWS_FILTER_ENABLED,
    NEWS_FILTER_BUFFER_MINUTES,
    FLASH_PMI_BUFFER_MINUTES,
    NEWS_CALENDAR_URL,
)

logger = logging.getLogger("NewsFilter")

# Cache to avoid excessive API requests (TTL: 15 minutes)
_CALENDAR_CACHE: List[Dict[str, Any]] = []
_CACHE_TIMESTAMP: Optional[datetime] = None
_CACHE_TTL_SECONDS = 900  # 15 minutes


def fetch_economic_calendar(calendar_url: str = NEWS_CALENDAR_URL, force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Fetch high-impact calendar events with in-memory and disk fallback caching."""
    global _CALENDAR_CACHE, _CACHE_TIMESTAMP
    now = datetime.now(timezone.utc)

    if not force_refresh and _CACHE_TIMESTAMP and (now - _CACHE_TIMESTAMP).total_seconds() < _CACHE_TTL_SECONDS:
        return _CALENDAR_CACHE

    try:
        req = urllib.request.Request(
            calendar_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) InstitutionalBot/3.3"}
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
            if isinstance(data, list):
                _CALENDAR_CACHE = data
                _CACHE_TIMESTAMP = now
                logger.info(f"Updated economic calendar cache with {len(data)} events.")
                try:
                    os.makedirs("data", exist_ok=True)
                    with open("data/ff_calendar_cache.json", "w", encoding="utf-8") as f:
                        json.dump(data, f)
                except Exception:
                    pass
                return _CALENDAR_CACHE
    except Exception as ex:
        logger.warning(f"Could not refresh economic calendar from {calendar_url}: {ex}. Using cached data if available.")
        if _CALENDAR_CACHE:
            return _CALENDAR_CACHE
        # Secondary fallback: restore from persistent disk cache
        try:
            if os.path.exists("data/ff_calendar_cache.json"):
                with open("data/ff_calendar_cache.json", "r", encoding="utf-8") as f:
                    disk_data = json.load(f)
                    if isinstance(disk_data, list) and disk_data:
                        _CALENDAR_CACHE = disk_data
                        _CACHE_TIMESTAMP = now
                        logger.info(f"Loaded {len(disk_data)} calendar events from disk fallback cache.")
                        return _CALENDAR_CACHE
        except Exception:
            pass

    return []


def parse_event_time(date_str: str) -> Optional[datetime]:
    """Parse ISO 8601 date string to timezone-aware UTC datetime."""
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def is_news_window_active(
    pair: str,
    now_utc: Optional[datetime] = None,
    buffer_minutes: int = NEWS_FILTER_BUFFER_MINUTES,
    events: Optional[List[Dict[str, Any]]] = None
) -> Tuple[bool, str]:
    """Check whether a High-Impact news event or Flash PMI release is within the buffer window.

    Args:
        pair: 6-character Forex pair symbol (e.g. 'EURUSD', 'USDJPY').
        now_utc: Reference UTC datetime (defaults to current UTC time).
        buffer_minutes: Minutes before and after the event to suppress trading.
        events: Optional pre-loaded calendar event list (used in backtests and mocks).

    Returns:
        Tuple of (is_active: bool, reason: str).
    """
    if not NEWS_FILTER_ENABLED:
        return False, ""

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    clean_pair = pair.replace("=X", "").upper()
    if len(clean_pair) < 6:
        return False, ""

    base_curr = clean_pair[:3]
    quote_curr = clean_pair[3:6]
    target_currencies = {base_curr, quote_curr}

    calendar_events = events if events is not None else fetch_economic_calendar()

    for ev in calendar_events:
        impact = str(ev.get("impact") or "")
        title = str(ev.get("title") or "")
        title_lower = title.lower()

        is_high = (impact == "High")
        is_flash_pmi = ("flash" in title_lower and "pmi" in title_lower)

        # Suppress trading for High-Impact macro events and high-volatility preliminary Flash PMIs.
        # Regular Medium/Low events (consumer sentiment, wholesale trade, PPI sub-indices, etc.)
        # are intentionally ignored to guarantee zero impact on trade frequency during regular market days.
        if not (is_high or is_flash_pmi):
            continue

        country = str(ev.get("country") or "").upper()
        if country not in target_currencies:
            continue

        date_raw = ev.get("date")
        if not date_raw:
            continue

        ev_time = parse_event_time(date_raw)
        if not ev_time:
            continue

        # Flash PMIs often spark institutional positioning up to 45 minutes prior to release
        # (e.g., French Flash PMI at 08:15 UTC affecting the 07:30 UTC London open candle).
        effective_buffer = max(buffer_minutes, FLASH_PMI_BUFFER_MINUTES) if is_flash_pmi else buffer_minutes
        buffer_delta = timedelta(minutes=effective_buffer)

        # Check window: [ev_time - buffer, ev_time + buffer]
        start_win = ev_time - buffer_delta
        end_win = ev_time + buffer_delta

        if start_win <= now_utc <= end_win:
            diff_min = int((ev_time - now_utc).total_seconds() / 60)
            event_type = "Flash PMI Release" if (is_flash_pmi and not is_high) else "High-Impact News"
            if diff_min > 0:
                reason = f"{event_type} '{title}' ({country}) in {diff_min}m"
            elif diff_min < 0:
                reason = f"{event_type} '{title}' ({country}) occurred {abs(diff_min)}m ago"
            else:
                reason = f"{event_type} '{title}' ({country}) releasing right now"
            return True, reason

    return False, ""
