"""Test database models and repository functions."""

from app.database.repository import SignalRepository


def test_signal_crud(db_session):
    data = {
        "signal_id": "EURUSD_1710000000_LONG",
        "signal_time": "2026-03-09T12:00:00Z",
        "symbol": "EURUSD",
        "exchange": "OANDA",
        "timeframe": "60",
        "direction": "LONG",
        "entry": 1.08500,
        "stop_loss": 1.08300,
        "take_profit": 1.08900,
        "risk_reward": 2.0,
        "signal_score": 85.0,
        "adx": 26.5,
        "atr": 0.00115,
        "roc": 0.45,
        "htf_regime": "BULLISH",
        "breakout_length": 20,
        "atr_multiplier": 1.75,
        "strategy_version": "1.0.0",
        "environment": "LIVE",
        "status": "ACCEPTED",
    }

    # Create
    signal = SignalRepository.create_signal(db_session, data)
    assert signal.id is not None
    assert signal.signal_id == "EURUSD_1710000000_LONG"
    assert signal.direction == "LONG"
    assert signal.telegram_sent is False

    # Lookup
    fetched = SignalRepository.get_by_signal_id(db_session, "EURUSD_1710000000_LONG")
    assert fetched is not None
    assert fetched.entry == 1.08500

    # Update telegram status
    updated = SignalRepository.update_telegram_status(
        db_session, "EURUSD_1710000000_LONG", sent=True, message_id=12345
    )
    assert updated.telegram_sent is True
    assert updated.telegram_message_id == 12345

    # Stats
    stats = SignalRepository.get_stats(db_session)
    assert stats["total_signals"] == 1
    assert stats["long_signals"] == 1
    assert stats["short_signals"] == 0
    assert stats["live_signals"] == 1
    assert stats["signals_by_pair"].get("EURUSD") == 1
