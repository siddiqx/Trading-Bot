"""Unit tests for Post-Mortem Diagnostics and Volume Pattern Engine."""

import pytest
from core.post_mortem import (
    get_volume_for_trade,
    determine_trading_session,
    calculate_excursion,
    classify_trade_diagnostics
)
from market_scanner import format_exit_message


def test_get_volume_for_trade():
    # Volume 1 boundaries
    v_no, t_no, v_id = get_volume_for_trade(1)
    assert (v_no, t_no, v_id) == (1, 1, "VOL_01")

    v_no, t_no, v_id = get_volume_for_trade(50)
    assert (v_no, t_no, v_id) == (1, 50, "VOL_01")

    v_no, t_no, v_id = get_volume_for_trade(100)
    assert (v_no, t_no, v_id) == (1, 100, "VOL_01")

    # Volume 2 boundaries
    v_no, t_no, v_id = get_volume_for_trade(101)
    assert (v_no, t_no, v_id) == (2, 1, "VOL_02")

    v_no, t_no, v_id = get_volume_for_trade(200)
    assert (v_no, t_no, v_id) == (2, 100, "VOL_02")

    # Volume 3
    v_no, t_no, v_id = get_volume_for_trade(201)
    assert (v_no, t_no, v_id) == (3, 1, "VOL_03")


def test_determine_trading_session():
    # London/NY overlap
    assert determine_trading_session("2026-09-28T14:30:00Z") == "London/New York Overlap"
    # London
    assert determine_trading_session("2026-09-28T09:00:00Z") == "London Session"
    # Asian
    assert determine_trading_session("2026-09-28T03:00:00Z") == "Asian/Tokyo Session"


def test_calculate_excursion_fallback():
    trade_loss = {
        "entry": 1.1400,
        "stop_loss": 1.1420,
        "take_profit": 1.1365,
        "pip": 0.0001,
        "direction": "SHORT",
        "outcome": "LOSS",
        "realized_pips": -20.0
    }
    ex = calculate_excursion(trade_loss)
    assert ex["mfe_pips"] >= 0
    assert ex["mae_pips"] == -20.0


def test_classify_trade_diagnostics_premature_reversal():
    trade = {
        "direction": "LONG",
        "outcome": "LOSS",
        "duration_bars": 4
    }
    excursion = {
        "mfe_pips": 15.0,
        "mfe_r": 0.85,
        "mae_pips": -18.0,
        "mae_r": -1.0,
        "tp_distance_pct_reached": 50.0
    }
    regime = {
        "trading_session": "London Session",
        "rsi_at_entry": 52.0,
        "breakout_candle_wick_ratio": 0.20
    }
    diag = classify_trade_diagnostics(trade, excursion, regime)
    assert diag["primary_factor"] == "PREMATURE_REVERSAL"
    assert "Breakeven" in diag["actionable_insight"]


def test_classify_trade_diagnostics_liquidity_grab():
    trade = {
        "direction": "LONG",
        "outcome": "LOSS",
        "duration_bars": 2
    }
    excursion = {
        "mfe_pips": 3.0,
        "mfe_r": 0.15,
        "mae_pips": -18.0,
        "mae_r": -1.0,
        "tp_distance_pct_reached": 10.0
    }
    regime = {
        "trading_session": "London Session",
        "rsi_at_entry": 50.0,
        "breakout_candle_wick_ratio": 0.45
    }
    diag = classify_trade_diagnostics(trade, excursion, regime)
    assert diag["primary_factor"] == "LIQUIDITY_GRAB_REVERSAL"
    assert "body-to-wick" in diag["actionable_insight"]


def test_classify_trade_diagnostics_clean_win():
    trade = {
        "direction": "LONG",
        "outcome": "WIN",
        "duration_bars": 5
    }
    excursion = {
        "mfe_pips": 31.5,
        "mfe_r": 1.75,
        "mae_pips": -2.0,
        "mae_r": -0.11,
        "tp_distance_pct_reached": 100.0
    }
    regime = {
        "trading_session": "London Session",
        "rsi_at_entry": 55.0,
        "breakout_candle_wick_ratio": 0.15
    }
    diag = classify_trade_diagnostics(trade, excursion, regime)
    assert diag["primary_factor"] == "CLEAN_MOMENTUM_EXPANSION"


def test_format_exit_message_with_post_mortem():
    trade = {
        "pair": "EUR/USD",
        "timeframe": "1H",
        "direction": "SHORT",
        "entry": 1.13662
    }
    pm_record = {
        "tracking": {
            "volume_no": 1,
            "volume_trade_no": 1,
            "global_trade_no": 1
        },
        "diagnostic": {
            "primary_factor": "STRUCTURAL_INVALIDATION",
            "actionable_insight": "Clean invalidation preserving capital."
        },
        "excursion_metrics": {
            "mfe_pips": 4.7,
            "tp_distance_pct_reached": 14.3,
            "mae_pips": -18.7
        }
    }
    msg = format_exit_message(
        trade=trade,
        outcome="LOSS",
        exit_price=1.13849,
        realized_pips=-18.7,
        realized_r=-1.0,
        post_mortem_record=pm_record
    )
    assert "Volume 1 · Trade #1/100" in msg
    assert "STRUCTURAL_INVALIDATION" in msg
    assert "+4.7 pips" in msg
    assert "EUR/USD" in msg


def test_record_trade_post_mortem_deduplication(tmp_path, monkeypatch):
    import core.post_mortem as pm
    monkeypatch.setattr(pm, "DATA_DIR", tmp_path / "data" / "patterns")
    monkeypatch.setattr(pm, "VOLUMES_DATA_DIR", tmp_path / "data" / "patterns" / "volumes")
    monkeypatch.setattr(pm, "JOURNALS_DIR", tmp_path / "journals")
    monkeypatch.setattr(pm, "VOLUMES_JOURNAL_DIR", tmp_path / "journals" / "volumes")

    test_trade = {
        "trade_id": "TEST_DEDUP_TRADE_001",
        "pair": "USD/CAD",
        "symbol": "USDCAD",
        "direction": "LONG",
        "entry": 1.3500,
        "exit_price": 1.3550,
        "stop_loss": 1.3470,
        "take_profit": 1.3550,
        "outcome": "WIN",
        "realized_pips": 50.0,
        "realized_r": 1.75
    }
    rec1 = pm.record_trade_post_mortem(test_trade)
    rec2 = pm.record_trade_post_mortem(test_trade)

    # Must be exact same record and not duplicate global trade count
    assert rec1["tracking"]["global_trade_no"] == rec2["tracking"]["global_trade_no"]
    assert rec1["trade_id"] == rec2["trade_id"]
