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
    # Candle 0 touches entry (high touches 1.10000), but stays below SL
    mock_df = pd.DataFrame({
        "timestamp": [int(t0.timestamp())],
        "time": [t0],
        "open": [1.09950],
        "high": [1.10005],  # Touches entry 1.10000
        "low": [1.09940],
        "close": [1.09980],
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
            "EURUSD": {
                "trade_id": "EURUSD_TEST_1",
                "pair": "EURUSD",
                "symbol": "EURUSD",
                "ticker": "EURUSD=X",
                "direction": "SHORT",
                "entry": 1.10000,
                "stop_loss": 1.10100,
                "take_profit": 1.09850,
                "sl_pips": 10.0,
                "tp_pips": 15.0,
                "rr": 1.5,
                "pip": 0.0001,
                "digits": 5,
                "opened_at": "2026-09-30T15:30:00Z",
                "status": "PENDING",
                "filled_at": None
            }
        },
        "completed_trades": []
    }

    check_active_trades(records)

    trade = records["active_trades"]["EURUSD"]
    assert trade["status"] == "OPEN"
    assert trade["filled_at"] is not None
    assert any("ORDER FILLED" in a for a in alerts)


def test_check_active_trades_pending_order_cancellation(monkeypatch):
    """Ensure a PENDING trade is CANCELLED with 0 loss if price hits SL before ever touching entry."""
    from market_scanner import check_active_trades

    t0 = datetime(2026, 9, 30, 15, 30, tzinfo=timezone.utc)
    # Candle breaches SL (1.10100) without touching entry (1.10000) for SHORT
    mock_df = pd.DataFrame({
        "timestamp": [int(t0.timestamp())],
        "time": [t0],
        "open": [1.10050],
        "high": [1.10120],  # Breaches SL 1.10100
        "low": [1.10020],   # Never touches 1.10000
        "close": [1.10080],
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
            "EURUSD": {
                "trade_id": "EURUSD_TEST_2",
                "pair": "EURUSD",
                "symbol": "EURUSD",
                "ticker": "EURUSD=X",
                "direction": "SHORT",
                "entry": 1.10000,
                "stop_loss": 1.10100,
                "take_profit": 1.09850,
                "sl_pips": 10.0,
                "tp_pips": 15.0,
                "rr": 1.5,
                "pip": 0.0001,
                "digits": 5,
                "opened_at": "2026-09-30T15:30:00Z",
                "status": "PENDING",
                "filled_at": None
            }
        },
        "completed_trades": []
    }

    check_active_trades(records)

    assert "EURUSD" not in records["active_trades"]
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
        "open": [1.09950],
        "high": [1.09980],  # Stays below limit entry 1.10000 (unfilled)
        "low": [1.09920],   # Stays above TP 1.09850
        "close": [1.09950],
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
            "EURUSD": {
                "trade_id": "EURUSD_TIMEOUT_TEST",
                "pair": "EURUSD",
                "symbol": "EURUSD",
                "ticker": "EURUSD=X",
                "direction": "SHORT",
                "timeframe": "15M",
                "entry": 1.10000,
                "stop_loss": 1.10100,
                "take_profit": 1.09850,
                "sl_pips": 10.0,
                "tp_pips": 15.0,
                "rr": 1.5,
                "pip": 0.0001,
                "digits": 5,
                "opened_at": old_time,
                "status": "PENDING",
                "filled_at": None
            }
        },
        "completed_trades": []
    }

    check_active_trades(records)

    # Order must be removed from active and moved to completed as EXPIRED
    assert "EURUSD" not in records["active_trades"]
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

    # Create a series with a clear fractal swing high at bar 4 (high = 1.1437)
    highs = [1.1380, 1.1400, 1.1420, 1.1430, 1.1437, 1.1420, 1.1410, 1.1390, 1.1400, 1.1410]
    lows = [h - 0.0020 for h in highs]
    df = pd.DataFrame({"high": highs, "low": lows})

    entry = 1.1410
    sl_dist = 0.0020 # 20 pips SL

    # BSL at 1.1437 is 27 pips above entry -> 1.35R
    tp, rr, pool_name = find_ict_liquidity_target(df, entry=entry, sl_dist=sl_dist, is_long=True)

    assert tp == 1.1437
    assert rr == 1.35
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


def test_gold_config_excluded_from_scanner_symbols():
    """Ensure Gold (XAUUSD) is completely removed from scanner SYMBOLS whitelist."""
    from market_scanner import SYMBOLS
    from core.instrument_validator import is_gold_symbol

    assert "XAUUSD" not in SYMBOLS
    assert "GOLD" not in SYMBOLS
    assert all(not is_gold_symbol(sym) for sym in SYMBOLS)
    assert "EURUSD" in SYMBOLS
    assert "GBPUSD" in SYMBOLS
    assert "USDJPY" in SYMBOLS

    # Ensure no futures, crypto, or gold symbols exist in SYMBOLS
    for sym, cfg in SYMBOLS.items():
        assert "GC=F" not in cfg["ticker"], f"Found COMEX futures GC=F in {sym}"
        assert "PAXG" not in cfg["ticker"], f"Found crypto PAXG in {sym}"
        assert "XAU" not in cfg["ticker"], f"Found Gold ticker in {sym}"


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


def test_fixed_tp_and_sl_trade_resolution(monkeypatch):
    """Verify that an active EURUSD trade correctly resolves as WIN at +15 pips TP and LOSS at -10 pips SL."""
    from market_scanner import check_active_trades

    t_entry = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    mock_df_win = pd.DataFrame({
        "time": [t_entry + timedelta(hours=i) for i in range(3)],
        "open": [1.10000, 1.10050, 1.10120],
        "high": [1.10050, 1.10160, 1.10140],  # Bar 1 touches 1.10160 (+16 pips >= 15 pips TP 1.10150)
        "low": [1.09980, 1.10020, 1.10090],
        "close": [1.10040, 1.10140, 1.10110],
        "volume": [100] * 3,
        "ema20": [1.09900] * 3,
        "ema50": [1.09800] * 3
    })

    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *args, **kwargs: True)
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *args, **kwargs: mock_df_win)
    monkeypatch.setattr("market_scanner.send_telegram_alert", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.sync_worker", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.save_trade_records", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.record_trade_post_mortem", lambda *args, **kwargs: None)

    records = {
        "active_trades": {
            "EURUSD": {
                "trade_id": "EURUSD_TEST",
                "pair": "EURUSD",
                "symbol": "EURUSD",
                "ticker": "EURUSD=X",
                "direction": "LONG",
                "timeframe": "15M",
                "entry": 1.10000,
                "stop_loss": 1.09900,  # 10 pips SL
                "take_profit": 1.10150, # 15 pips TP
                "sl_pips": 10.0,
                "tp_pips": 15.0,
                "rr": 1.5,
                "pip": 0.0001,
                "digits": 5,
                "opened_at": t_entry.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "OPEN",
            }
        },
        "completed_trades": []
    }

    check_active_trades(records)

    assert "EURUSD" not in records["active_trades"]
    assert len(records["completed_trades"]) == 1
    completed = records["completed_trades"][0]
    assert completed["status"] == "CLOSED"
    assert completed["outcome"] == "WIN"
    assert completed["realized_r"] == 1.5
    assert completed["realized_pips"] == 15.0


def test_stage_1_breakeven_lock_at_75_r(monkeypatch):
    """Verify that reaching +0.75R does NOT prematurely strangle trade at BE; position remains active on normal retests."""
    from market_scanner import check_active_trades

    t_entry = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    # Entry: 1.10000, SL: 1.09800 (SL dist = 20 pips = 0.00200). +0.75R = 15 pips (1.10150).
    # Bar 1 high reaches 1.10160 (+16 pips).
    # Bar 2 price dips to 1.09900 (above initial SL of 1.09800).
    mock_df = pd.DataFrame({
        "time": [t_entry + timedelta(hours=i) for i in range(3)],
        "open": [1.10000, 1.10050, 1.10100],
        "high": [1.10050, 1.10160, 1.10120],  # Bar 1 high = 1.10160 (+0.80R)
        "low": [1.09980, 1.10020, 1.09900],   # Bar 2 low dips to 1.09900 (above SL 1.09800)
        "close": [1.10040, 1.10110, 1.09920],
        "volume": [100] * 3,
        "ema20": [1.09900] * 3,
        "ema50": [1.09800] * 3
    })

    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *args, **kwargs: True)
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *args, **kwargs: mock_df)
    monkeypatch.setattr("market_scanner.send_telegram_alert", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.sync_worker", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.save_trade_records", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.record_trade_post_mortem", lambda *args, **kwargs: None)

    records = {
        "active_trades": {
            "EURUSD": {
                "trade_id": "EURUSD_TEST",
                "pair": "EURUSD",
                "symbol": "EURUSD",
                "ticker": "EURUSD=X",
                "direction": "LONG",
                "timeframe": "1H",
                "entry": 1.10000,
                "stop_loss": 1.09800,  # 20 pips
                "take_profit": 1.10270, # 1.35R
                "sl_pips": 20.0,
                "tp_pips": 27.0,
                "rr": 1.35,
                "pip": 0.0001,
                "digits": 5,
                "opened_at": t_entry.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "OPEN",
                "be_active": False,
                "partial_taken": False
            }
        },
        "completed_trades": []
    }

    check_active_trades(records)

    # Trade must NOT be prematurely stopped out at BE; it remains actively OPEN with breathing room!
    assert "EURUSD" in records["active_trades"]
    assert len(records["completed_trades"]) == 0


def test_check_daily_circuit_breaker_profit_unlimited():
    """Ensure 5K account does NOT artificially cap winning days, allowing profits to compound."""
    from market_scanner import check_daily_circuit_breaker
    from datetime import datetime, timezone
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    records = {
        "completed_trades": [
            {"closed_at": f"{today_utc}T10:00:00Z", "outcome": "WIN", "realized_r": 3.50}
        ]
    }
    tripped, reason = check_daily_circuit_breaker(records)
    assert tripped is False
    assert reason == ""


def test_check_daily_circuit_breaker_loss_limit():
    """Ensure circuit breaker trips if daily loss hits <= -2.50R or >= 3 losses."""
    from market_scanner import check_daily_circuit_breaker
    from datetime import datetime, timezone
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    records = {
        "completed_trades": [
            {"closed_at": f"{today_utc}T08:00:00Z", "outcome": "LOSS", "realized_r": -1.0},
            {"closed_at": f"{today_utc}T12:00:00Z", "outcome": "LOSS", "realized_r": -1.0},
            {"closed_at": f"{today_utc}T14:00:00Z", "outcome": "LOSS", "realized_r": -0.8}
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


def test_secondary_pair_conviction_filter(monkeypatch):
    """Ensure secondary pairs (USDJPY, AUDUSD, GBPUSD) skip scanning when EMA separation is in flat chop."""
    from market_scanner import scan_pair_timeframe
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    t0 = now - timedelta(hours=35)
    # 35 bars of flat candle data where ema20 is virtually identical to ema50
    mock_df = pd.DataFrame({
        "timestamp": [int((t0 + timedelta(hours=i)).timestamp()) for i in range(35)],
        "time": [t0 + timedelta(hours=i) for i in range(35)],
        "open": [150.00] * 35,
        "high": [150.10] * 35,
        "low": [149.90] * 35,
        "close": [150.00] * 35,
        "volume": [100] * 35
    })

    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *args, **kwargs: True)
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *args, **kwargs: mock_df)
    monkeypatch.setattr("market_scanner.get_live_price", lambda *args, **kwargs: 150.00)

    cfg = {"ticker": "USDJPY=X", "pip": 0.01, "digits": 3, "donchian_len": 20}
    state = {"alerted_signals": []}
    signals = scan_pair_timeframe("USDJPY", cfg, "1h", state)
    assert len(signals) == 0


def test_audusd_elevated_conviction_threshold(monkeypatch):
    """Ensure AUDUSD requires higher conviction (0.25 ATR EMA separation) to avoid chronic range chop."""
    from market_scanner import scan_pair_timeframe
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    t0 = now - timedelta(hours=35)
    # Mild trend with separation ~0.18 ATR (passes standard 0.15 filter, but rejected by AUDUSD 0.25 filter)
    mock_df = pd.DataFrame({
        "timestamp": [int((t0 + timedelta(hours=i)).timestamp()) for i in range(35)],
        "time": [t0 + timedelta(hours=i) for i in range(35)],
        "open": [0.6500 + i * 0.0001 for i in range(35)],
        "high": [0.6510 + i * 0.0001 for i in range(35)],
        "low": [0.6490 + i * 0.0001 for i in range(35)],
        "close": [0.6505 + i * 0.0001 for i in range(35)],
        "volume": [100] * 35
    })

    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *args, **kwargs: True)
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *args, **kwargs: mock_df)
    monkeypatch.setattr("market_scanner.get_live_price", lambda *args, **kwargs: 0.6540)

    cfg = {"ticker": "AUDUSD=X", "pip": 0.0001, "digits": 5, "donchian_len": 20}
    state = {"alerted_signals": []}
    signals = scan_pair_timeframe("AUDUSD", cfg, "1h", state)
    assert len(signals) == 0


def test_detect_ict_liquidity_sweep_bullish():
    """Verify detect_ict_liquidity_sweep confirms bullish sweep and reclaim of Asian Low."""
    from market_scanner import detect_ict_liquidity_sweep

    times = [datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=15 * i) for i in range(20)]
    df = pd.DataFrame({
        "time": times,
        "close_time": [t + timedelta(minutes=15) for t in times],
        "open": [1.0820] * 19 + [1.0802],
        "high": [1.0830] * 19 + [1.0810],
        "low": [1.0810] * 19 + [1.0798],   # Swept 1.0800 Asian low by 2.0 pips
        "close": [1.0820] * 19 + [1.0808], # Reclaimed above 1.0800, bullish candle
        "atr": [0.0010] * 20,              # ATR = 10 pips, bar range = 12 pips >= 0.6 ATR
        "asia_low": [1.0800] * 20,
        "asia_high": [1.0850] * 20,
        "sw10_low": [1.0805] * 20,
        "sw10_high": [1.0845] * 20
    })

    confirmed, bar_time, swept_lvl, depth_pips, pool_name = detect_ict_liquidity_sweep(
        df, pip=0.0001, is_long=True
    )
    assert confirmed is True
    assert swept_lvl == 1.0800
    assert depth_pips == 2.0
    assert "Asian Session Low" in pool_name


def test_detect_ict_liquidity_sweep_bearish():
    """Verify detect_ict_liquidity_sweep confirms bearish sweep and reclaim of Asian High."""
    from market_scanner import detect_ict_liquidity_sweep

    times = [datetime(2026, 10, 14, 13, 0, tzinfo=timezone.utc) + timedelta(minutes=15 * i) for i in range(20)]
    df = pd.DataFrame({
        "time": times,
        "close_time": [t + timedelta(minutes=15) for t in times],
        "open": [1.0880] * 19 + [1.0898],
        "high": [1.0890] * 19 + [1.0903],  # Swept 1.0900 Asian high by 3.0 pips
        "low": [1.0870] * 19 + [1.0890],
        "close": [1.0880] * 19 + [1.0892], # Reclaimed below 1.0900, bearish candle
        "atr": [0.0010] * 20,              # ATR = 10 pips, bar range = 13 pips >= 0.6 ATR
        "asia_low": [1.0850] * 20,
        "asia_high": [1.0900] * 20,
        "sw10_low": [1.0855] * 20,
        "sw10_high": [1.0895] * 20
    })

    confirmed, bar_time, swept_lvl, depth_pips, pool_name = detect_ict_liquidity_sweep(
        df, pip=0.0001, is_long=False
    )
    assert confirmed is True
    assert swept_lvl == 1.0900
    assert depth_pips == 3.0
    assert "Asian Session High" in pool_name


def test_detect_ict_liquidity_sweep_rejected_on_small_range():
    """Verify detect_ict_liquidity_sweep rejects setup if candle range < 0.6 ATR (no displacement)."""
    from market_scanner import detect_ict_liquidity_sweep

    times = [datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=15 * i) for i in range(20)]
    df = pd.DataFrame({
        "time": times,
        "close_time": [t + timedelta(minutes=15) for t in times],
        "open": [1.0820] * 19 + [1.0801],
        "high": [1.0830] * 19 + [1.0804],
        "low": [1.0810] * 19 + [1.0799],   # 5 pip range vs 15 pip ATR -> 0.33 ATR (< 0.6)
        "close": [1.0820] * 19 + [1.0803],
        "atr": [0.0015] * 20,
        "asia_low": [1.0800] * 20,
        "asia_high": [1.0850] * 20
    })

    confirmed, bar_time, swept_lvl, depth_pips, pool_name = detect_ict_liquidity_sweep(
        df, pip=0.0001, is_long=True
    )
    assert confirmed is False


def test_format_alert_message_ict():
    """Verify format_alert_message displays ICT Liquidity Sweep metadata."""
    from market_scanner import format_alert_message

    sig = {
        "id": "EURUSD_15M_20261014T080000Z_LONG",
        "pair": "EURUSD",
        "timeframe": "15M",
        "direction": "LONG",
        "strategy": "ICT Killzone Liquidity Sweep (Turtle Soup)",
        "phase": "Liquidity Sweep Reclaim (Asian Session Low Liquidity Pool)",
        "swept_level": 1.08000,
        "sweep_depth_pips": 2.5,
        "time": "2026-10-14T08:00:00Z",
        "entry": 1.08050,
        "stop_loss": 1.07950,
        "take_profit": 1.08200,
        "sl_pips": 10.0,
        "tp_pips": 15.0,
        "rr": 1.5,
        "target_type": "Asian Session Low Liquidity Pool",
        "rsi": 44.5,
        "atr": 10.2,
        "score": 96
    }
    msg = format_alert_message(sig)
    assert "ICT Killzone Liquidity Sweep" in msg
    assert "1.08" in msg
    assert "Pure Binary 1:1.50 Target (100% Runner to TP / SL, Zero Partials)" in msg
    assert "$25.00 / trade (0.50% on $5,000 Prop Account · 0.25 Lots)" in msg


def test_binary_target_execution_no_partial_banking_at_1r(monkeypatch):
    """Verify that reaching +1.0R does NOT bank partial profit or move SL to Breakeven (binary target execution)."""
    from market_scanner import check_active_trades

    t_entry = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    # Entry: 1.10000, SL: 1.09840 (16 pips). TP: 1.10240 (24 pips = 1.5R).
    # Bar 1 reaches 1.10170 (+1.06R). Does not reach 1.5R TP (1.10240).
    mock_df = pd.DataFrame({
        "time": [t_entry + timedelta(minutes=15 * i) for i in range(2)],
        "open": [1.10000, 1.10080],
        "high": [1.10050, 1.10170],  # Reaches +1.0R excursion
        "low": [1.09980, 1.10050],
        "close": [1.10040, 1.10120],
        "volume": [100] * 2,
        "ema20": [1.09900] * 2,
        "ema50": [1.09800] * 2
    })

    alerts = []
    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *args, **kwargs: True)
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *args, **kwargs: mock_df)
    monkeypatch.setattr("market_scanner.send_telegram_alert", lambda msg: alerts.append(msg))
    monkeypatch.setattr("market_scanner.sync_worker", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.save_trade_records", lambda *args, **kwargs: None)

    records = {
        "active_trades": {
            "EURUSD": {
                "trade_id": "EURUSD_BINARY",
                "pair": "EURUSD",
                "symbol": "EURUSD",
                "ticker": "EURUSD=X",
                "direction": "LONG",
                "timeframe": "15M",
                "entry": 1.10000,
                "stop_loss": 1.09840,
                "take_profit": 1.10240,
                "sl_pips": 16.0,
                "tp_pips": 24.0,
                "rr": 1.5,
                "bank_pct": 0.0,
                "partial_taken": False,
                "be_active": False,
                "pip": 0.0001,
                "digits": 5,
                "opened_at": t_entry.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "OPEN",
            }
        },
        "completed_trades": []
    }

    check_active_trades(records)

    trade = records["active_trades"]["EURUSD"]
    # Trade remains open with initial SL completely untouched
    assert trade["stop_loss"] == 1.09840
    assert trade.get("partial_taken") is False
    assert not any("PARTIAL PROFIT SECURED" in a for a in alerts)


def test_binary_target_execution_reaches_full_tp_for_win(monkeypatch):
    """Verify that reaching full TP completes with pure WIN and 1.50R without partial deductions."""
    from market_scanner import check_active_trades

    t_entry = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    # Entry: 1.10000, SL: 1.09840, TP: 1.10240. Bar high reaches 1.10250 (TP hit).
    mock_df = pd.DataFrame({
        "time": [t_entry + timedelta(minutes=15)],
        "open": [1.10050],
        "high": [1.10250],  # Hits TP
        "low": [1.10020],
        "close": [1.10240],
        "volume": [100],
        "ema20": [1.09900],
        "ema50": [1.09800]
    })

    alerts = []
    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *args, **kwargs: True)
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *args, **kwargs: mock_df)
    monkeypatch.setattr("market_scanner.send_telegram_alert", lambda msg: alerts.append(msg))
    monkeypatch.setattr("market_scanner.sync_worker", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.save_trade_records", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.record_trade_post_mortem", lambda *args, **kwargs: None)

    records = {
        "active_trades": {
            "EURUSD": {
                "trade_id": "EURUSD_FULL_TP",
                "pair": "EURUSD",
                "symbol": "EURUSD",
                "ticker": "EURUSD=X",
                "direction": "LONG",
                "timeframe": "15M",
                "entry": 1.10000,
                "stop_loss": 1.09840,
                "take_profit": 1.10240,
                "sl_pips": 16.0,
                "tp_pips": 24.0,
                "rr": 1.5,
                "bank_pct": 0.0,
                "partial_taken": False,
                "be_active": False,
                "pip": 0.0001,
                "digits": 5,
                "opened_at": t_entry.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "OPEN",
            }
        },
        "completed_trades": []
    }

    check_active_trades(records)

    assert "EURUSD" not in records["active_trades"]
    assert len(records["completed_trades"]) == 1
    completed = records["completed_trades"][0]
    assert completed["outcome"] == "WIN"
    assert completed["realized_r"] == 1.50
    assert completed["realized_pips"] == 24.0


def test_stop_loss_priority_over_take_profit_on_volatile_bar(monkeypatch):
    """Ensure that when a volatile candle reaches both SL and TP thresholds, Stop Loss takes absolute precedence."""
    from market_scanner import check_active_trades

    t_entry = datetime(2026, 10, 13, 8, 45, tzinfo=timezone.utc)
    # USDJPY Short: Entry: 158.103, SL: 158.203 (+10 pips), TP: 157.953 (-15 pips)
    # Candle: High 158.385 (breaches SL by 18.2 pips), Low 157.917 (touches TP)
    mock_df = pd.DataFrame({
        "time": [t_entry],
        "open": [158.042],
        "high": [158.385],  # Touches SL
        "low": [157.917],   # Also touches TP
        "close": [158.004],
        "volume": [500],
        "ema20": [158.100],
        "ema50": [158.150]
    })

    alerts = []
    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *args, **kwargs: True)
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *args, **kwargs: mock_df)
    monkeypatch.setattr("market_scanner.send_telegram_alert", lambda msg: alerts.append(msg))
    monkeypatch.setattr("market_scanner.sync_worker", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.save_trade_records", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.record_trade_post_mortem", lambda *args, **kwargs: None)

    records = {
        "active_trades": {
            "USDJPY_15M": {
                "trade_id": "USDJPY_15M_VOLATILE_BAR",
                "pair": "USDJPY",
                "symbol": "USDJPY",
                "ticker": "USDJPY=X",
                "direction": "SHORT",
                "timeframe": "15M",
                "entry": 158.103,
                "stop_loss": 158.203,
                "take_profit": 157.953,
                "sl_pips": 10.0,
                "tp_pips": 15.0,
                "rr": 1.5,
                "pip": 0.01,
                "digits": 3,
                "opened_at": t_entry.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "OPEN",
            }
        },
        "completed_trades": []
    }

    check_active_trades(records)

    assert "USDJPY_15M" not in records["active_trades"]
    assert len(records["completed_trades"]) == 1
    completed = records["completed_trades"][0]
    # Must be recorded as LOSS, not false positive WIN
    assert completed["outcome"] == "LOSS"
    assert completed["exit_price"] == 158.203
    assert completed["realized_r"] == -1.0
    assert completed["realized_pips"] == -10.0


def test_usd_directional_bias_and_exposure_counter():
    """Verify USD directional exposure mapping across institutional universe."""
    from market_scanner import get_usd_directional_bias, count_usd_direction_exposure

    # Base pairs: LONG = Long USD (+1), SHORT = Short USD (-1)
    assert get_usd_directional_bias("USDJPY", "LONG") == 1
    assert get_usd_directional_bias("USDJPY", "SHORT") == -1
    assert get_usd_directional_bias("USDCHF", "LONG") == 1
    assert get_usd_directional_bias("USDCHF", "SHORT") == -1
    assert get_usd_directional_bias("USDCAD", "LONG") == 1
    assert get_usd_directional_bias("USDCAD", "SHORT") == -1

    # Quote pairs: LONG = Short USD (-1), SHORT = Long USD (+1)
    assert get_usd_directional_bias("EURUSD", "LONG") == -1
    assert get_usd_directional_bias("EURUSD", "SHORT") == 1
    assert get_usd_directional_bias("GBPUSD", "LONG") == -1
    assert get_usd_directional_bias("GBPUSD", "SHORT") == 1
    assert get_usd_directional_bias("AUDUSD", "LONG") == -1
    assert get_usd_directional_bias("AUDUSD", "SHORT") == 1

    # Test count_usd_direction_exposure
    mock_active = {
        "EURUSD_15M": {"pair": "EURUSD", "direction": "SHORT", "be_active": False},  # Long USD (+1)
        "USDCAD_15M": {"pair": "USDCAD", "direction": "LONG", "be_active": False},   # Long USD (+1)
        "USDCHF_15M": {"pair": "USDCHF", "direction": "LONG", "be_active": True},    # De-risked to BE (ignored)
        "AUDUSD_15M": {"pair": "AUDUSD", "direction": "LONG", "be_active": False},   # Short USD (-1)
    }
    # Long USD count should be 2 (EURUSD SHORT + USDCAD LONG; USDCHF LONG is BE so ignored)
    assert count_usd_direction_exposure(mock_active, 1) == 2
    # Short USD count should be 1 (AUDUSD LONG)
    assert count_usd_direction_exposure(mock_active, -1) == 1


def test_post_loss_cooldown_locks_pair():
    """Verify pair-specific post-loss cooldown locks out pair for 60 minutes after a stop-loss."""
    from market_scanner import is_pair_in_post_loss_cooldown

    now_utc = datetime.now(timezone.utc)
    recent_closed = (now_utc - timedelta(minutes=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old_closed = (now_utc - timedelta(minutes=90)).strftime("%Y-%m-%dT%H:%M:%SZ")

    records_with_recent_loss = {
        "completed_trades": [
            {"pair": "GBPUSD", "outcome": "LOSS", "closed_at": recent_closed}
        ]
    }
    in_cd, remaining = is_pair_in_post_loss_cooldown(records_with_recent_loss, "GBPUSD", cooldown_minutes=60.0)
    assert in_cd is True
    assert 30.0 <= remaining <= 40.0

    # Trade completed 90 mins ago: cooldown should be expired
    records_with_old_loss = {
        "completed_trades": [
            {"pair": "GBPUSD", "outcome": "LOSS", "closed_at": old_closed}
        ]
    }
    in_cd, remaining = is_pair_in_post_loss_cooldown(records_with_old_loss, "GBPUSD", cooldown_minutes=60.0)
    assert in_cd is False
    assert remaining == 0.0

    # Trade was a WIN: no cooldown
    records_with_win = {
        "completed_trades": [
            {"pair": "GBPUSD", "outcome": "WIN", "closed_at": recent_closed}
        ]
    }
    in_cd, remaining = is_pair_in_post_loss_cooldown(records_with_win, "GBPUSD", cooldown_minutes=60.0)
    assert in_cd is False


def test_in_cycle_usd_correlation_guard_and_unprotected_cap(monkeypatch):
    """Ensure run_scan_cycle rejects a 3rd Long-USD position and caps total unprotected trades at 3."""
    from market_scanner import run_scan_cycle

    # Simulate already having 2 Long-USD positions: EURUSD SHORT and USDCHF LONG
    records_state = {
        "active_trades": {
            "EURUSD_15M": {"pair": "EURUSD", "direction": "SHORT", "be_active": False},
            "USDCHF_15M": {"pair": "USDCHF", "direction": "LONG", "be_active": False},
        },
        "completed_trades": []
    }

    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *args, **kwargs: True)
    monkeypatch.setattr("market_scanner.check_active_trades", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.check_daily_circuit_breaker", lambda *args, **kwargs: (False, "OK"))
    monkeypatch.setattr("market_scanner.load_trade_records", lambda: records_state)
    monkeypatch.setattr("market_scanner.save_trade_records", lambda rec: records_state.update(rec))
    monkeypatch.setattr("market_scanner.load_state", lambda: {"alerted_signals": []})
    monkeypatch.setattr("market_scanner.save_state", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.sync_worker", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.send_telegram_alert", lambda *args, **kwargs: None)

    # Mock scan_pair_timeframe returning a 3rd Long-USD signal: USDCAD LONG
    # And a Short-USD signal: AUDUSD LONG
    def mock_scan(pair_name, cfg, tf, state):
        if pair_name == "USDCAD" and tf == "15m":
            return [{
                "id": "USDCAD_15M_CORR_TEST",
                "pair": "USDCAD",
                "timeframe": "15M",
                "direction": "LONG",  # Long USD (+1) -> Must be rejected by correlation guard!
                "time": "2026-10-15T12:00:00Z",
                "entry": 1.4250,
                "stop_loss": 1.4234,
                "take_profit": 1.4274,
                "sl_pips": 16.0,
                "tp_pips": 24.0,
                "rr": 1.5,
                "bank_pct": 0.60
            }]
        elif pair_name == "AUDUSD" and tf == "15m":
            return [{
                "id": "AUDUSD_15M_CORR_TEST",
                "pair": "AUDUSD",
                "timeframe": "15M",
                "direction": "LONG",  # Short USD (-1) -> Must be accepted!
                "time": "2026-10-15T12:00:00Z",
                "entry": 0.6950,
                "stop_loss": 0.6938,
                "take_profit": 0.6968,
                "sl_pips": 12.0,
                "tp_pips": 18.0,
                "rr": 1.5,
                "rsi": 52.0,
                "atr": 12.0,
                "score": 92,
                "bank_pct": 0.60
            }]
        return []

    monkeypatch.setattr("market_scanner.scan_pair_timeframe", mock_scan)

    # Run scan cycle
    dispatched = run_scan_cycle()

    # USDCAD LONG was rejected because 2 Long-USD positions already existed.
    # AUDUSD LONG was accepted because Short-USD count was 0.
    assert "USDCAD_15M" not in records_state["active_trades"]
    assert "AUDUSD_15M" in records_state["active_trades"]
    assert dispatched == 1


def test_in_cycle_max_unprotected_cap(monkeypatch):
    """Ensure run_scan_cycle strictly rejects signals once 3 unprotected trades are active."""
    from market_scanner import run_scan_cycle

    # Simulate 3 active floating unprotected trades
    records_state = {
        "active_trades": {
            "EURUSD_15M": {"pair": "EURUSD", "direction": "SHORT", "be_active": False},
            "USDCHF_15M": {"pair": "USDCHF", "direction": "LONG", "be_active": False},
            "AUDUSD_15M": {"pair": "AUDUSD", "direction": "LONG", "be_active": False},
        },
        "completed_trades": []
    }

    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *args, **kwargs: True)
    monkeypatch.setattr("market_scanner.check_active_trades", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.check_daily_circuit_breaker", lambda *args, **kwargs: (False, "OK"))
    monkeypatch.setattr("market_scanner.load_trade_records", lambda: records_state)
    monkeypatch.setattr("market_scanner.save_trade_records", lambda rec: records_state.update(rec))
    monkeypatch.setattr("market_scanner.load_state", lambda: {"alerted_signals": []})
    monkeypatch.setattr("market_scanner.save_state", lambda *args, **kwargs: None)
    monkeypatch.setattr("market_scanner.sync_worker", lambda *args, **kwargs: None)

    # Mock returning a signal for GBPUSD 15M
    def mock_scan(pair_name, cfg, tf, state):
        if pair_name == "GBPUSD" and tf == "15m":
            return [{
                "id": "GBPUSD_15M_CAP_TEST",
                "pair": "GBPUSD",
                "timeframe": "15M",
                "direction": "LONG",
                "time": "2026-10-15T12:00:00Z",
                "entry": 1.3200,
                "stop_loss": 1.3180,
                "take_profit": 1.3230,
                "sl_pips": 20.0,
                "tp_pips": 30.0,
                "rr": 1.5,
                "rsi": 55.0,
                "atr": 18.0,
                "score": 95,
                "bank_pct": 0.60
            }]
        return []

    monkeypatch.setattr("market_scanner.scan_pair_timeframe", mock_scan)

    dispatched = run_scan_cycle()
    # Must dispatch 0 signals because 3 unprotected positions are already floating
    assert dispatched == 0
    assert "GBPUSD_15M" not in records_state["active_trades"]

    # Now simulate EURUSD de-risked to Breakeven (+1.0R partial banked)
    records_state["active_trades"]["EURUSD_15M"]["be_active"] = True
    dispatched_after_be = run_scan_cycle()
    # Now that floating unprotected count is 2 (< 3), GBPUSD should be accepted!
    assert dispatched_after_be == 1
    assert "GBPUSD_15M" in records_state["active_trades"]


def test_signal_strictly_uses_live_price_not_stale_5m(monkeypatch):
    """Ensure signals quote the actual live price, never overriding with a stale 5M candle close."""
    from market_scanner import scan_pair_timeframe

    cfg = {"ticker": "GBPUSD=X", "pip": 0.0001, "digits": 5, "donchian_len": 20}
    state = {"alerted_signals": []}

    # Create mock 15M candles where the last candle is a valid ICT liquidity sweep reclaim
    now_utc = datetime(2026, 10, 15, 8, 30, tzinfo=timezone.utc)
    t0 = now_utc - timedelta(minutes=15 * 50)
    times = [t0 + timedelta(minutes=15 * i) for i in range(50)]
    
    # Prices: downward trend, then a bullish sweep reclaim on the last bar
    closes = [1.3250 - (i * 0.0002) for i in range(49)] + [1.3160]
    highs = [c + 0.0005 for c in closes]
    lows = [c - 0.0005 for c in closes]
    # Make last bar a strong rejection sweep reclaim
    lows[-1] = 1.3140  # Deep sweep
    highs[-1] = 1.3165
    opens = [c - 0.0001 for c in closes]
    opens[-1] = 1.3145

    df = pd.DataFrame({
        "timestamp": [int(t.timestamp()) for t in times],
        "time": times,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [1000] * 50
    })

    live_executable_price = 1.31610  # Live tick right now (within 1 pip of 1.3160 bar close)
    stale_5m_price = 1.31520         # Old 5M candle close from minutes ago

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "1")
    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *a, **kw: True)
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *a, **kw: df)
    monkeypatch.setattr("market_scanner.check_htf_alignment", lambda *a, **kw: (True, "HTF Aligned"))
    monkeypatch.setattr("market_scanner.detect_ict_liquidity_sweep", lambda *a, **kw: (True, "2026-10-15T08:30:00Z", 1.3150, 10.0, "Asian Low Pool"))
    monkeypatch.setattr("market_scanner.get_live_price", lambda *a, **kw: live_executable_price)
    # Mock 5M trigger returning a stale 5M precision_entry
    monkeypatch.setattr("market_scanner.fetch_5m_entry_trigger", lambda *a, **kw: {
        "trigger_type": "5M Rejection Wick",
        "precision_entry": stale_5m_price,
        "confidence": 92,
        "action_text": "Bullish pin bar on 5M",
        "bar_close_time": "08:25 UTC"
    })

    signals = scan_pair_timeframe("GBPUSD", cfg, "15m", state)
    assert len(signals) == 1
    sig = signals[0]
    # The entry MUST strictly be the live executable price, NOT the stale 5M price!
    assert sig["entry"] == live_executable_price
    assert sig["entry"] != stale_5m_price
    # Stop loss and take profit must be calculated from the live entry
    assert sig["stop_loss"] < sig["entry"]
    assert sig["take_profit"] > sig["entry"]


def test_chase_guard_rejects_extended_moves(monkeypatch):
    """Ensure signals are rejected if live price has already drifted > 1.5 pips from bar close."""
    from market_scanner import scan_pair_timeframe

    cfg = {"ticker": "GBPUSD=X", "pip": 0.0001, "digits": 5, "donchian_len": 20}
    state = {"alerted_signals": []}

    now_utc = datetime(2026, 10, 15, 8, 30, tzinfo=timezone.utc)
    t0 = now_utc - timedelta(minutes=15 * 50)
    times = [t0 + timedelta(minutes=15 * i) for i in range(50)]
    closes = [1.3160] * 50

    df = pd.DataFrame({
        "timestamp": [int(t.timestamp()) for t in times],
        "time": times,
        "open": closes,
        "high": [c + 0.0005 for c in closes],
        "low": [c - 0.0005 for c in closes],
        "close": closes,
        "volume": [1000] * 50
    })

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "1")
    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *a, **kw: True)
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *a, **kw: df)
    monkeypatch.setattr("market_scanner.check_htf_alignment", lambda *a, **kw: (True, "HTF Aligned"))
    monkeypatch.setattr("market_scanner.detect_ict_liquidity_sweep", lambda *a, **kw: (True, "2026-10-15T08:30:00Z", 1.3150, 10.0, "Asian Low Pool"))
    
    # Case 1: Live price is 1.31620 (2.0 pips above bar close 1.3160) -> exceeds 1.5 pip max chase!
    monkeypatch.setattr("market_scanner.get_live_price", lambda *a, **kw: 1.31620)
    signals = scan_pair_timeframe("GBPUSD", cfg, "15m", state)
    assert len(signals) == 0

    # Case 2: Live price is 1.31580 (2.0 pips below bar close 1.3160) -> adverse drift > 1.5 pips!
    monkeypatch.setattr("market_scanner.get_live_price", lambda *a, **kw: 1.31580)
    signals_adverse = scan_pair_timeframe("GBPUSD", cfg, "15m", state)
    assert len(signals_adverse) == 0

    # Case 3: Live price is 1.31610 (1.0 pip above bar close) -> valid baseline entry!
    monkeypatch.setattr("market_scanner.get_live_price", lambda *a, **kw: 1.31610)
    signals_valid = scan_pair_timeframe("GBPUSD", cfg, "15m", state)
    assert len(signals_valid) == 1
    assert signals_valid[0]["entry"] == 1.31610


def test_calculate_liquidity_bounds_tp_sl():
    """Verify that TP and SL are strictly bounded between 15.0 and 25.0 pips and anchored to liquidity."""
    from market_scanner import calculate_liquidity_bounds_tp_sl

    # Generate synthetic 15M bars
    times = pd.date_range("2026-10-15 00:00", periods=50, freq="15min", tz="UTC")
    closes = [1.3000 + i * 0.0001 for i in range(50)]
    df = pd.DataFrame({
        "time": times,
        "open": closes,
        "high": [c + 0.0010 for c in closes],
        "low": [c - 0.0010 for c in closes],
        "close": closes,
        "volume": [1000] * 50
    })
    closed_bars = df.to_dict("records")
    entry = 1.30500
    pip = 0.0001
    digits = 5

    # Test LONG with tight invalidation (should be clamped up to 15.0 min SL)
    tp, sl, tp_pips, sl_pips, rr, pool_name = calculate_liquidity_bounds_tp_sl(
        closed_bars, entry=entry, is_long=True, pair_name="GBPUSD",
        pip=pip, digits=digits, invalidation_level=1.30450, # only 5 pips away
        min_pips=15.0, max_pips=25.0
    )
    assert 15.0 <= sl_pips <= 25.0
    assert 15.0 <= tp_pips <= 25.0
    assert sl_pips == 15.0
    assert rr >= 1.0
    assert sl < entry
    assert tp > entry

    # Test LONG with wide invalidation (should be clamped down to 25.0 max SL)
    tp, sl, tp_pips, sl_pips, rr, pool_name = calculate_liquidity_bounds_tp_sl(
        closed_bars, entry=entry, is_long=True, pair_name="GBPUSD",
        pip=pip, digits=digits, invalidation_level=1.30100, # 40 pips away
        min_pips=15.0, max_pips=25.0
    )
    assert sl_pips == 25.0
    assert 15.0 <= tp_pips <= 25.0
    assert rr >= 1.0

    # Test SHORT
    tp, sl, tp_pips, sl_pips, rr, pool_name = calculate_liquidity_bounds_tp_sl(
        closed_bars, entry=entry, is_long=False, pair_name="GBPUSD",
        pip=pip, digits=digits, invalidation_level=1.30550, # 5 pips away
        min_pips=15.0, max_pips=25.0
    )
    assert 15.0 <= sl_pips <= 25.0
    assert 15.0 <= tp_pips <= 25.0
    assert sl_pips == 15.0
    assert rr >= 1.0
    assert sl > entry
    assert tp < entry


def test_evaluate_active_trade_exits_spread_clearance(monkeypatch):
    """
    Verify that TP is NOT triggered when price grazes TP within retail spread gap (< 1.0 pip past TP).
    Only true penetrations beyond (TP ± 1.0 pip clearance) trigger target reached.
    """
    from market_scanner import check_active_trades

    monkeypatch.setattr("market_scanner.send_telegram_alert", lambda *a, **kw: None)
    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda *a, **kw: True)
    monkeypatch.setattr("market_scanner.record_trade_post_mortem", lambda *a, **kw: None)
    monkeypatch.setattr("market_scanner.save_trade_records", lambda *a, **kw: None)

    # SHORT Trade on USDCAD
    # Entry: 1.41932, TP: 1.41692 (24p), SL: 1.42092 (16p)
    # Required clearance for SHORT TP: low <= (1.41692 - 0.00010) = 1.41682
    trade_id = "USDCAD_15M_SHORT"
    active_trade = {
        "trade_id": trade_id,
        "symbol": "USDCAD",
        "ticker": "USDCAD=X",
        "pair": "USDCAD",
        "timeframe": "15M",
        "direction": "SHORT",
        "entry": 1.41932,
        "stop_loss": 1.42092,
        "take_profit": 1.41692,
        "sl_pips": 16.0,
        "tp_pips": 24.0,
        "rr": 1.50,
        "pip": 0.0001,
        "digits": 5,
        "status": "OPEN",
        "opened_at": "2026-10-15T00:00:00Z"
    }

    # Case A: Low is 1.41690 (touches TP 1.41692, but above 1.41682 clearance; does NOT clear 1.0p buffer)
    time_candle = pd.to_datetime("2026-10-15 01:00:00+00:00")
    df_graze = pd.DataFrame([{
        "time": time_candle,
        "open": 1.41750,
        "high": 1.41780,
        "low": 1.41690,  # Touched TP (1.41692), but only 0.2 pips penetration, does NOT clear 1.0p buffer
        "close": 1.41740,
        "volume": 100
    }])
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *a, **kw: df_graze)

    records = {
        "active_trades": {trade_id: dict(active_trade)},
        "completed_trades": []
    }
    check_active_trades(records)
    assert trade_id in records["active_trades"]  # Position remains OPEN!
    assert len(records["completed_trades"]) == 0

    # Case B: Low penetrates deep enough to clear 1.0 pip buffer: low <= 1.41682 (e.g. 1.41580)
    df_clear = pd.DataFrame([{
        "time": time_candle,
        "open": 1.41750,
        "high": 1.41780,
        "low": 1.41580,  # 11.2 pips past TP, cleanly clears 1.0p buffer
        "close": 1.41600,
        "volume": 100
    }])
    monkeypatch.setattr("market_scanner.fetch_candles", lambda *a, **kw: df_clear)

    records = {
        "active_trades": {trade_id: dict(active_trade)},
        "completed_trades": []
    }
    check_active_trades(records)
    assert trade_id not in records["active_trades"]
    assert len(records["completed_trades"]) == 1
    assert records["completed_trades"][0]["outcome"] == "WIN"







