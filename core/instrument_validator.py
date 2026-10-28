"""Centralized Instrument Eligibility Validator and Execution Geometry Module.

Enforces:
1. Complete exclusion of Gold (XAUUSD and all aliases).
2. Restriction to standard institutional Forex currency pairs only.
3. Fixed 15-pip Take Profit and 10-pip Stop Loss calculations (Pure Binary 1:1.50 R:R).
4. Symbol-specific pip conversion and broker precision.
5. Prop-firm risk-based position sizing and currency conversion.
6. Zero-budget breaching: Rejects trades if minimum lot constraint would exceed risk budget.
"""

import math
import re
from typing import Tuple, Dict, Any, Optional

from core.config import (
    CANONICAL_SYMBOLS,
    ELIGIBLE_FOREX_SYMBOLS,
    EXCLUDED_GOLD_SYMBOLS,
    EXCLUDED_SYMBOLS,
    CANONICAL_TAKE_PROFIT_PIPS,
    CANONICAL_STOP_LOSS_PIPS,
    CANONICAL_RISK_REWARD_RATIO,
    PAIR_CONFIGS,
    STANDARD_LOT_SIZE,
    DEFAULT_MIN_LOT,
    DEFAULT_LOT_STEP,
    DEFAULT_MAX_LOT,
    REFERENCE_ACCOUNT_EQUITY,
    REFERENCE_RISK_PCT,
)

# Known Gold aliases and patterns across all data providers and brokers
KNOWN_GOLD_ALIASES = EXCLUDED_GOLD_SYMBOLS

# Universal Strategy Exits (Non-negotiable baseline: 15.0 TP / 10.0 SL)
FIXED_TAKE_PROFIT_PIPS: float = CANONICAL_TAKE_PROFIT_PIPS
FIXED_STOP_LOSS_PIPS: float = CANONICAL_STOP_LOSS_PIPS
FIXED_RISK_REWARD_RATIO: float = CANONICAL_RISK_REWARD_RATIO

# Standardized Pair Schedules - All 6 Institutional Pairs strictly follow 15p TP / 10p SL
PAIR_SCHEDULES: Dict[str, Dict[str, Any]] = {
    sym: {
        "sl_pips": CANONICAL_STOP_LOSS_PIPS,
        "tp_pips": CANONICAL_TAKE_PROFIT_PIPS,
        "tp_rr": CANONICAL_RISK_REWARD_RATIO,
        "bank_pct": 0.0,
        "hours": PAIR_CONFIGS[sym]["hours"],
    }
    for sym in CANONICAL_SYMBOLS
}


def normalize_symbol_string(raw_symbol: str) -> str:
    """Normalize raw ticker strings (e.g. 'OANDA:EUR_USD', 'EURUSD=X') to standard 'EURUSD'."""
    if not raw_symbol or not isinstance(raw_symbol, str):
        return ""
    clean = raw_symbol.strip().upper()
    if ":" in clean:
        clean = clean.split(":")[-1]
    clean = clean.replace("=X", "").replace("/", "").replace("_", "").replace(".", "").strip()
    return clean


def is_gold_symbol(symbol: str) -> bool:
    """Check if symbol corresponds to Gold or any known Gold derivative/alias."""
    if not symbol or not isinstance(symbol, str):
        return False
    norm = normalize_symbol_string(symbol)
    raw_upper = symbol.strip().upper()

    if norm in KNOWN_GOLD_ALIASES or raw_upper in KNOWN_GOLD_ALIASES:
        return True
    if "XAU" in norm or "GOLD" in norm or "XAU" in raw_upper or "GOLD" in raw_upper or "PAXG" in norm or "PAXG" in raw_upper:
        return True
    return False


def is_forex_symbol(symbol: str) -> bool:
    """Check if symbol is an eligible standard forex currency pair."""
    norm = normalize_symbol_string(symbol)
    return norm in ELIGIBLE_FOREX_SYMBOLS


def validate_instrument_eligibility(symbol: str) -> Tuple[bool, str]:
    """
    Centralized instrument-eligibility validator.
    Rejects Gold and any non-forex pair.
    """
    if not symbol or not isinstance(symbol, str):
        return False, "Instrument validation failed: Empty or invalid symbol string."

    if is_gold_symbol(symbol):
        return (
            False,
            f"Symbol '{symbol}' REJECTED: Gold (XAUUSD) trading is permanently excluded. "
            f"Only standard forex pairs are eligible.",
        )

    norm = normalize_symbol_string(symbol)
    if norm not in ELIGIBLE_FOREX_SYMBOLS:
        return (
            False,
            f"Symbol '{symbol}' (normalized: '{norm}') REJECTED: "
            f"Not in verified institutional pair whitelist ({', '.join(sorted(ELIGIBLE_FOREX_SYMBOLS))}).",
        )

    return True, f"Symbol '{norm}' is an approved eligible forex pair."


def get_symbol_spec(symbol: str) -> Dict[str, Any]:
    """
    Retrieve instrument specifications including pip size, broker display digits,
    contract specifications, and canonical risk/reward parameters.
    """
    norm = normalize_symbol_string(symbol)
    cfg = PAIR_CONFIGS.get(norm, {})
    is_jpy = "JPY" in norm

    pip_size = cfg.get("pip_size", 0.01 if is_jpy else 0.0001)
    digits = cfg.get("digits", 3 if is_jpy else 5)
    contract_size = STANDARD_LOT_SIZE

    return {
        "symbol": norm,
        "is_jpy": is_jpy,
        "pip_size": pip_size,
        "digits": digits,
        "contract_size": contract_size,
        "default_tp_pips": CANONICAL_TAKE_PROFIT_PIPS,
        "default_sl_pips": CANONICAL_STOP_LOSS_PIPS,
        "rr_ratio": CANONICAL_RISK_REWARD_RATIO,
        "calibrated_tp_pips": CANONICAL_TAKE_PROFIT_PIPS,
        "calibrated_sl_pips": CANONICAL_STOP_LOSS_PIPS,
        "calibrated_rr": CANONICAL_RISK_REWARD_RATIO,
        "bank_pct": 0.0,
        "hours": cfg.get("hours", list(range(6, 17))),
    }


def pip_size_for_symbol(symbol: str) -> float:
    """Return pip size for the symbol (0.01 for JPY pairs, 0.0001 for standard pairs)."""
    return get_symbol_spec(symbol)["pip_size"]


def calculate_tp_sl(
    entry: float,
    direction: str,
    symbol: str,
    tp_pips: float = CANONICAL_TAKE_PROFIT_PIPS,
    sl_pips: float = CANONICAL_STOP_LOSS_PIPS,
) -> Tuple[float, float]:
    """
    Calculate exact Take-Profit and Stop-Loss prices anchored to the actual entry price.

    Canonical Strategy (Pure Binary 1:1.50):
      Long trade:
        SL price = actual entry price - (sl_pips * pip_size)
        TP price = actual entry price + (tp_pips * pip_size)

      Short trade:
        SL price = actual entry price + (sl_pips * pip_size)
        TP price = actual entry price - (tp_pips * pip_size)
    """
    spec = get_symbol_spec(symbol)
    pip_size = spec["pip_size"]
    digits = spec["digits"]

    dir_upper = direction.strip().upper()
    if dir_upper not in ["LONG", "SHORT", "BUY", "SELL"]:
        raise ValueError(f"Invalid direction '{direction}'. Must be LONG or SHORT.")

    is_long = dir_upper in ["LONG", "BUY"]

    if is_long:
        sl = round(entry - (sl_pips * pip_size), digits)
        tp = round(entry + (tp_pips * pip_size), digits)
    else:
        sl = round(entry + (sl_pips * pip_size), digits)
        tp = round(entry - (tp_pips * pip_size), digits)

    return tp, sl


def calculate_pip_value_usd(
    symbol: str,
    exchange_rate: Optional[float] = None,
    contract_size: float = STANDARD_LOT_SIZE,
) -> float:
    """
    Calculate the monetary value of 1 pip per standard lot in account currency (USD).

    Forex Pricing Model:
      - 1 Standard Lot = 100,000 units of Base currency.
      - 1 Pip distance:
          - JPY pairs (digits=3): pip_size = 0.01
          - Standard pairs (digits=5): pip_size = 0.0001
      - Pip value in quote currency = pip_size * contract_size
          - EURUSD, GBPUSD, AUDUSD -> 10.0 USD
          - USDCAD -> 10.0 CAD
          - USDCHF -> 10.0 CHF
          - USDJPY -> 1,000.0 JPY
      - Account Currency Conversion (USD):
          - Direct Quote pairs (XXX/USD): 10.0 USD
          - Indirect Quote pairs (USD/XXX): (pip_size * contract_size) / exchange_rate
    """
    if is_gold_symbol(symbol):
        raise ValueError(f"Gold trading is disabled and excluded: '{symbol}'.")

    norm = normalize_symbol_string(symbol)
    if norm not in ELIGIBLE_FOREX_SYMBOLS:
        raise ValueError(f"Symbol '{symbol}' ({norm}) is not in the eligible institutional forex universe.")

    spec = get_symbol_spec(norm)
    pip_size = spec["pip_size"]
    contract = float(contract_size or spec.get("contract_size", STANDARD_LOT_SIZE))

    # Quote currency is USD (Direct Quote): EURUSD, GBPUSD, AUDUSD
    if norm.endswith("USD"):
        return pip_size * contract  # Exactly 10.0 USD

    # Base currency is USD, Quote is non-USD (Indirect Quote): USDCAD, USDJPY, USDCHF
    if norm.startswith("USD"):
        if exchange_rate is None or exchange_rate <= 0:
            raise ValueError(
                f"Valid exchange_rate is required for quote currency conversion of non-USD pair '{symbol}' (received {exchange_rate})."
            )
        return (pip_size * contract) / float(exchange_rate)

    raise ValueError(f"Unsupported currency conversion structure for symbol '{symbol}'.")


def calculate_position_size(
    account_equity: float,
    risk_pct: float,
    sl_pips: float = CANONICAL_STOP_LOSS_PIPS,
    symbol: str = "EURUSD",
    exchange_rate: Optional[float] = None,
    pip_value_usd_per_lot: Optional[float] = None,
    min_lot: float = DEFAULT_MIN_LOT,
    lot_step: float = DEFAULT_LOT_STEP,
    max_lot: float = DEFAULT_MAX_LOT,
) -> float:
    """
    Calculate position size (lots) based on account equity, risk percentage, and stop-loss distance.

    Enforces Non-Negotiable Financial Safety Invariants:
      1. Instrument-specific pip size and contract specifications (100,000 base units).
      2. Accurate quote-to-USD exchange rate conversion (e.g. USDCAD, USDJPY, USDCHF).
      3. Conservative lot-step flooring (0.01 step) to guarantee monetary risk never exceeds budget.
      4. ZERO RISK BUDGET BREACHING: If the computed lot size is less than min_lot (0.01),
         returns 0.0 to safely reject/skip the trade rather than forcing a position that exceeds the budget.
    """
    if is_gold_symbol(symbol):
        raise ValueError(f"Gold trading is disabled and excluded from position sizing: '{symbol}'.")

    if sl_pips <= 0:
        raise ValueError(f"Stop-loss distance must be strictly positive (> 0 pips). Received {sl_pips}.")

    if account_equity <= 0 or risk_pct <= 0:
        return 0.0

    # Support risk_pct passed as percentage (e.g. 1.0 for 1%) or decimal fraction (e.g. 0.01 for 1%)
    fraction = (risk_pct / 100.0) if risk_pct > 0.10 else risk_pct
    dollar_risk_budget = account_equity * fraction

    if pip_value_usd_per_lot is None or pip_value_usd_per_lot <= 0:
        pip_value_usd = calculate_pip_value_usd(symbol, exchange_rate)
    else:
        pip_value_usd = float(pip_value_usd_per_lot)

    loss_per_standard_lot = sl_pips * pip_value_usd
    if loss_per_standard_lot <= 0:
        return 0.0

    raw_lots = dollar_risk_budget / loss_per_standard_lot

    # Conservative lot step flooring: ensure rounding does not violate maximum risk budget
    step_decimals = max(0, -int(math.floor(math.log10(lot_step)))) if lot_step < 1 else 0
    floored_lots = math.floor((raw_lots / lot_step) + 1e-9) * lot_step
    lots = round(floored_lots, step_decimals)

    # Strict Risk Budget Guard:
    # If the budget cannot accommodate at least the broker minimum lot (min_lot),
    # return 0.0 to signal safe rejection instead of forcing min_lot which breaches budget.
    if lots < min_lot:
        return 0.0

    if lots > max_lot:
        lots = max_lot

    return lots


def calculate_monetary_risk(
    lots: float,
    sl_pips: float,
    symbol: str = "EURUSD",
    exchange_rate: Optional[float] = None,
    pip_value_usd_per_lot: Optional[float] = None,
) -> float:
    """
    Calculate the exact monetary dollar risk for an executed position.

    Formula:
      monetary_risk_usd = lots * sl_pips * pip_value_usd
    """
    if lots <= 0 or sl_pips <= 0:
        return 0.0

    if pip_value_usd_per_lot is None or pip_value_usd_per_lot <= 0:
        pip_value_usd = calculate_pip_value_usd(symbol, exchange_rate)
    else:
        pip_value_usd = float(pip_value_usd_per_lot)

    return round(lots * sl_pips * pip_value_usd, 2)
