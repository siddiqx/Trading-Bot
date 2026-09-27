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


def test_unsupported_symbol_rejection():
    settings = Settings()
    validator = SignalValidator(settings)

    payload_data = {
        "symbol": "NZDCHF",  # Unverified non-whitelist pair
        "direction": "LONG",
        "signal_time": "2026-03-09T14:00:00Z",
        "price": 0.5250,
        "entry": 0.5250,
        "stop_loss": 0.5230,
        "take_profit": 0.5290,
        "signal_score": 85.0,
        "adx": 25.0,
        "atr": 0.0010,
        "roc": 0.5,
        "htf_regime": "BULLISH",
        "webhook_secret": "test-secret-key-12345",
    }
    payload = SignalPayload(**payload_data)
    is_valid, reason = validator.validate(payload)
    assert not is_valid
    assert "Not in verified institutional pair whitelist" in reason


def test_institutional_whitelist_pairs_accepted():
    settings = Settings()
    validator = SignalValidator(settings)

    institutional_pairs = ["USDCAD", "USDCHF", "USDJPY", "AUDUSD", "XAUUSD"]
    for pair in institutional_pairs:
        price = 2000.0 if pair == "XAUUSD" else (145.0 if "JPY" in pair else 1.3000)
        sl = price - (5.0 if pair == "XAUUSD" else (0.30 if "JPY" in pair else 0.0020))
        tp = price + (10.0 if pair == "XAUUSD" else (0.60 if "JPY" in pair else 0.0040))
        payload_data = {
            "symbol": pair,
            "direction": "LONG",
            "signal_time": "2026-03-09T14:00:00Z",
            "price": price,
            "entry": price,
            "stop_loss": sl,
            "take_profit": tp,
            "signal_score": 85.0,
            "adx": 25.0,
            "atr": 0.0010,
            "roc": 0.5,
            "htf_regime": "BULLISH",
            "webhook_secret": "test-secret-key-12345",
        }
        payload = SignalPayload(**payload_data)
        is_valid, reason = validator.validate(payload)
        assert is_valid, f"Failed for pair {pair}: {reason}"


def test_gold_toxic_hours_rejection():
    settings = Settings()
    validator = SignalValidator(settings)

    # Hour 04:00 UTC (Pre-London manipulation trap - 0% historical win rate)
    payload_toxic = SignalPayload(
        symbol="XAUUSD",
        direction="LONG",
        signal_time="2026-03-09T04:30:00Z",
        price=2150.0,
        entry=2150.0,
        stop_loss=2130.0,
        take_profit=2185.0,
        signal_score=85.0,
        adx=25.0,
        atr=5.0,
        roc=0.5,
        htf_regime="BULLISH",
        webhook_secret="test-secret-key-12345",
    )
    is_valid, reason = validator.validate(payload_toxic)
    assert not is_valid
    assert "blacklisted manipulation windows" in reason

    # Hour 09:00 UTC (London Open peak momentum - high historical win rate)
    payload_valid = SignalPayload(
        symbol="XAUUSD",
        direction="LONG",
        signal_time="2026-03-09T09:00:00Z",
        price=2150.0,
        entry=2150.0,
        stop_loss=2130.0,
        take_profit=2185.0,
        signal_score=85.0,
        adx=25.0,
        atr=5.0,
        roc=0.5,
        htf_regime="BULLISH",
        webhook_secret="test-secret-key-12345",
    )
    is_valid_ok, reason_ok = validator.validate(payload_valid)
    assert is_valid_ok, f"Failed for valid Gold hour: {reason_ok}"



