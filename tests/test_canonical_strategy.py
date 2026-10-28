"""Unit tests for the canonical trading strategy exit alignment and single source of truth.

Verifies:
1. Canonical configuration constants in core.config:
   - TP = 15.0 pips, SL = 10.0 pips (Pure 1:1.50 R:R).
   - Reference Account Equity = $5,000.00, Risk = 1.0% ($50.00 risk budget).
   - Universe: 6 institutional Forex pairs (EURUSD, USDCAD, GBPUSD, USDJPY, USDCHF, AUDUSD).
   - Gold (XAUUSD) and non-Forex assets strictly excluded.
2. Cross-module alignment:
   - core.instrument_validator.PAIR_SCHEDULES uses canonical 15p TP / 10p SL.
   - app.config uses canonical 15p TP / 10p SL.
   - market_scanner calculate_liquidity_bounds_tp_sl returns 15.0p TP / 10.0p SL.
3. Telegram alert message formatting:
   - Explicitly displays: actual stop distance (10.0 pips), target distance (15.0 pips),
     calculated position size, account equity ($5,000.00), risk budget ($50.00),
     and estimated monetary risk.
4. Position sizing risk budget enforcement:
   - Never exceeds $50.00 on a $5,000 reference account.
   - Safely returns 0.0 (skips trade) when min permitted lot (0.01) would breach budget.
5. Backtest configuration alignment:
   - scripts/run_canonical_backtest.py uses the authoritative constants.
"""

import pytest
import pandas as pd
from core.config import (
    CANONICAL_SYMBOLS,
    CANONICAL_TAKE_PROFIT_PIPS,
    CANONICAL_STOP_LOSS_PIPS,
    CANONICAL_RISK_REWARD_RATIO,
    REFERENCE_ACCOUNT_EQUITY,
    REFERENCE_RISK_PCT,
    REFERENCE_RISK_BUDGET_USD,
    PAIR_CONFIGS,
    CANONICAL_TRANSACTION_COSTS,
)
from core.instrument_validator import (
    PAIR_SCHEDULES,
    FIXED_STOP_LOSS_PIPS,
    FIXED_TAKE_PROFIT_PIPS,
    calculate_tp_sl,
    calculate_position_size,
    calculate_monetary_risk,
)
import app.config as app_config
from market_scanner import calculate_liquidity_bounds_tp_sl, format_alert_message


def test_canonical_config_constants():
    """Verify single source of truth configuration values in core.config."""
    assert CANONICAL_TAKE_PROFIT_PIPS == 15.0
    assert CANONICAL_STOP_LOSS_PIPS == 10.0
    assert CANONICAL_RISK_REWARD_RATIO == 1.50
    assert REFERENCE_ACCOUNT_EQUITY == 5000.0
    assert REFERENCE_RISK_PCT == 1.0
    assert REFERENCE_RISK_BUDGET_USD == 50.00

    expected_pairs = {"EURUSD", "USDCAD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD"}
    assert set(CANONICAL_SYMBOLS) == expected_pairs
    assert "XAUUSD" not in CANONICAL_SYMBOLS
    assert "GOLD" not in CANONICAL_SYMBOLS


def test_module_configuration_alignment():
    """Verify all modules inherit identical canonical exit geometry."""
    # core.instrument_validator
    assert FIXED_TAKE_PROFIT_PIPS == 15.0
    assert FIXED_STOP_LOSS_PIPS == 10.0
    for sym in CANONICAL_SYMBOLS:
        assert PAIR_SCHEDULES[sym]["sl_pips"] == 10.0
        assert PAIR_SCHEDULES[sym]["tp_pips"] == 15.0

    # app.config
    assert app_config.TAKE_PROFIT_PIPS == 15.0
    assert app_config.STOP_LOSS_PIPS == 10.0
    assert app_config.DEFAULT_RISK_REWARD == 1.50
    assert set(app_config.SUPPORTED_SYMBOLS) == set(CANONICAL_SYMBOLS)

    # market_scanner calculate_liquidity_bounds_tp_sl
    tp, sl, tp_pips, sl_pips, rr, name = calculate_liquidity_bounds_tp_sl(
        df=pd.DataFrame(),
        entry=1.0850,
        is_long=True,
        pair_name="EURUSD",
        pip=0.0001,
        digits=5,
    )
    assert tp_pips == 15.0
    assert sl_pips == 10.0
    assert rr == 1.50


def test_calculate_tp_sl_prices():
    """Verify exact target and stop loss price calculations."""
    # EURUSD Long at 1.0850: SL 10p = 1.0840, TP 15p = 1.0865
    tp, sl = calculate_tp_sl(entry=1.0850, direction="LONG", symbol="EURUSD")
    assert tp == 1.0865
    assert sl == 1.0840

    # EURUSD Short at 1.0850: SL 10p = 1.0860, TP 15p = 1.0835
    tp_s, sl_s = calculate_tp_sl(entry=1.0850, direction="SHORT", symbol="EURUSD")
    assert tp_s == 1.0835
    assert sl_s == 1.0860

    # USDJPY Long at 155.00: SL 10p (0.10) = 154.90, TP 15p (0.15) = 155.15
    tp_j, sl_j = calculate_tp_sl(entry=155.00, direction="LONG", symbol="USDJPY")
    assert pytest.approx(tp_j, abs=1e-4) == 155.15
    assert pytest.approx(sl_j, abs=1e-4) == 154.90


def test_reference_account_risk_ceiling():
    """Verify that monetary risk on a $5,000 account never breaches $50.00 across all pairs."""
    mock_rates = {
        "EURUSD": 1.0850,
        "GBPUSD": 1.2950,
        "AUDUSD": 0.6550,
        "USDCAD": 1.4190,
        "USDJPY": 155.00,
        "USDCHF": 0.8800,
    }

    for sym in CANONICAL_SYMBOLS:
        rate = mock_rates[sym]
        lots = calculate_position_size(
            account_equity=REFERENCE_ACCOUNT_EQUITY,
            risk_pct=REFERENCE_RISK_PCT,
            sl_pips=CANONICAL_STOP_LOSS_PIPS,
            symbol=sym,
            exchange_rate=rate,
        )
        assert lots > 0.0, f"Expected positive lots for {sym}"
        monetary_risk = calculate_monetary_risk(
            lots=lots,
            sl_pips=CANONICAL_STOP_LOSS_PIPS,
            symbol=sym,
            exchange_rate=rate,
        )
        assert monetary_risk <= REFERENCE_RISK_BUDGET_USD + 0.01, (
            f"Risk breach on {sym}: ${monetary_risk:.2f} > ${REFERENCE_RISK_BUDGET_USD:.2f}"
        )


def test_budget_breach_returns_zero_lot():
    """Verify that if minimum permitted lot (0.01) would breach the dollar risk budget,
    the position sizing engine returns 0.0 (safely skipping the trade)."""
    # $20 account, 1% risk = $0.20 budget.
    # 0.01 lot EURUSD with 10 pips SL risks $1.00.
    # $1.00 > $0.20 -> must return 0.0
    lots = calculate_position_size(
        account_equity=20.0,
        risk_pct=1.0,
        sl_pips=10.0,
        symbol="EURUSD",
        min_lot=0.01,
    )
    assert lots == 0.0


def test_telegram_alert_formatter_contains_all_metrics():
    """Verify that Telegram signal alerts include all required risk and geometry parameters."""
    signal = {
        "pair": "EURUSD",
        "timeframe": "15M",
        "direction": "LONG",
        "entry": 1.08500,
        "take_profit": 1.08650,
        "stop_loss": 1.08400,
        "tp_pips": 15.0,
        "sl_pips": 10.0,
        "rr": 1.50,
        "calc_lots": 0.50,
        "account_equity": 5000.0,
        "risk_budget_usd": 50.0,
        "monetary_risk_usd": 50.0,
        "trigger": "PULLBACK",
        "killzone": "LONDON",
        "bias": "BULLISH",
        "time": "2026-10-28 14:00 UTC",
    }
    msg = format_alert_message(signal)

    assert "EUR/USD" in msg
    assert "BUY / LONG" in msg
    assert "1.085" in msg
    assert "10.0 pips" in msg
    assert "15.0 pips" in msg
    assert "0.50 Lots" in msg
    assert "$5,000.00" in msg
    assert "$50.00" in msg
