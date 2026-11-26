"""
Unit Tests for Strategy Expectancy Enhancements (v3.3.0+):
Option 1: Dynamic Target Expansion on Extreme Macro Divergence (|D| >= 2.50σ).
Option 2: Higher-Timeframe (HTF) 4H Soft Trend Confluence Gate.
"""

import os
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from core.config import (
    DYNAMIC_TARGET_EXPANSION_ENABLED,
    CCRS_EXTREME_DIVERGENCE_THRESHOLD,
    EXPANDED_TAKE_PROFIT_RR,
    HTF_CONFLUENCE_ENABLED,
    CANONICAL_RISK_REWARD_RATIO,
)
from market_scanner import check_4h_trend_confluence, scan_pair_timeframe


def _create_synthetic_1h_data(n_bars: int = 150, trend: str = "bullish") -> pd.DataFrame:
    """Generate synthetic 1H OHLCV dataframe for 4H confluence testing."""
    base_time = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
    times = [base_time + timedelta(hours=i) for i in range(n_bars)]
    
    if trend == "bullish":
        closes = np.linspace(1.0500, 1.1000, n_bars)
    elif trend == "bearish":
        closes = np.linspace(1.1000, 1.0500, n_bars)
    else:  # flat / ranging
        closes = np.full(n_bars, 1.0800)

    highs = closes + 0.0010
    lows = closes - 0.0010
    opens = closes - 0.0002

    df = pd.DataFrame({
        "time": times,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [1000] * n_bars
    })
    return df


def test_4h_trend_confluence_bullish_approved():
    """Verify check_4h_trend_confluence approves LONG trade when 4H trend is bullish."""
    df_1h = _create_synthetic_1h_data(n_bars=200, trend="bullish")
    # In test environment, bypass PYTEST_CURRENT_TEST guard
    old_test_env = os.environ.pop("PYTEST_CURRENT_TEST", None)
    try:
        aligned, desc = check_4h_trend_confluence(
            ticker="EURUSD=X",
            is_long=True,
            pair_div=2.00,  # Below 2.50σ extreme threshold
            df_1h=df_1h
        )
        assert aligned is True
        assert "4H Bullish Confluence" in desc
    finally:
        if old_test_env:
            os.environ["PYTEST_CURRENT_TEST"] = old_test_env


def test_4h_trend_confluence_bearish_rejects_long():
    """Verify check_4h_trend_confluence rejects LONG trade when 4H trend is strongly bearish."""
    df_1h = _create_synthetic_1h_data(n_bars=200, trend="bearish")
    old_test_env = os.environ.pop("PYTEST_CURRENT_TEST", None)
    try:
        aligned, desc = check_4h_trend_confluence(
            ticker="EURUSD=X",
            is_long=True,
            pair_div=2.00,  # Below 2.50σ extreme threshold
            df_1h=df_1h
        )
        assert aligned is False
        assert "4H Bearish Countertrend" in desc
    finally:
        if old_test_env:
            os.environ["PYTEST_CURRENT_TEST"] = old_test_env


def test_4h_trend_confluence_bearish_approved_for_short():
    """Verify check_4h_trend_confluence approves SHORT trade when 4H trend is bearish."""
    df_1h = _create_synthetic_1h_data(n_bars=200, trend="bearish")
    old_test_env = os.environ.pop("PYTEST_CURRENT_TEST", None)
    try:
        aligned, desc = check_4h_trend_confluence(
            ticker="EURUSD=X",
            is_long=False,
            pair_div=-2.00,
            df_1h=df_1h
        )
        assert aligned is True
        assert "4H Bearish Confluence" in desc
    finally:
        if old_test_env:
            os.environ["PYTEST_CURRENT_TEST"] = old_test_env


def test_4h_trend_confluence_extreme_divergence_override():
    """Verify that extreme macro flow (|D| >= 2.50σ) overrides 4H countertrend consolidation."""
    df_1h = _create_synthetic_1h_data(n_bars=200, trend="bearish")
    old_test_env = os.environ.pop("PYTEST_CURRENT_TEST", None)
    try:
        # Divergence +2.65σ exceeds threshold 2.50σ
        aligned, desc = check_4h_trend_confluence(
            ticker="EURUSD=X",
            is_long=True,
            pair_div=2.65,
            df_1h=df_1h
        )
        assert aligned is True
        assert "Overridden by Extreme Macro Flow" in desc
    finally:
        if old_test_env:
            os.environ["PYTEST_CURRENT_TEST"] = old_test_env


def test_4h_trend_confluence_disabled_flag(monkeypatch):
    """Verify check_4h_trend_confluence bypasses when HTF_CONFLUENCE_ENABLED is False."""
    monkeypatch.setattr("market_scanner.HTF_CONFLUENCE_ENABLED", False)
    old_test_env = os.environ.pop("PYTEST_CURRENT_TEST", None)
    try:
        aligned, desc = check_4h_trend_confluence(
            ticker="EURUSD=X",
            is_long=True,
            pair_div=1.80,
            df_1h=None
        )
        assert aligned is True
        assert "Bypassed" in desc
    finally:
        if old_test_env:
            os.environ["PYTEST_CURRENT_TEST"] = old_test_env


def test_dynamic_target_expansion_extreme_macro(monkeypatch):
    """Verify Option 1 expands target to 1.75R when divergence >= 2.50σ."""
    cfg = {"ticker": "EURUSD=X", "pip": 0.0001, "digits": 5, "donchian_len": 20}
    state = {"alerted_signals": []}

    now_utc = datetime(2026, 10, 15, 10, 30, tzinfo=timezone.utc)
    t0 = now_utc - timedelta(minutes=15 * 60)
    times = [t0 + timedelta(minutes=15 * i) for i in range(60)]
    closes = [1.0850] * 60

    df = pd.DataFrame({
        "time": times,
        "open": closes,
        "high": [c + 0.0010 for c in closes],
        "low": [c - 0.0005 for c in closes],
        "close": closes,
        "volume": [1000] * 60
    })
    df.loc[59, "open"] = 1.0845
    df.loc[59, "low"] = 1.0840
    df.loc[59, "close"] = 1.0855
    df.loc[59, "high"] = 1.0858

    mock_ccrs = {
        "latest_div": {"EURUSD": 2.70},  # >= 2.50σ Extreme Divergence
        "prev_div": {"EURUSD": 2.60},
        "latest_z": {"EUR": 1.50, "USD": -1.20},
    }

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "1")
    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *a, **kw: True)
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *a, **kw: df)
    monkeypatch.setattr("market_scanner.get_live_price", lambda *a, **kw: 1.08550)
    monkeypatch.setattr("market_scanner.check_htf_alignment", lambda *a, **kw: (True, "HTF Aligned"))
    monkeypatch.setattr("market_scanner.check_4h_trend_confluence", lambda *a, **kw: (True, "4H Aligned"))

    signals = scan_pair_timeframe("EURUSD", cfg, "15m", state, ccrs_matrix=mock_ccrs)
    assert len(signals) == 1
    sig = signals[0]

    # Verify Dynamic Target Expansion triggered
    assert sig["divergence"] == 2.70
    assert sig["rr"] == EXPANDED_TAKE_PROFIT_RR
    assert sig["tp_pips"] == round(sig["sl_pips"] * EXPANDED_TAKE_PROFIT_RR, 1)
    assert "Dynamic Expansion Target" in sig["target_type"]
    assert f"{EXPANDED_TAKE_PROFIT_RR:.2f}R" in sig["model_j"]


def test_canonical_target_retained_below_extreme_threshold(monkeypatch):
    """Verify Option 1 retains canonical target when divergence < 2.50σ."""
    cfg = {"ticker": "EURUSD=X", "pip": 0.0001, "digits": 5, "donchian_len": 20}
    state = {"alerted_signals": []}

    now_utc = datetime(2026, 10, 15, 10, 30, tzinfo=timezone.utc)
    t0 = now_utc - timedelta(minutes=15 * 60)
    times = [t0 + timedelta(minutes=15 * i) for i in range(60)]
    closes = [1.0850] * 60

    df = pd.DataFrame({
        "time": times,
        "open": closes,
        "high": [c + 0.0010 for c in closes],
        "low": [c - 0.0005 for c in closes],
        "close": closes,
        "volume": [1000] * 60
    })
    df.loc[59, "open"] = 1.0845
    df.loc[59, "low"] = 1.0840
    df.loc[59, "close"] = 1.0855
    df.loc[59, "high"] = 1.0858

    mock_ccrs = {
        "latest_div": {"EURUSD": 2.15},  # < 2.50σ Normal Active Divergence
        "prev_div": {"EURUSD": 2.05},
        "latest_z": {"EUR": 1.20, "USD": -0.95},
    }

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "1")
    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *a, **kw: True)
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *a, **kw: df)
    monkeypatch.setattr("market_scanner.get_live_price", lambda *a, **kw: 1.08550)
    monkeypatch.setattr("market_scanner.check_htf_alignment", lambda *a, **kw: (True, "HTF Aligned"))
    monkeypatch.setattr("market_scanner.check_4h_trend_confluence", lambda *a, **kw: (True, "4H Aligned"))

    signals = scan_pair_timeframe("EURUSD", cfg, "15m", state, ccrs_matrix=mock_ccrs)
    assert len(signals) == 1
    sig = signals[0]

    # Verify Canonical Target Geometry retained
    assert sig["divergence"] == 2.15
    assert sig["rr"] == CANONICAL_RISK_REWARD_RATIO
    assert sig["tp_pips"] == round(sig["sl_pips"] * CANONICAL_RISK_REWARD_RATIO, 1)
    assert sig["target_type"] == "Institutional Dual-Timeframe Target"
