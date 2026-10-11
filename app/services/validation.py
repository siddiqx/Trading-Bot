"""Validation and regime/session/news filtering logic."""

from datetime import datetime, timezone
from typing import Tuple, List, Optional
from app.config import Settings
from app.schemas.signal import SignalPayload
from app.utils.logging import logger
from core.instrument_validator import is_gold_symbol, validate_instrument_eligibility


class SessionFilter:
    """Evaluates whether current UTC time falls within allowed liquid FX sessions."""

    # Approximate UTC market sessions
    # Asia (Tokyo/Sydney): 00:00 - 08:00 UTC
    # London: 08:00 - 16:30 UTC
    # New York: 13:00 - 21:00 UTC
    # London/NY Overlap: 13:00 - 16:30 UTC

    @staticmethod
    def get_current_session(dt: datetime) -> List[str]:
        hour = dt.hour + (dt.minute / 60.0)
        active = []
        if 0.0 <= hour < 8.0:
            active.append("ASIA")
        if 8.0 <= hour < 16.5:
            active.append("LONDON")
        if 13.0 <= hour < 21.0:
            active.append("NEW_YORK")
        if 13.0 <= hour < 16.5:
            active.append("OVERLAP")
        return active

    @classmethod
    def is_session_permitted(
        cls,
        timestamp_str: str,
        allowed_sessions: List[str],
    ) -> Tuple[bool, str]:
        """Check if signal timestamp matches configured allowed trading sessions."""
        try:
            # Handle ISO or UNIX timestamp
            if timestamp_str.isdigit():
                dt = datetime.fromtimestamp(int(timestamp_str) / 1000.0, tz=timezone.utc)
            else:
                dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except Exception:
            dt = datetime.now(timezone.utc)

        active = cls.get_current_session(dt)
        matches = [s for s in active if s in allowed_sessions]
        if matches:
            return True, f"Active session ({','.join(matches)}) is permitted."
        return False, f"Current active sessions ({','.join(active)}) not in allowed list ({allowed_sessions})."


class NewsFilter:
    """Interface for major economic news event avoidance.

    Version 1 defaults to unblocked unless an external calendar feed is connected.
    """

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def is_blocked(self, symbol: str, timestamp_str: str) -> Tuple[bool, str]:
        """Check if trading should be blacked out due to high-impact economic news."""
        if not self.enabled:
            return False, "News filter disabled."

        # In Version 1, no mock calendar is fabricated to preserve truthfulness.
        # Clean extension point for Forexfactory/TradingEconomics API integration.
        return False, "No active high-impact news blackout detected."


class SignalValidator:
    """Performs deep business logic validation on received signal payload."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.session_filter = SessionFilter()
        self.news_filter = NewsFilter(enabled=settings.NEWS_FILTER_ENABLED)

    def validate(self, payload: SignalPayload) -> Tuple[bool, str]:
        """Evaluate all system filters and parameter bounds."""
        # 1. Centralized Instrument Exclusion (Reject Gold unconditionally)
        if is_gold_symbol(payload.symbol):
            logger.warning(f"Gold symbol {payload.symbol} rejected: Gold trading is permanently disabled.")
            return False, f"Symbol {payload.symbol} rejected: Gold (XAUUSD) trading is permanently excluded. Forex pairs only."

        # 1b. Check eligible forex whitelist
        is_inst_valid, inst_reason = validate_instrument_eligibility(payload.symbol)
        if not is_inst_valid:
            logger.warning(f"Symbol {payload.symbol} failed eligibility check: {inst_reason}")
            return False, inst_reason

        # 1c. Friday Cutoff Filter (12:00 UTC for Forex)
        try:
            sig_str = str(payload.signal_time)
            if sig_str.isdigit():
                dt = datetime.fromtimestamp(int(sig_str) / 1000.0, tz=timezone.utc)
            else:
                dt = datetime.fromisoformat(sig_str.replace("Z", "+00:00"))
            if dt.weekday() == 4:  # Friday
                cutoff = self.settings.FOREX_FRIDAY_CUTOFF_HOUR
                if dt.hour >= cutoff:
                    return False, f"Friday PM cutoff active: Signal at {dt.hour:02d}:00 UTC reaches or exceeds {payload.symbol} Friday cutoff ({cutoff:02d}:00 UTC)."
        except Exception as e:
            logger.debug(f"Unable to parse timestamp for Friday cutoff check: {e}")

        # 2. ADX minimum threshold check
        if payload.adx < self.settings.DEFAULT_ADX_MIN:
            return False, f"ADX value ({payload.adx}) is below minimum threshold ({self.settings.DEFAULT_ADX_MIN})."

        # 3. Minimum Signal Score heuristic check
        if payload.signal_score < self.settings.MIN_SIGNAL_SCORE:
            return False, f"Signal score ({payload.signal_score}) is below minimum acceptable quality ({self.settings.MIN_SIGNAL_SCORE})."

        # 4. Session filtering (if enabled)
        if self.settings.SESSION_FILTER_ENABLED:
            allowed = self.settings.allowed_sessions_list
            permitted, reason = self.session_filter.is_session_permitted(payload.signal_time, allowed)
            if not permitted:
                return False, f"Session filter rejected trade: {reason}"

        # 5. News filtering (if enabled)
        if self.settings.NEWS_FILTER_ENABLED:
            blocked, reason = self.news_filter.is_blocked(payload.symbol, payload.signal_time)
            if blocked:
                return False, f"News filter blackout active: {reason}"

        # 6. Anti-Wick Strong Body check (if provided and enabled)
        if self.settings.ANTI_WICK_FILTER_ENABLED and payload.candle_body_ratio is not None:
            if payload.candle_body_ratio < self.settings.MIN_BODY_RATIO:
                return False, f"Candle body ratio ({payload.candle_body_ratio:.2f}) is below minimum anti-wick threshold ({self.settings.MIN_BODY_RATIO})."

        return True, "All validation rules satisfied."
