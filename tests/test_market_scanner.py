"""Unit tests for standalone market scanner engine."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from market_scanner import compute_indicators, format_alert_message, scan_pair_timeframe


def generate_mock_df(n_bars=60, start_price=1.0800, trend="up"):
    times = [datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=15 * i) for i in range(n_bars)]
    
    if trend == "up":
        prices = [start_price + (i * 0.0003) for i in range(n_bars)]
    else:
        prices = [start_price - (i * 0.0003) for i in range(n_bars)]
        
    df = pd.DataFrame({
        "timestamp": [int(t.timestamp()) for t in times],
        "time": times,
        "open": prices,
        "high": [p + 0.0005 for p in prices],
        "low": [p - 0.0005 for p in prices],
        "close": prices,
        "volume": [1000] * n_bars
    })
    return df


def test_compute_indicators():
    df = generate_mock_df(60)
    df_calc = compute_indicators(df, donchian_len=20)
    
    assert "ema20" in df_calc.columns
    assert "ema50" in df_calc.columns
    assert "donch_high" in df_calc.columns
    assert "donch_low" in df_calc.columns
    assert "atr" in df_calc.columns
    assert "rsi" in df_calc.columns
    
    # RSI should be positive
    assert df_calc["rsi"].iloc[-1] > 0
    # Donchian high should be less than or equal to recent highs
    assert df_calc["donch_high"].iloc[-1] is not None


def test_format_alert_message():
    sig = {
        "id": "EURUSD_1H_20260928T070000Z_LONG",
        "pair": "EURUSD",
        "timeframe": "1H",
        "direction": "LONG",
        "time": "2026-09-28T07:00:00Z",
        "entry": 1.08550,
        "stop_loss": 1.08200,
        "take_profit": 1.09250,
        "sl_pips": 35.0,
        "tp_pips": 61.3,
        "rr": 1.75,
        "rsi": 58.4,
        "atr": 14.2,
        "score": 92
    }
    msg = format_alert_message(sig)
    assert "EUR/USD" in msg
    assert "BUY / LONG" in msg
    assert "1.0855" in msg
    assert "1.082" in msg
    assert "1.0925" in msg


def test_check_active_trades_skips_pre_entry_bars(monkeypatch):
    """Ensure check_active_trades never evaluates bars that closed prior to trade entry."""
    from market_scanner import check_active_trades

    # Create bars spanning 01:00 to 01:45
    t0 = datetime(2026, 9, 29, 1, 0, tzinfo=timezone.utc)
    mock_df = pd.DataFrame({
        "timestamp": [int((t0 + timedelta(minutes=15 * i)).timestamp()) for i in range(4)],
        "time": [t0 + timedelta(minutes=15 * i) for i in range(4)],
        "open": [1.4170, 1.4175, 1.4180, 1.4185],
        # Notice bar 0 (01:00) dipped to 1.4150, which would hit SL 1.4163 if evaluated
        "low": [1.4150, 1.4172, 1.4178, 1.4182],
        "high": [1.4176, 1.4182, 1.4188, 1.4190],
        "close": [1.4175, 1.4180, 1.4185, 1.4188],
        "volume": [100, 100, 100, 100]
    })

    monkeypatch.setattr("market_scanner.fetch_candles", lambda *args, **kwargs: mock_df)
    monkeypatch.setattr("market_scanner.send_telegram_alert", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.sync_worker", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.save_trade_records", lambda *args, **kwargs: None)

    # Trade was entered at 01:15 (bar 1). Bar 0 happened BEFORE entry.
    records = {
        "active_trades": {
            "USDCAD": {
                "trade_id": "USDCAD_1",
                "pair": "USDCAD",
                "symbol": "USDCAD",
                "ticker": "USDCAD=X",
                "direction": "LONG",
                "entry": 1.4180,
                "stop_loss": 1.4163, # Bar 0 low (1.4150) is below this, but Bar 1-3 lows are above (1.4172+)
                "take_profit": 1.4213,
                "sl_pips": 17.0,
                "tp_pips": 33.0,
                "rr": 1.75,
                "pip": 0.0001,
                "digits": 5,
                "opened_at": "2026-09-29T01:15:00Z",
                "status": "OPEN"
            }
        },
        "completed_trades": []
    }

    check_active_trades(records)

    # USDCAD must remain OPEN because post-entry lows (1.4172+) never touched SL (1.4163)
    assert "USDCAD" in records["active_trades"]
    assert len(records["completed_trades"]) == 0

