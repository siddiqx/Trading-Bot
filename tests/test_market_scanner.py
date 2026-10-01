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


def test_check_active_trades_pending_order_fill(monkeypatch):
    """Ensure a PENDING trade transitions to OPEN when price touches entry price."""
    from market_scanner import check_active_trades

    t0 = datetime(2026, 9, 30, 15, 30, tzinfo=timezone.utc)
    # Candle 0 touches entry (high touches 4187.90), but stays above SL
    mock_df = pd.DataFrame({
        "timestamp": [int(t0.timestamp())],
        "time": [t0],
        "open": [4185.00],
        "high": [4188.50], # Touches entry 4187.90
        "low": [4184.00],
        "close": [4186.00],
        "volume": [100]
    })

    alerts = []
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *args, **kwargs: mock_df)
    monkeypatch.setattr("market_scanner.send_telegram_alert", lambda msg: alerts.append(msg))
    monkeypatch.setattr("market_scanner.sync_worker", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.save_trade_records", lambda *args, **kwargs: None)

    records = {
        "active_trades": {
            "XAUUSD": {
                "trade_id": "XAUUSD_TEST_1",
                "pair": "XAUUSD",
                "symbol": "XAUUSD",
                "ticker": "GC=F",
                "direction": "SHORT",
                "entry": 4187.90,
                "stop_loss": 4220.28,
                "take_profit": 4131.23,
                "sl_pips": 323.8,
                "tp_pips": 566.7,
                "rr": 1.75,
                "pip": 0.1,
                "digits": 2,
                "opened_at": "2026-09-30T15:30:00Z",
                "status": "PENDING",
                "filled_at": None
            }
        },
        "completed_trades": []
    }

    check_active_trades(records)

    trade = records["active_trades"]["XAUUSD"]
    assert trade["status"] == "OPEN"
    assert trade["filled_at"] is not None
    assert any("ORDER FILLED" in a for a in alerts)


def test_check_active_trades_pending_order_cancellation(monkeypatch):
    """Ensure a PENDING trade is CANCELLED with 0 loss if price hits SL before ever touching entry."""
    from market_scanner import check_active_trades

    t0 = datetime(2026, 9, 30, 15, 30, tzinfo=timezone.utc)
    # Candle breaches SL (4220.28) without touching entry (4187.90) for SHORT
    mock_df = pd.DataFrame({
        "timestamp": [int(t0.timestamp())],
        "time": [t0],
        "open": [4200.00],
        "high": [4225.00], # Breaches SL 4220.28
        "low": [4195.00],  # Never touches 4187.90
        "close": [4210.00],
        "volume": [100]
    })

    alerts = []
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *args, **kwargs: mock_df)
    monkeypatch.setattr("market_scanner.send_telegram_alert", lambda msg: alerts.append(msg))
    monkeypatch.setattr("market_scanner.sync_worker", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.save_trade_records", lambda *args, **kwargs: None)

    records = {
        "active_trades": {
            "XAUUSD": {
                "trade_id": "XAUUSD_TEST_2",
                "pair": "XAUUSD",
                "symbol": "XAUUSD",
                "ticker": "GC=F",
                "direction": "SHORT",
                "entry": 4187.90,
                "stop_loss": 4220.28,
                "take_profit": 4131.23,
                "sl_pips": 323.8,
                "tp_pips": 566.7,
                "rr": 1.75,
                "pip": 0.1,
                "digits": 2,
                "opened_at": "2026-09-30T15:30:00Z",
                "status": "PENDING",
                "filled_at": None
            }
        },
        "completed_trades": []
    }

    check_active_trades(records)

    assert "XAUUSD" not in records["active_trades"]
    assert len(records["completed_trades"]) == 1
    cancelled = records["completed_trades"][0]
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["outcome"] == "CANCELLED"
    assert cancelled["realized_pips"] == 0.0
    assert cancelled["realized_r"] == 0.0
    assert any("SETUP CANCELLED" in a for a in alerts)


def test_check_active_trades_pending_order_timeout(monkeypatch):
    """Ensure an unfilled PENDING order automatically expires after session limit without loss."""
    from market_scanner import check_active_trades

    old_time_dt = datetime.now(timezone.utc) - timedelta(hours=5)
    old_time = old_time_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    t0 = old_time_dt + timedelta(minutes=15)

    # Mock candle data where price stays below entry and SL for SHORT (no fill, no breach)
    mock_df = pd.DataFrame({
        "timestamp": [int(t0.timestamp())],
        "time": [t0],
        "open": [4180.00],
        "high": [4185.00], # Stays below limit entry 4187.90 (unfilled)
        "low": [4175.00],  # Stays above TP 4131.23
        "close": [4180.00],
        "volume": [100]
    })

    alerts = []
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *args, **kwargs: mock_df)
    monkeypatch.setattr("market_scanner.send_telegram_alert", lambda msg: alerts.append(msg))
    monkeypatch.setattr("market_scanner.sync_worker", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.save_trade_records", lambda *args, **kwargs: None)

    records = {
        "active_trades": {
            "XAUUSD": {
                "trade_id": "XAUUSD_TIMEOUT_TEST",
                "pair": "XAUUSD",
                "symbol": "XAUUSD",
                "ticker": "GC=F",
                "direction": "SHORT",
                "timeframe": "15M",
                "entry": 4187.90,
                "stop_loss": 4220.28,
                "take_profit": 4131.23,
                "sl_pips": 323.8,
                "tp_pips": 566.7,
                "rr": 1.75,
                "pip": 0.1,
                "digits": 2,
                "opened_at": old_time,
                "status": "PENDING",
                "filled_at": None
            }
        },
        "completed_trades": []
    }

    check_active_trades(records)

    # Order must be removed from active and moved to completed as EXPIRED
    assert "XAUUSD" not in records["active_trades"]
    assert len(records["completed_trades"]) == 1
    expired = records["completed_trades"][0]
    assert expired["status"] == "EXPIRED"
    assert expired["outcome"] == "EXPIRED_UNFILLED"
    assert expired["realized_pips"] == 0.0
    assert expired["realized_r"] == 0.0
    assert any("SETUP EXPIRED" in a for a in alerts)


def test_find_ict_liquidity_target_long_bsl():
    """Ensure find_ict_liquidity_target correctly targets the nearest overhead BSL pool for longs."""
    from market_scanner import find_ict_liquidity_target

    # Create a series with a clear fractal swing high at bar 4 (high = 1.1450)
    highs = [1.1380, 1.1400, 1.1420, 1.1440, 1.1450, 1.1430, 1.1410, 1.1390, 1.1400, 1.1410]
    lows = [h - 0.0020 for h in highs]
    df = pd.DataFrame({"high": highs, "low": lows})

    entry = 1.1410
    sl_dist = 0.0020 # 20 pips SL

    # BSL at 1.1450 is 40 pips above entry -> 2.0R
    tp, rr, pool_name = find_ict_liquidity_target(df, entry=entry, sl_dist=sl_dist, is_long=True)

    assert tp == 1.1450
    assert rr == 2.0
    assert "BSL Pool" in pool_name


def test_find_ict_liquidity_target_short_ssl():
    """Ensure find_ict_liquidity_target correctly targets the nearest resting SSL pool for shorts."""
    from market_scanner import find_ict_liquidity_target

    # Create a series with a clear fractal swing low at bar 4 (low = 1.1350)
    lows = [1.1420, 1.1400, 1.1380, 1.1360, 1.1350, 1.1370, 1.1390, 1.1400, 1.1390, 1.1380]
    highs = [l + 0.0020 for l in lows]
    df = pd.DataFrame({"high": highs, "low": lows})

    entry = 1.1380
    sl_dist = 0.0020 # 20 pips SL

    # SSL at 1.1350 is 30 pips below entry -> 1.5R
    tp, rr, pool_name = find_ict_liquidity_target(df, entry=entry, sl_dist=sl_dist, is_long=False)

    assert tp == 1.1350
    assert rr == 1.5
    assert "SSL Pool" in pool_name


def test_find_ict_liquidity_target_fallback():
    """Ensure find_ict_liquidity_target falls back to 1.75R expansion when no qualifying pool exists."""
    from market_scanner import find_ict_liquidity_target

    # Monotonically increasing bars (no overhead swing high)
    highs = [1.1000 + (0.0010 * i) for i in range(15)]
    lows = [h - 0.0010 for h in highs]
    df = pd.DataFrame({"high": highs, "low": lows})

    entry = highs[-1]
    sl_dist = 0.0020

    tp, rr, pool_name = find_ict_liquidity_target(df, entry=entry, sl_dist=sl_dist, is_long=True)

    expected_tp = entry + (sl_dist * 1.75)
    assert round(tp, 5) == round(expected_tp, 5)
    assert rr == 1.75
    assert "Structural Expansion" in pool_name




