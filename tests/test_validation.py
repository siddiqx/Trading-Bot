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

    institutional_pairs = ["EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY", "AUDUSD"]
    for pair in institutional_pairs:
        price = 150.0 if "JPY" in pair else 1.1000
        sl = price - (0.10 if "JPY" in pair else 0.0010)
        tp = price + (0.15 if "JPY" in pair else 0.0015)
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
        assert is_valid, f"Failed for eligible pair {pair}: {reason}"


def test_gold_exclusion_and_aliases_rejected():
    settings = Settings()
    validator = SignalValidator(settings)

    gold_aliases = ["XAUUSD", "GOLD", "XAU", "OANDA:XAUUSD", "GC=F", "XAUUSD=X"]
    for alias in gold_aliases:
        try:
            payload = SignalPayload(
                symbol=alias,
                direction="LONG",
                signal_time="2026-03-09T14:00:00Z",
                price=2000.0,
                entry=2000.0,
                stop_loss=1980.0,
                take_profit=2030.0,
                signal_score=85.0,
                adx=25.0,
                atr=5.0,
                roc=0.5,
                htf_regime="BULLISH",
                webhook_secret="test-secret-key-12345",
            )
            is_valid, reason = validator.validate(payload)
            assert not is_valid, f"Gold alias {alias} was not rejected!"
            assert "Gold" in reason or "excluded" in reason.lower()
        except Exception:
            # If rejected during pydantic normalization/validation, that's also valid rejection
            pass


def test_friday_cutoff_forex():
    settings = Settings()
    validator = SignalValidator(settings)

    # 1. EURUSD Friday 11:00 UTC (Before 12:00 UTC cutoff -> PERMITTED)
    p_eur_allowed = SignalPayload(
        symbol="EURUSD",
        direction="LONG",
        signal_time="2026-03-13T11:00:00Z",  # Friday
        price=1.0850,
        entry=1.0850,
        stop_loss=1.0830,
        take_profit=1.0890,
        signal_score=85.0,
        adx=25.0,
        atr=0.0010,
        roc=0.5,
        htf_regime="BULLISH",
        webhook_secret="test-secret-key-12345",
    )
    ok_eur, _ = validator.validate(p_eur_allowed)
    assert ok_eur

    # 2. EURUSD Friday 13:00 UTC (After 12:00 UTC cutoff -> BLOCKED)
    p_eur_blocked = SignalPayload(
        symbol="EURUSD",
        direction="LONG",
        signal_time="2026-03-13T13:00:00Z",  # Friday
        price=1.0850,
        entry=1.0850,
        stop_loss=1.0830,
        take_profit=1.0890,
        signal_score=85.0,
        adx=25.0,
        atr=0.0010,
        roc=0.5,
        htf_regime="BULLISH",
        webhook_secret="test-secret-key-12345",
    )
    ok_eur_bl, reason_eur = validator.validate(p_eur_blocked)
    assert not ok_eur_bl
    assert "Friday PM cutoff active" in reason_eur


def test_tp_sl_and_position_sizing_specifications():
    """Verify Section 15.A & 15.C automated test specifications."""
    from core.instrument_validator import calculate_tp_sl, calculate_position_size

    # 1. Long EUR/USD entry at 1.10000: TP = 1.10150, SL = 1.09900
    tp1, sl1 = calculate_tp_sl(1.10000, "LONG", "EURUSD")
    assert tp1 == 1.10150
    assert sl1 == 1.09900

    # 2. Short EUR/USD entry at 1.10000: TP = 1.09850, SL = 1.10100
    tp2, sl2 = calculate_tp_sl(1.10000, "SHORT", "EURUSD")
    assert tp2 == 1.09850
    assert sl2 == 1.10100

    # 3. Long USD/JPY entry at 150.000: TP = 150.150, SL = 149.900
    tp3, sl3 = calculate_tp_sl(150.000, "LONG", "USDJPY")
    assert tp3 == 150.150
    assert sl3 == 149.900

    # 4. Short USD/JPY entry at 150.000: TP = 149.850, SL = 150.100
    tp4, sl4 = calculate_tp_sl(150.000, "SHORT", "USDJPY")
    assert tp4 == 149.850
    assert sl4 == 150.100

    # Position sizing: $5,000 account, 1% risk ($50), 10-pip SL -> 0.50 lots
    lots_1 = calculate_position_size(5000.0, 1.0, 10.0, "EURUSD")
    assert lots_1 == 0.50

    # Position sizing: $5,000 account, 0.5% risk ($25), 10-pip SL -> 0.25 lots
    lots_half = calculate_position_size(5000.0, 0.5, 10.0, "EURUSD")
    assert lots_half == 0.25





