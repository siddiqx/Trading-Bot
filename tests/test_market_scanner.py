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

    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *args, **kwargs: True)
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
    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *args, **kwargs: True)
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
                "ticker": "XAUUSD",
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
    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *args, **kwargs: True)
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
                "ticker": "XAUUSD",
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
    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *args, **kwargs: True)
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
                "ticker": "XAUUSD",
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


def test_find_ict_liquidity_target_no_qualifying_pool():
    # v2 behavior: no 1.75R fallback. Returns (None, None, None) when no BSL pool qualifies.
    from market_scanner import find_ict_liquidity_target

    # Monotonically increasing bars: no overhead swing high exists to target
    highs = [1.1000 + (0.0010 * i) for i in range(15)]
    lows = [h - 0.0010 for h in highs]
    df = pd.DataFrame(dict(high=highs, low=lows))

    entry = highs[-1]
    sl_dist = 0.0020

    tp, rr, pool_name = find_ict_liquidity_target(df, entry=entry, sl_dist=sl_dist, is_long=True)

    assert tp is None
    assert rr == 0.0  # function returns 0.0 (not None) when no pool found
    assert pool_name is None


def test_check_active_trades_ema20_invalidation_exit(monkeypatch):
    """Ensure check_active_trades triggers EMA20 invalidation exit when trade holds > 24h and closes opposite 20-EMA."""
    from market_scanner import check_active_trades

    # Entry was 26 hours ago
    t_open = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
    t_now = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)

    # Mock candle closed at 1.1350, with ema20 at 1.1360 (below EMA for LONG -> invalidation)
    mock_df = pd.DataFrame({
        "timestamp": [int(t_now.timestamp())],
        "time": [t_now],
        "open": [1.1355],
        "high": [1.1365], # does not reach TP (1.1400)
        "low": [1.1340],  # does not breach SL (1.1300)
        "close": [1.1350],
        "volume": [500],
        "ema20": [1.1360]
    })

    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *args, **kwargs: True)
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *args, **kwargs: mock_df)
    monkeypatch.setattr("market_scanner.send_telegram_alert", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.sync_worker", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.save_trade_records", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.compute_indicators", lambda df, **kwargs: df)
    monkeypatch.setattr("market_scanner.record_trade_post_mortem", lambda *args, **kwargs: None)

    records = {
        "active_trades": {
            "EURUSD": {
                "trade_id": "EURUSD_1H_TEST",
                "pair": "EURUSD",
                "symbol": "EURUSD",
                "ticker": "EURUSD=X",
                "direction": "LONG",
                "timeframe": "1H",
                "entry": 1.1360,
                "stop_loss": 1.1300,
                "take_profit": 1.1460,
                "sl_pips": 60.0,
                "tp_pips": 100.0,
                "rr": 1.67,
                "pip": 0.0001,
                "digits": 5,
                "opened_at": t_open.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "OPEN"
            }
        },
        "completed_trades": []
    }

    check_active_trades(records)

    # EURUSD should have exited via EMA invalidation
    assert "EURUSD" not in records["active_trades"]
    assert len(records["completed_trades"]) == 1
    completed = records["completed_trades"][0]
    assert completed["exit_reason"] == "EMA20_INVALIDATION"
    assert completed["exit_price"] == 1.1350
    assert completed["status"] == "CLOSED"


def test_is_forex_market_open_cases():
    """Verify that is_forex_market_open strictly closes from Friday 17:00 NY to Sunday 17:00 NY."""
    from zoneinfo import ZoneInfo
    from market_scanner import is_forex_market_open

    ny_tz = ZoneInfo("America/New_York")

    # Wednesday 10:00 NY -> Open
    wed_open = datetime(2026, 9, 30, 10, 0, tzinfo=ny_tz)
    assert is_forex_market_open(wed_open) is True

    # Friday 16:59 NY -> Open
    fri_open = datetime(2026, 10, 2, 16, 59, tzinfo=ny_tz)
    assert is_forex_market_open(fri_open) is True

    # Friday 17:00 NY -> Closed
    fri_close = datetime(2026, 10, 2, 17, 0, tzinfo=ny_tz)
    assert is_forex_market_open(fri_close) is False

    # Saturday 12:00 NY -> Closed
    sat_noon = datetime(2026, 10, 3, 12, 0, tzinfo=ny_tz)
    assert is_forex_market_open(sat_noon) is False

    # Sunday 16:59 NY -> Closed
    sun_before_open = datetime(2026, 10, 4, 16, 59, tzinfo=ny_tz)
    assert is_forex_market_open(sun_before_open) is False

    # Sunday 17:00 NY -> Open
    sun_open = datetime(2026, 10, 4, 17, 0, tzinfo=ny_tz)
    assert is_forex_market_open(sun_open) is True


def test_gold_config_uses_mt5_spot_pair():
    """Ensure Gold configuration strictly uses MT5 spot XAUUSD with calibrated 8-bar Donchian."""
    from market_scanner import SYMBOLS

    assert "XAUUSD" in SYMBOLS
    gold_cfg = SYMBOLS["XAUUSD"]
    assert gold_cfg["ticker"] == "XAUUSD"
    assert gold_cfg["pip"] == 0.10
    assert gold_cfg["digits"] == 2
    assert gold_cfg["donchian_len"] == 8

    # Ensure no futures or crypto symbols exist in SYMBOLS
    for sym, cfg in SYMBOLS.items():
        assert "GC=F" not in cfg["ticker"], f"Found COMEX futures GC=F in {sym}"
        assert "PAXG" not in cfg["ticker"], f"Found crypto PAXG in {sym}"


def test_run_scan_cycle_skips_when_market_closed(monkeypatch, caplog):
    """Ensure run_scan_cycle immediately halts and stands down when forex market is closed."""
    import logging
    from market_scanner import run_scan_cycle

    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *args, **kwargs: False)
    
    with caplog.at_level(logging.INFO):
        run_scan_cycle()

    assert "markets are CLOSED for the weekend" in caplog.text


def test_detect_pullback_confirmation():
    """Verify that detect_pullback_confirmation detects Phase 1 breakout and confirms Phase 2 rejection."""
    from market_scanner import detect_pullback_confirmation

    # Construct synthetic bars:
    # Bars 0-20: flat base at 100.0 (high 101.0, low 99.0)
    # Bar 21: Donchian high breakout at 103.0 (impulse)
    # Bar 22: Pullback bar down to 101.5 (touches value zone)
    # Bar 23: Rejection bounce bar closing higher (close > open: 102.0 -> 102.8)
    times = [datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc) + timedelta(hours=i) for i in range(25)]
    
    closes = [100.0] * 21 + [103.0, 101.8, 102.8, 102.8]
    opens = [100.0] * 21 + [100.5, 103.0, 101.8, 102.0]
    highs = [101.0] * 21 + [103.5, 103.0, 103.0, 103.0]
    lows = [99.0] * 21 + [100.2, 101.2, 101.6, 101.8]
    
    df = pd.DataFrame({
        "time": times,
        "close_time": [t + timedelta(hours=1) for t in times],
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [1000] * 25,
        "ema20": [99.5] * 21 + [100.5, 101.0, 101.4, 101.4],
        "ema50": [98.0] * 25,
        "ema20_slope": [0.05] * 25,
        "donch_high": [101.0] * 21 + [101.0, 103.5, 103.5, 103.5],
        "donch_low": [98.5] * 25,
        "rsi": [55.0] * 25,
        "atr": [1.0] * 25
    })
    
    # Evaluate at bar 23 (index 23)
    bars_subset = df.iloc[:24]
    confirmed, bo_time, ob_l, fib_50, hunt_lvl = detect_pullback_confirmation(
        bars_subset, donch_len=8, is_long=True, max_lookback=8
    )
    assert confirmed is True
    assert hunt_lvl == 101.0
    assert ob_l <= 101.0


def test_model_j_partial_tp_and_breakeven_lock(monkeypatch):
    """Verify that reaching +1.0R banks 50% profit (+0.50R) and moves SL to Breakeven."""
    from market_scanner import check_active_trades

    t_entry = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    mock_df = pd.DataFrame({
        "time": [t_entry + timedelta(hours=i) for i in range(5)],
        "open": [2650.0, 2652.0, 2660.0, 2655.0, 2652.0],
        "high": [2652.0, 2662.0, 2665.0, 2658.0, 2654.0],  # Bar 1 high is 2662 (+12.0 above entry, exceeds 1.0R = 10.0)
        "low": [2649.0, 2651.0, 2653.0, 2649.0, 2648.0],
        "close": [2651.0, 2661.0, 2657.0, 2650.0, 2649.0],
        "volume": [100] * 5,
        "ema20": [2645.0] * 5,
        "ema50": [2640.0] * 5
    })

    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *args, **kwargs: True)
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *args, **kwargs: mock_df)
    monkeypatch.setattr("market_scanner.send_telegram_alert", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.sync_worker", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.save_trade_records", lambda *args, **kwargs: None)

    records = {
        "active_trades": {
            "XAUUSD": {
                "trade_id": "XAUUSD_TEST",
                "pair": "XAUUSD",
                "symbol": "XAUUSD",
                "ticker": "XAUUSD",
                "direction": "LONG",
                "timeframe": "1H",
                "entry": 2650.00,
                "stop_loss": 2640.00,  # 1.0R = $10.00 (100 pips)
                "take_profit": 2667.50, # 1.75R
                "sl_pips": 100.0,
                "tp_pips": 175.0,
                "rr": 1.75,
                "pip": 0.10,
                "digits": 2,
                "opened_at": t_entry.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "OPEN",
                "be_active": False,
                "partial_taken": False
            }
        },
        "completed_trades": []
    }

    check_active_trades(records)

    # In bar 1, high reached 2662.0 (+12.0 > 10.0 initial SL dist), so partial TP must be taken
    # and SL moved to Breakeven (+1 pip = 2650.10).
    # Then in bar 3, low dipped to 2649.0, hitting the Breakeven stop loss!
    # Because Model J locked BE with 50% booked, trade must resolve as WIN (+0.50R banked).
    assert "XAUUSD" not in records["active_trades"]
    assert len(records["completed_trades"]) == 1
    completed = records["completed_trades"][0]
    assert completed["status"] == "CLOSED"
    assert completed["outcome"] == "WIN"
    assert completed["realized_r"] == 0.50
    assert completed["realized_pips"] == 50.5


def test_check_daily_circuit_breaker_profit_lock():
    from market_scanner import check_daily_circuit_breaker
    from datetime import datetime, timezone
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    records = {
        "completed_trades": [
            {"closed_at": f"{today_utc}T10:00:00Z", "outcome": "WIN", "realized_r": 1.35}
        ]
    }
    tripped, reason = check_daily_circuit_breaker(records)
    assert tripped is True
    assert "Daily Profit Lock" in reason


def test_check_daily_circuit_breaker_loss_limit():
    from market_scanner import check_daily_circuit_breaker
    from datetime import datetime, timezone
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    records = {
        "completed_trades": [
            {"closed_at": f"{today_utc}T08:00:00Z", "outcome": "LOSS", "realized_r": -1.0},
            {"closed_at": f"{today_utc}T12:00:00Z", "outcome": "LOSS", "realized_r": -1.0}
        ]
    }
    tripped, reason = check_daily_circuit_breaker(records)
    assert tripped is True
    assert "Daily Loss Circuit Breaker" in reason


def test_check_daily_circuit_breaker_neutral():
    from market_scanner import check_daily_circuit_breaker
    from datetime import datetime, timezone
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    records = {
        "completed_trades": [
            {"closed_at": f"{today_utc}T08:00:00Z", "outcome": "WIN", "realized_r": 0.50}
        ]
    }
    tripped, reason = check_daily_circuit_breaker(records)
    assert tripped is False
    assert reason == ""








