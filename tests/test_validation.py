"""Tests for strategy validation and filtering mechanisms."""

from app.config import Settings
from app.schemas.signal import SignalPayload
from app.services.validation import SignalValidator, SessionFilter, NewsFilter


def test_adx_threshold_validation():
    settings = Settings(DEFAULT_ADX_MIN=20.0)
    validator = SignalValidator(settings)

    payload_data = {
        "symbol": "EURUSD",
        "direction": "LONG",
        "signal_time": "2026-03-09T14:00:00Z",
        "price": 1.0850,
        "entry": 1.0850,
        "stop_loss": 1.0830,
        "take_profit": 1.0890,
        "signal_score": 75.0,
        "adx": 15.0,  # Below 20.0
        "atr": 0.0010,
        "roc": 0.5,
        "htf_regime": "BULLISH",
        "webhook_secret": "test-secret-key-12345",
    }
    payload = SignalPayload(**payload_data)
    is_valid, reason = validator.validate(payload)
    assert not is_valid
    assert "below minimum threshold" in reason


def test_signal_score_validation():
    settings = Settings(MIN_SIGNAL_SCORE=70.0)
    validator = SignalValidator(settings)

    payload_data = {
        "symbol": "EURUSD",
        "direction": "LONG",
        "signal_time": "2026-03-09T14:00:00Z",
        "price": 1.0850,
        "entry": 1.0850,
        "stop_loss": 1.0830,
        "take_profit": 1.0890,
        "signal_score": 55.0,  # Below 70.0
        "adx": 25.0,
        "atr": 0.0010,
        "roc": 0.5,
        "htf_regime": "BULLISH",
        "webhook_secret": "test-secret-key-12345",
    }
    payload = SignalPayload(**payload_data)
    is_valid, reason = validator.validate(payload)
    assert not is_valid
    assert "below minimum acceptable quality" in reason


def test_session_filter_evaluation():
    # 14:00 UTC is London/NY overlap
    permitted, reason = SessionFilter.is_session_permitted("2026-03-09T14:00:00Z", ["LONDON", "OVERLAP"])
    assert permitted

    # 22:00 UTC is outside standard London/NY
    permitted_late, reason_late = SessionFilter.is_session_permitted("2026-03-09T22:00:00Z", ["LONDON", "NEW_YORK"])
    assert not permitted_late
