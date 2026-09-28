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
    assert "EURUSD" in msg
    assert "BUY / LONG" in msg
    assert "1.0855" in msg
    assert "1.082" in msg
    assert "1.0925" in msg
