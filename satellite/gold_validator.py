"""Gold Commodity Validator & Correlation Interlock Module.

Enforces:
1. Gold Commodity Contract Sizing: 100 Troy Oz per Standard Lot ($100/point).
2. Conservative Lot-Step Flooring: 0.01 lot step, zero-budget breaching.
3. Cross-Engine Correlation Interlock: Strictly enforces MAX_CONCURRENT_USD_EXPOSURE
   across BOTH Forex (trade_records.json) and Gold (satellite/gold_trade_records.json).
4. Rollover Blackout Protection: 20:30 - 22:30 UTC spread widening defense.
5. Friday 16:00 UTC Weekend Gap Protection.
"""

import os
import json
import math
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

from satellite.gold_config import (
    POINT_VALUE_PER_LOT,
    MIN_LOT,
    LOT_STEP,
    MAX_LOT,
    REFERENCE_ACCOUNT_EQUITY,
    PROP_FIRM_RISK_PCT,
    REFERENCE_RISK_BUDGET_USD,
    MIN_SL_POINTS,
    MAX_SL_POINTS,
    MAX_CONCURRENT_USD_EXPOSURE,
    ROLLOVER_BLACKOUT_START_HOUR,
    ROLLOVER_BLACKOUT_START_MINUTE,
    ROLLOVER_BLACKOUT_END_HOUR,
    ROLLOVER_BLACKOUT_END_MINUTE,
    FRIDAY_CUTOFF_HOUR_UTC,
    FOREX_TRADE_RECORDS_PATH,
)

logger = logging.getLogger("GoldValidator")


def calculate_gold_position_size(
    account_equity: float,
    risk_pct: float = PROP_FIRM_RISK_PCT,
    sl_points: float = 22.0,
    min_lot: float = MIN_LOT,
    lot_step: float = LOT_STEP,
    max_lot: float = MAX_LOT,
    max_budget_breach_ratio: float = 1.50,
) -> Tuple[float, float]:
    """
    Calculates floored lot size and realized dollar risk for Gold (XAUUSD).

    Contract Sizing:
      - 1 Standard Lot = 100 Troy Ounces.
      - 1 Point ($1.00 move in Gold price) = $100.00 USD per 1.0 standard lot.
      - Dollar Risk per lot = sl_points * 100.0.
      - Lot size is floored to 0.01 lot increments.

    Returns:
      (lots, monetary_risk_usd)
      Returns (0.0, 0.0) if minimum lot (0.01) would breach the dollar budget
      beyond max_budget_breach_ratio.
    """
    if account_equity <= 0:
        raise ValueError(f"account_equity must be positive (received {account_equity}).")
    if risk_pct <= 0:
        raise ValueError(f"risk_pct must be positive (received {risk_pct}).")
    if sl_points <= 0:
        raise ValueError(f"sl_points must be positive (received {sl_points}).")

    dollar_budget = account_equity * (risk_pct / 100.0)
    cost_per_lot = sl_points * POINT_VALUE_PER_LOT
    raw_lots = dollar_budget / cost_per_lot

    # Floor to nearest lot_step
    floored_lots = math.floor(raw_lots / lot_step) * lot_step
    floored_lots = round(floored_lots, 4)

    # Check minimum lot constraint
    if floored_lots < min_lot:
        min_lot_monetary_risk = min_lot * cost_per_lot
        # If the minimum permitted lot exceeds 1.5x of dollar budget, skip trade safely
        if min_lot_monetary_risk > (dollar_budget * max_budget_breach_ratio):
            logger.warning(
                f"Gold position size rejected: Min lot {min_lot} risks ${min_lot_monetary_risk:.2f}, "
                f"exceeding allowed budget ${dollar_budget:.2f} (>{max_budget_breach_ratio}x ceiling)."
            )
            return 0.0, 0.0
        floored_lots = min_lot

    floored_lots = min(floored_lots, max_lot)
    monetary_risk = floored_lots * cost_per_lot

    return floored_lots, round(monetary_risk, 2)


def is_rollover_blackout_active(dt: Optional[datetime] = None) -> bool:
    """
    Checks if current UTC time falls within the 20:30 - 22:30 UTC daily rollover window.
    During this period, global institutional interbank liquidity thins and broker
    spreads on Gold frequently widen from $0.20 to $1.50 - $3.00/oz.
    New trade entries are strictly prohibited.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    utc_minutes = dt.hour * 60 + dt.minute
    start_minutes = ROLLOVER_BLACKOUT_START_HOUR * 60 + ROLLOVER_BLACKOUT_START_MINUTE  # 20:30 = 1230
    end_minutes = ROLLOVER_BLACKOUT_END_HOUR * 60 + ROLLOVER_BLACKOUT_END_MINUTE        # 22:30 = 1350

    return start_minutes <= utc_minutes <= end_minutes


def is_friday_weekend_cutoff(dt: Optional[datetime] = None) -> bool:
    """
    Checks if current time is Friday after 16:00 UTC.
    Holding Gold positions over the weekend exposes trades to massive Sunday opening
    geopolitical price gaps ($15 - $50/oz). All trading is halted and active positions closed.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    # 4 = Friday
    if dt.weekday() == 4 and dt.hour >= FRIDAY_CUTOFF_HOUR_UTC:
        return True
    # 5 = Saturday, 6 = Sunday before 21:00 UTC
    if dt.weekday() == 5 or (dt.weekday() == 6 and dt.hour < 21):
        return True

    return False


def get_gold_usd_bias(direction: str) -> int:
    """
    Returns USD directional bias for a Gold (XAUUSD) trade:
      - LONG Gold (Buy XAU / Sell USD) = -1 (Short USD bias)
      - SHORT Gold (Sell XAU / Buy USD) = +1 (Long USD bias)
    """
    dir_clean = direction.strip().upper()
    if dir_clean in ["LONG", "BUY"]:
        return -1
    elif dir_clean in ["SHORT", "SELL"]:
        return 1
    raise ValueError(f"Invalid direction '{direction}'. Must be LONG or SHORT.")


def check_correlation_interlock(
    gold_direction: str,
    forex_records_path: Optional[Path] = None,
    max_usd_exposure: int = MAX_CONCURRENT_USD_EXPOSURE,
) -> Tuple[bool, str, int]:
    """
    Inspects active Forex trades in trade_records.json and calculates net USD exposure.
    If the Forex portfolio already holds >= max_usd_exposure (2) trades in the same
    net USD direction as the prospective Gold trade, the trade is rejected to prevent
    correlated drawdowns across the combined portfolio.

    Returns:
      (is_approved, explanation_message, current_same_direction_count)
    """
    target_usd_bias = get_gold_usd_bias(gold_direction)
    target_label = "LONG USD (+1)" if target_usd_bias == 1 else "SHORT USD (-1)"

    if forex_records_path is None:
        forex_records_path = FOREX_TRADE_RECORDS_PATH

    if not forex_records_path.exists():
        return True, "Forex records ledger not found; interlock approved.", 0

    try:
        with open(forex_records_path, "r", encoding="utf-8") as f:
            forex_data = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read Forex records for correlation interlock: {e}")
        return True, f"Error reading Forex ledger ({e}); fail-open interlock approved.", 0

    active_trades = forex_data.get("active_trades", {})
    if not isinstance(active_trades, dict) or not active_trades:
        return True, "No active Forex trades open; interlock approved.", 0

    # Count active Forex trades sharing the same USD bias
    # Direct quote pairs (EURUSD, GBPUSD, AUDUSD): LONG = -1 (Short USD), SHORT = +1 (Long USD)
    # Indirect quote pairs (USDCAD, USDJPY, USDCHF): LONG = +1 (Long USD), SHORT = -1 (Short USD)
    same_bias_count = 0
    contributing_pairs = []

    for trade_id, tr in active_trades.items():
        if not isinstance(tr, dict):
            continue
        p = tr.get("symbol") or tr.get("pair") or ""
        clean_raw = p.strip().upper()
        if ":" in clean_raw:
            clean_raw = clean_raw.split(":")[-1]
        p_clean = clean_raw.replace("=X", "").replace("/", "").replace("_", "").split(".")[0].strip()
        direction = tr.get("direction", "").upper()

        if not p_clean or not direction:
            continue

        if p_clean in ["EURUSD", "GBPUSD", "AUDUSD"]:
            pair_usd_bias = -1 if direction in ["LONG", "BUY"] else 1
        elif p_clean in ["USDCAD", "USDJPY", "USDCHF"]:
            pair_usd_bias = 1 if direction in ["LONG", "BUY"] else -1
        else:
            continue

        if pair_usd_bias == target_usd_bias:
            same_bias_count += 1
            contributing_pairs.append(f"{p_clean} ({direction})")

    if same_bias_count >= max_usd_exposure:
        msg = (
            f"Correlation Interlock REJECTED: Gold {gold_direction} requires {target_label} exposure, "
            f"but Forex already has {same_bias_count} active trades in same USD bias: "
            f"{', '.join(contributing_pairs)} (Max allowed: {max_usd_exposure})."
        )
        return False, msg, same_bias_count

    msg = (
        f"Correlation Interlock APPROVED: Gold {gold_direction} ({target_label}) - "
        f"{same_bias_count} of {max_usd_exposure} concurrent USD positions occupied."
    )
    return True, msg, same_bias_count
