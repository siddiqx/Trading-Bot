"""
Unit tests for Quantitative Trade Chart Generator (core/chart_generator.py)
and multi-channel photo dispatching in market_scanner.py.
"""

import numpy as np
import pandas as pd
import pytest

from core.chart_generator import generate_trade_chart
from market_scanner import _safe_send_telegram_photo, send_telegram_photo


@pytest.fixture
def sample_ohlcv_df():
    """Generates a synthetic 50-bar 15M OHLCV dataset."""
    dates = pd.date_range("2026-11-27 10:00", periods=50, freq="15min")
    prices = 1.0850 + np.cumsum(np.random.normal(0, 0.0002, 50))
    return pd.DataFrame({
        "open": prices,
        "high": prices + 0.0004,
        "low": prices - 0.0004,
        "close": prices + 0.0001,
        "volume": [1000] * 50
    }, index=dates)


def test_generate_trade_chart_long(sample_ohlcv_df):
    """Verify that a LONG trade chart renders valid PNG bytes with TradingView styling."""
    sig = {
        "pair": "EURUSD",
        "direction": "LONG",
        "entry": 1.08500,
        "stop_loss": 1.08280,
        "take_profit": 1.08830,
        "sl_pips": 22.0,
        "tp_pips": 33.0,
        "rr": 1.50,
        "timeframe": "15M"
    }
    png_bytes = generate_trade_chart(sample_ohlcv_df, sig, trade_status="OPEN")
    assert png_bytes is not None
    assert isinstance(png_bytes, bytes)
    # Check PNG magic signature: \x89PNG\r\n\x1a\n
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png_bytes) > 20000


def test_generate_trade_chart_short(sample_ohlcv_df):
    """Verify that a SHORT trade chart renders valid PNG bytes."""
    sig = {
        "pair": "USDCAD",
        "direction": "SHORT",
        "entry": 1.38500,
        "stop_loss": 1.38720,
        "take_profit": 1.38170,
        "sl_pips": 22.0,
        "tp_pips": 33.0,
        "rr": 1.50,
        "timeframe": "15M"
    }
    png_bytes = generate_trade_chart(sample_ohlcv_df, sig, trade_status="OPEN")
    assert png_bytes is not None
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png_bytes) > 20000


def test_generate_trade_chart_tp_hit(sample_ohlcv_df):
    """Verify that a TAKE PROFIT resolution chart renders properly."""
    sig = {
        "pair": "USDCHF",
        "direction": "LONG",
        "entry": 0.88500,
        "stop_loss": 0.88300,
        "take_profit": 0.88850,
        "sl_pips": 20.0,
        "tp_pips": 35.0,
        "rr": 1.75,
        "timeframe": "15M"
    }
    png_bytes = generate_trade_chart(sample_ohlcv_df, sig, trade_status="TP_HIT")
    assert png_bytes is not None
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_generate_trade_chart_market_outlook(sample_ohlcv_df):
    """Verify that a higher-timeframe MARKET OUTLOOK chart renders properly."""
    sig = {
        "pair": "EURUSD",
        "timeframe": "4H",
        "direction": "NEUTRAL"
    }
    png_bytes = generate_trade_chart(sample_ohlcv_df, sig, trade_status="OUTLOOK")
    assert png_bytes is not None
    assert isinstance(png_bytes, bytes)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png_bytes) > 20000


def test_generate_trade_chart_empty_df():
    """Verify graceful handling when dataframe is empty or None."""
    sig = {"pair": "EURUSD", "direction": "LONG"}
    assert generate_trade_chart(pd.DataFrame(), sig) is None
    assert generate_trade_chart(None, sig) is None


def test_send_telegram_photo_test_mode():
    """Verify send_telegram_photo safely returns True in pytest test mode without network call."""
    res = send_telegram_photo(b"dummy_png", "Test Caption")
    assert res is True


def test_safe_send_telegram_photo_fallback(monkeypatch):
    """Verify _safe_send_telegram_photo gracefully falls back to text when photo_bytes is None."""
    calls = []

    def mock_safe_send_alert(text, **kwargs):
        calls.append(text)
        return True

    monkeypatch.setattr("market_scanner._safe_send_telegram_alert", mock_safe_send_alert)

    res = _safe_send_telegram_photo(None, "Fallback text message")
    assert res is True
    assert len(calls) == 1
    assert calls[0] == "Fallback text message"
