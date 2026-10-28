"""Unit tests for institutional multi-currency position sizing and risk calculations.

Verifies:
1. Direct USD quote pairs (EURUSD, GBPUSD, AUDUSD) where pip value is exactly $10.00.
2. Indirect USD base pairs (USDCAD, USDJPY, USDCHF) requiring quote-to-USD conversion.
3. Strict rejection of Gold (XAUUSD and aliases) and unsupported symbols.
4. Error handling for missing or invalid exchange rates on non-USD quote pairs.
5. Error handling for zero or negative stop-loss distances.
6. Conservative lot-step flooring (0.01 step) to prevent risk budget overshoot.
7. Minimum lot constraints (0.01 min lot).
8. Monetary dollar risk calculations after rounding.
"""

import pytest
import math
from core.instrument_validator import (
    calculate_pip_value_usd,
    calculate_position_size,
    calculate_monetary_risk,
    FIXED_STOP_LOSS_PIPS,
)


def test_pip_value_usd_quote_pairs():
    """Verify $10.00/pip standard lot value for direct USD quote pairs."""
    for sym in ["EURUSD", "GBPUSD", "AUDUSD", "EUR/USD", "GBPUSD=X"]:
        pip_val = calculate_pip_value_usd(sym)
        assert pip_val == 10.0, f"Expected 10.0 USD/pip for {sym}, got {pip_val}"

        # Passing exchange rate should not alter quote USD pairs
        pip_val_with_rate = calculate_pip_value_usd(sym, exchange_rate=1.1200)
        assert pip_val_with_rate == 10.0


def test_pip_value_usd_base_pairs():
    """Verify quote-to-USD conversion for USD base pairs (USDCAD, USDJPY, USDCHF)."""
    # USDCAD @ 1.4190: 10 CAD / 1.4190 CAD per USD = $7.047216 USD
    cad_rate = 1.4190
    expected_cad_pip = 10.0 / cad_rate
    actual_cad_pip = calculate_pip_value_usd("USDCAD", exchange_rate=cad_rate)
    assert pytest.approx(actual_cad_pip, rel=1e-5) == expected_cad_pip

    # USDJPY @ 155.00: 1,000 JPY / 155.00 JPY per USD = $6.451613 USD
    jpy_rate = 155.00
    expected_jpy_pip = 1000.0 / jpy_rate
    actual_jpy_pip = calculate_pip_value_usd("USDJPY", exchange_rate=jpy_rate)
    assert pytest.approx(actual_jpy_pip, rel=1e-5) == expected_jpy_pip

    # USDCHF @ 0.8800: 10 CHF / 0.8800 CHF per USD = $11.363636 USD
    chf_rate = 0.8800
    expected_chf_pip = 10.0 / chf_rate
    actual_chf_pip = calculate_pip_value_usd("USDCHF", exchange_rate=chf_rate)
    assert pytest.approx(actual_chf_pip, rel=1e-5) == expected_chf_pip


def test_position_sizing_eurusd():
    """Test EURUSD position sizing on a $5,000 account risking 1.0% ($50.00)."""
    equity = 5000.0
    risk_pct = 1.0  # 1% = $50.00 risk budget
    sl_pips = 10.0

    lots = calculate_position_size(equity, risk_pct, sl_pips=sl_pips, symbol="EURUSD")
    # Expected: $50.00 / (10 pips * $10.00/pip) = 0.50 lots
    assert lots == 0.50

    actual_risk = calculate_monetary_risk(lots, sl_pips=sl_pips, symbol="EURUSD")
    assert actual_risk == 50.00
    assert actual_risk <= 50.00


def test_position_sizing_usdcad():
    """Test USDCAD position sizing with quote conversion and lot flooring."""
    equity = 5000.0
    risk_pct = 1.0  # $50.00 budget
    sl_pips = 16.0
    rate = 1.4190

    # Pip value = 10 / 1.4190 = 7.047216 USD
    # Loss per lot = 16 * 7.047216 = $112.75546 USD
    # Raw lots = 50 / 112.75546 = 0.443438 lots -> Floored to 0.44 lots
    lots = calculate_position_size(
        equity, risk_pct, sl_pips=sl_pips, symbol="USDCAD", exchange_rate=rate
    )
    assert lots == 0.44

    actual_risk = calculate_monetary_risk(
        lots, sl_pips=sl_pips, symbol="USDCAD", exchange_rate=rate
    )
    # 0.44 * 16 * (10 / 1.4190) = $49.61
    assert actual_risk == 49.61
    assert actual_risk <= 50.00  # Never exceeds $50.00 risk budget!


def test_position_sizing_usdjpy():
    """Test USDJPY position sizing with JPY pip conversion and lot flooring."""
    equity = 5000.0
    risk_pct = 1.0  # $50.00 budget
    sl_pips = 18.0
    rate = 155.00

    # Pip value = 1000 / 155.00 = 6.451613 USD
    # Loss per lot = 18 * 6.451613 = $116.1290 USD
    # Raw lots = 50 / 116.1290 = 0.43055 lots -> Floored to 0.43 lots
    lots = calculate_position_size(
        equity, risk_pct, sl_pips=sl_pips, symbol="USDJPY", exchange_rate=rate
    )
    assert lots == 0.43

    actual_risk = calculate_monetary_risk(
        lots, sl_pips=sl_pips, symbol="USDJPY", exchange_rate=rate
    )
    # 0.43 * 18 * (1000 / 155.00) = $49.94
    assert actual_risk == 49.94
    assert actual_risk <= 50.00


def test_position_sizing_usdchf():
    """Test USDCHF position sizing with CHF quote conversion and lot flooring."""
    equity = 5000.0
    risk_pct = 1.0  # $50.00 budget
    sl_pips = 14.0
    rate = 0.8800

    # Pip value = 10 / 0.8800 = 11.363636 USD
    # Loss per lot = 14 * 11.363636 = $159.0909 USD
    # Raw lots = 50 / 159.0909 = 0.314285 lots -> Floored to 0.31 lots
    lots = calculate_position_size(
        equity, risk_pct, sl_pips=sl_pips, symbol="USDCHF", exchange_rate=rate
    )
    assert lots == 0.31

    actual_risk = calculate_monetary_risk(
        lots, sl_pips=sl_pips, symbol="USDCHF", exchange_rate=rate
    )
    # 0.31 * 14 * (10 / 0.8800) = $49.32
    assert actual_risk == 49.32
    assert actual_risk <= 50.00


def test_zero_or_negative_stop_distance():
    """Verify that zero or negative stop loss distance raises ValueError."""
    with pytest.raises(ValueError, match="strictly positive"):
        calculate_position_size(5000.0, 1.0, sl_pips=0.0, symbol="EURUSD")

    with pytest.raises(ValueError, match="strictly positive"):
        calculate_position_size(5000.0, 1.0, sl_pips=-15.0, symbol="EURUSD")


def test_missing_or_invalid_conversion_rates():
    """Verify that missing conversion rates on non-USD quote pairs raise ValueError."""
    # None exchange rate
    with pytest.raises(ValueError, match="Valid exchange_rate is required"):
        calculate_position_size(5000.0, 1.0, sl_pips=16.0, symbol="USDCAD", exchange_rate=None)

    # 0.0 exchange rate
    with pytest.raises(ValueError, match="Valid exchange_rate is required"):
        calculate_pip_value_usd("USDJPY", exchange_rate=0.0)

    # Negative exchange rate
    with pytest.raises(ValueError, match="Valid exchange_rate is required"):
        calculate_pip_value_usd("USDCHF", exchange_rate=-0.88)


def test_invalid_instrument_specifications():
    """Verify that Gold and unsupported symbols are strictly rejected."""
    # Gold symbols
    for gold in ["XAUUSD", "GOLD", "PAXGUSDT", "XAU/USD"]:
        with pytest.raises(ValueError, match="Gold"):
            calculate_position_size(5000.0, 1.0, sl_pips=10.0, symbol=gold)

        with pytest.raises(ValueError, match="Gold"):
            calculate_pip_value_usd(gold)

    # Unsupported non-forex pairs
    for invalid in ["BTCUSD", "ETHUSD", "AAPL", "INVALID_PAIR"]:
        with pytest.raises(ValueError, match="eligible institutional forex universe"):
            calculate_pip_value_usd(invalid)


def test_minimum_lot_constraints_and_budget_breach_rejection():
    """Verify that calculations return 0.0 (safe rejection) if min_lot breaches risk budget,
    and returns min_lot (0.01) only when min_lot is within the allowed risk budget."""
    # Scenario A: Budget is $1.00 ($100 equity @ 1% risk). EURUSD 25 pip SL risks $2.50 at 0.01 lot.
    # $2.50 exceeds the $1.00 budget! Must NOT force 0.01 lot. Must return 0.0 (trade skipped).
    lots_breach = calculate_position_size(100.0, 1.0, sl_pips=25.0, symbol="EURUSD", min_lot=0.01)
    assert lots_breach == 0.0, f"Expected 0.0 to reject trade over budget, got {lots_breach}"

    # Scenario B: Budget is $3.00 ($300 equity @ 1% risk). EURUSD 25 pip SL risks $2.50 at 0.01 lot.
    # $2.50 <= $3.00 budget. Safe to trade 0.01 lot.
    lots_valid = calculate_position_size(300.0, 1.0, sl_pips=25.0, symbol="EURUSD", min_lot=0.01)
    assert lots_valid == 0.01, f"Expected 0.01 lot, got {lots_valid}"

    # Zero equity or zero risk returns 0.0
    assert calculate_position_size(0.0, 1.0, sl_pips=10.0, symbol="EURUSD") == 0.0
    assert calculate_position_size(5000.0, 0.0, sl_pips=10.0, symbol="EURUSD") == 0.0


def test_lot_step_rounding_and_risk_budget_protection():
    """Verify across arbitrary equities and SLs that floored lots NEVER exceed dollar risk budget."""
    test_cases = [
        (2500.0, 1.0, 14.5, "EURUSD", 1.0850),
        (10000.0, 0.5, 22.0, "USDCAD", 1.4210),
        (50000.0, 1.0, 17.5, "USDJPY", 154.20),
        (5000.0, 0.9, 13.0, "USDCHF", 0.8840),
        (7500.0, 1.5, 19.0, "GBPUSD", 1.2950),
        (3000.0, 0.5, 11.0, "AUDUSD", 0.6520),
    ]

    for equity, risk_pct, sl_pips, sym, rate in test_cases:
        budget = equity * (risk_pct / 100.0)
        lots = calculate_position_size(equity, risk_pct, sl_pips, sym, exchange_rate=rate)
        risk_usd = calculate_monetary_risk(lots, sl_pips, sym, exchange_rate=rate)

        # Flooring guarantees monetary risk <= risk budget (with floating point tolerance)
        assert risk_usd <= budget + 0.01, (
            f"Over-budget violation: {sym} risk ${risk_usd} > budget ${budget} "
            f"for {lots} lots on {equity} equity"
        )


def test_decimal_or_percentage_risk_pct_input():
    """Verify that risk_pct works identically whether passed as 1.0 (1%) or 0.01 (1%)."""
    lots_pct = calculate_position_size(5000.0, 1.0, sl_pips=10.0, symbol="EURUSD")
    lots_dec = calculate_position_size(5000.0, 0.01, sl_pips=10.0, symbol="EURUSD")
    assert lots_pct == lots_dec == 0.50
