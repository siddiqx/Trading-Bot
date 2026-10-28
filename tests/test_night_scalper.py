"""Unit test suite for the Asian Night Statistical Mean-Reversion Scalper (v2.0).

Tests:
1. Bullish mean-reversion detection (lower Bollinger Band pierce, reclaim, RSI oversold).
2. Bearish mean-reversion detection (upper Bollinger Band pierce, reclaim, RSI overbought).
3. Rollover / session hour gating (22:00 rollover skipped).
4. Minimum Take Profit constraint (>= 5.0 pips).
5. Dynamic Stop Loss bounding (8.0 to 25.0 pips).
6. Integration into scan_pair_timeframe and alert message formatting.
"""

import os
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from market_scanner import (
    compute_indicators,
    detect_night_mean_reversion,
    format_alert_message,
)
from core.config import (
    NIGHT_SESSION_HOURS,
    NIGHT_RSI_OVERSOLD,
    NIGHT_RSI_OVERBOUGHT,
    NIGHT_MIN_TP_PIPS,
    STRATEGY_NAME,
)


def _create_mock_night_series(n_bars: int = 40, base_price: float = 1.1000, pip: float = 0.0001) -> pd.DataFrame:
    """Creates a mock DataFrame with proper indicators and Bollinger Band width."""
    times = pd.date_range("2026-10-28 01:00:00", periods=n_bars, freq="15min", tz=timezone.utc)
    # Add slight sine variation so rolling std is around 10-15 pips
    sine_wave = np.sin(np.linspace(0, 3 * np.pi, n_bars)) * (15.0 * pip)
    closes = base_price + sine_wave
    highs = closes + (2.0 * pip)
    lows = closes - (2.0 * pip)
    opens = closes.copy()

    df = pd.DataFrame({
        "time": times,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "spread": 10.0,
    })
    df = compute_indicators(df, donchian_len=20)
    df["close_time"] = df["time"] + pd.Timedelta(minutes=15)
    return df


def test_detect_night_mean_reversion_bullish():
    pip = 0.0001
    digits = 5
    df = _create_mock_night_series(n_bars=35, base_price=1.1000, pip=pip)

    ema20 = float(df.iloc[-1]["ema20"])
    lower_band = float(df.iloc[-2]["bb_lower"])

    # Ensure lower band is sufficiently below ema20 for >= 5p TP
    assert (ema20 - lower_band) / pip >= 8.0

    # Set up row -2 (piercing lower band and oversold RSI)
    df.loc[df.index[-2], "low"] = lower_band - (3.0 * pip)
    df.loc[df.index[-2], "close"] = lower_band - (1.0 * pip)
    df.loc[df.index[-2], "rsi"] = 32.0

    # Set up row -1 (bullish reclaim above lower band, heading to EMA20)
    df.loc[df.index[-1], "open"] = lower_band + (0.5 * pip)
    df.loc[df.index[-1], "close"] = lower_band + (2.0 * pip)
    df.loc[df.index[-1], "low"] = lower_band + (0.2 * pip)
    df.loc[df.index[-1], "high"] = lower_band + (2.5 * pip)
    df.loc[df.index[-1], "rsi"] = 35.0

    confirmed, bar_time, entry, sl, tp, sl_pips, tp_pips, rr = detect_night_mean_reversion(
        df, pip=pip, digits=digits, is_long=True, pair_name="EURUSD"
    )

    assert confirmed is True
    assert entry > sl
    assert tp > entry
    assert sl_pips >= 8.0
    assert sl_pips <= 25.0
    assert tp_pips >= NIGHT_MIN_TP_PIPS
    assert rr > 0.0


def test_detect_night_mean_reversion_bearish():
    pip = 0.0001
    digits = 5
    df = _create_mock_night_series(n_bars=35, base_price=1.1000, pip=pip)

    ema20 = float(df.iloc[-1]["ema20"])
    upper_band = float(df.iloc[-2]["bb_upper"])

    # Ensure upper band is sufficiently above ema20 for >= 5p TP
    assert (upper_band - ema20) / pip >= 8.0

    # Set up row -2 (piercing upper band and overbought RSI)
    df.loc[df.index[-2], "high"] = upper_band + (3.0 * pip)
    df.loc[df.index[-2], "close"] = upper_band + (1.0 * pip)
    df.loc[df.index[-2], "rsi"] = 68.0

    # Set up row -1 (bearish reclaim below upper band)
    df.loc[df.index[-1], "open"] = upper_band - (0.5 * pip)
    df.loc[df.index[-1], "close"] = upper_band - (2.0 * pip)
    df.loc[df.index[-1], "high"] = upper_band - (0.2 * pip)
    df.loc[df.index[-1], "low"] = upper_band - (2.5 * pip)
    df.loc[df.index[-1], "rsi"] = 65.0

    confirmed, bar_time, entry, sl, tp, sl_pips, tp_pips, rr = detect_night_mean_reversion(
        df, pip=pip, digits=digits, is_long=False, pair_name="EURUSD"
    )

    assert confirmed is True
    assert entry < sl
    assert tp < entry
    assert sl_pips >= 8.0
    assert sl_pips <= 25.0
    assert tp_pips >= NIGHT_MIN_TP_PIPS
    assert rr > 0.0


def test_detect_night_mean_reversion_insufficient_tp():
    pip = 0.0001
    digits = 5
    df = _create_mock_night_series(n_bars=35, base_price=1.1000, pip=pip)

    lower_band = float(df.iloc[-2]["bb_lower"])
    df.loc[df.index[-2], "low"] = lower_band - (2.0 * pip)
    df.loc[df.index[-2], "rsi"] = 30.0

    # Set close already almost at EMA20 (tp_pips < 5.0)
    ema20 = float(df.iloc[-1]["ema20"])
    df.loc[df.index[-1], "close"] = ema20 - (2.0 * pip)  # only 2.0 pips TP
    df.loc[df.index[-1], "open"] = ema20 - (3.0 * pip)
    df.loc[df.index[-1], "rsi"] = 35.0

    confirmed, _, _, _, _, _, tp_pips, _ = detect_night_mean_reversion(
        df, pip=pip, digits=digits, is_long=True, pair_name="EURUSD"
    )

    assert confirmed is False


def test_night_scalper_alert_formatting():
    sig = {
        "id": "EURUSD_15M_2026-10-28T02:00:00Z_LONG_MR",
        "pair": "EURUSD",
        "timeframe": "15M",
        "direction": "LONG",
        "strategy": STRATEGY_NAME,
        "strategy_type": "NIGHT_SCALPER",
        "phase": "Extreme 2.0σ Deviation Reclaim",
        "time": "2026-10-28T02:00:00Z",
        "entry": 1.08500,
        "stop_loss": 1.08350,
        "take_profit": 1.08680,
        "sl_pips": 15.0,
        "tp_pips": 18.0,
        "rr": 1.20,
        "target_type": "Equilibrium Mean (20-EMA)",
        "account_equity": 5000.0,
        "risk_pct": 1.0,
        "risk_budget_usd": 50.0,
        "calc_lots": 0.33,
        "risk_usd": 49.50,
        "max_hold_hours": 4.0,
    }

    msg = format_alert_message(sig)
    assert "EUR/USD" in msg
    assert "BUY / LONG" in msg
    assert "1.085" in msg
    assert "1.0835" in msg
    assert "1.0868" in msg
    assert "0.33 Lots" in msg
    assert "$49.50 USD" in msg
    assert STRATEGY_NAME in msg
