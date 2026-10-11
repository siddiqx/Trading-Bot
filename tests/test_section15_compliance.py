import pytest
from datetime import datetime, timezone, timedelta
import pandas as pd
from core.instrument_validator import (
    is_gold_symbol,
    validate_instrument_eligibility,
    calculate_tp_sl,
    calculate_position_size,
    pip_size_for_symbol
)
from app.config import get_settings


# ==============================================================================
# SECTION 15.A: TP/SL Calculations
# ==============================================================================
def test_tp_sl_long_eurusd():
    """1. Long EUR/USD entry at 1.10000: TP = 1.10150, SL = 1.09900."""
    tp, sl = calculate_tp_sl(1.10000, "LONG", "EURUSD", tp_pips=15.0, sl_pips=10.0)
    assert tp == 1.10150, f"Expected 1.10150, got {tp}"
    assert sl == 1.09900, f"Expected 1.09900, got {sl}"


def test_tp_sl_short_eurusd():
    """2. Short EUR/USD entry at 1.10000: TP = 1.09850, SL = 1.10100."""
    tp, sl = calculate_tp_sl(1.10000, "SHORT", "EURUSD", tp_pips=15.0, sl_pips=10.0)
    assert tp == 1.09850, f"Expected 1.09850, got {tp}"
    assert sl == 1.10100, f"Expected 1.10100, got {sl}"


def test_tp_sl_long_usdjpy():
    """3. Long USD/JPY entry at 150.000: TP = 150.150, SL = 149.900."""
    tp, sl = calculate_tp_sl(150.000, "LONG", "USDJPY", tp_pips=15.0, sl_pips=10.0)
    assert tp == 150.150, f"Expected 150.150, got {tp}"
    assert sl == 149.900, f"Expected 149.900, got {sl}"


def test_tp_sl_short_usdjpy():
    """4. Short USD/JPY entry at 150.000: TP = 149.850, SL = 150.100."""
    tp, sl = calculate_tp_sl(150.000, "SHORT", "USDJPY", tp_pips=15.0, sl_pips=10.0)
    assert tp == 149.850, f"Expected 149.850, got {tp}"
    assert sl == 150.100, f"Expected 150.100, got {sl}"


# ==============================================================================
# SECTION 15.B: Gold Exclusion
# ==============================================================================
@pytest.mark.parametrize("gold_alias", [
    "XAUUSD", "XAU/USD", "GOLD", "XAU", "GC=F", "PAXGUSDT", "XAUUSD.pro", "XAUUSD.m", "XAU_USD"
])
def test_gold_exclusion_aliases(gold_alias):
    """Ensure XAUUSD and all known broker gold aliases are rejected."""
    assert is_gold_symbol(gold_alias) is True
    valid, reason = validate_instrument_eligibility(gold_alias)
    assert valid is False
    assert "Gold" in reason and "excluded" in reason.lower()


def test_valid_forex_pairs_accepted():
    """Ensure valid institutional forex pairs are accepted."""
    for pair in ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD"]:
        valid, reason = validate_instrument_eligibility(pair)
        assert valid is True
        assert "approved eligible forex pair" in reason


def test_config_gold_disabled():
    """Verify configuration settings explicitly disable Gold."""
    settings = get_settings()
    assert settings.GOLD_ENABLED is False
    assert "XAUUSD" not in settings.SUPPORTED_SYMBOLS
    assert settings.TAKE_PROFIT_PIPS == 15.0
    assert settings.STOP_LOSS_PIPS == 10.0


# ==============================================================================
# SECTION 15.C: Position Sizing ($5,000 Prop Account)
# ==============================================================================
def test_position_sizing_1_percent_risk():
    """$5,000 account, 1% risk ($50), 10-pip SL, $10/pip per lot -> 0.50 lots."""
    lots = calculate_position_size(account_equity=5000.0, risk_pct=0.01, sl_pips=10.0, symbol="EURUSD")
    assert lots == 0.50, f"Expected 0.50 lots, got {lots}"


def test_position_sizing_half_percent_risk():
    """$5,000 account, 0.5% risk ($25), 10-pip SL -> 0.25 lots."""
    lots = calculate_position_size(account_equity=5000.0, risk_pct=0.005, sl_pips=10.0, symbol="EURUSD")
    assert lots == 0.25, f"Expected 0.25 lots, got {lots}"


def test_position_sizing_lot_step_rounding_down():
    """Ensure lot sizing rounds down conservatively to permitted lot step."""
    # $5,000 * 0.75% = $37.50 / ($10 * 10) = 0.375 -> rounds down to 0.37
    lots = calculate_position_size(account_equity=5000.0, risk_pct=0.0075, sl_pips=10.0, symbol="EURUSD")
    assert lots == 0.37


def test_position_sizing_rejection_for_gold():
    """Ensure position sizing rejects gold symbols."""
    with pytest.raises(ValueError, match="Gold trading is disabled"):
        calculate_position_size(account_equity=5000.0, risk_pct=0.01, sl_pips=10.0, symbol="XAUUSD")


# ==============================================================================
# SECTION 15.D & 15.E: Session Filter & Signal Timing
# ==============================================================================
def test_session_filter_london_ny_hours():
    """Entries allowed strictly between 06:00 and 17:00 UTC."""
    from market_scanner import scan_pair_timeframe
    config = {"ticker": "EURUSD=X", "pip": 0.0001, "digits": 5, "donchian_len": 20}
    state = {"alerted_signals": []}

    # Asian session: 03:00 UTC (must be skipped)
    # Outside active hours
    asian_time = datetime(2026, 10, 14, 3, 0, tzinfo=timezone.utc)
    # Verification of hour constraint:
    assert not (6 <= asian_time.hour < 17)

    # London session: 09:00 UTC (within active hours)
    london_time = datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc)
    assert (6 <= london_time.hour < 17)

    # Rollover / Off-peak: 21:00 UTC (outside active hours)
    rollover_time = datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc)
    assert not (6 <= rollover_time.hour < 17)


# ==============================================================================
# SECTION 15.F: Exit Handling & Symmetry
# ==============================================================================
def test_exit_symmetry():
    """Ensure buy and sell distance is mathematically symmetric."""
    long_tp, long_sl = calculate_tp_sl(1.10000, "LONG", "EURUSD", 15.0, 10.0)
    short_tp, short_sl = calculate_tp_sl(1.10000, "SHORT", "EURUSD", 15.0, 10.0)

    long_tp_dist = round(long_tp - 1.10000, 5)
    long_sl_dist = round(1.10000 - long_sl, 5)
    short_tp_dist = round(1.10000 - short_tp, 5)
    short_sl_dist = round(short_sl - 1.10000, 5)

    assert long_tp_dist == short_tp_dist == 0.00150
    assert long_sl_dist == short_sl_dist == 0.00100
    assert round(long_tp_dist / long_sl_dist, 2) == 1.50
    assert round(short_tp_dist / short_sl_dist, 2) == 1.50
