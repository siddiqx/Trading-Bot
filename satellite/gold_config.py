"""Authoritative Configuration for the Isolated Gold Satellite Engine.

Operates strictly decoupled from the canonical Forex engine (market_scanner.py).
Governs:
1. Gold Commodity Contract Specifications (100 oz / lot, $100/point).
2. Dynamic Volatility-Anchored Exits (2.0x ATR, bounded $20.00 to $35.00 points).
3. Volatility Cushion Trailing Stop (+1.20R risk halving, +1.50R profit lock, +2.00R runner).
4. Cross-Engine Correlation Interlock (Enforces portfolio-wide Max 2 net USD exposure).
5. Rollover Blackout (20:30 - 22:30 UTC) & Friday 16:00 UTC weekend flat rule.
6. Prop Firm Calibrated Sizing ($5,000 reference account, 0.50% risk = $25.00 budget).
"""

import os
from pathlib import Path
from typing import Dict, Any

# ==============================================================================
# 1. ASSET SPECIFICATIONS & CONTRACT GEOMETRY
# ==============================================================================
GOLD_SYMBOL: str = "XAUUSD"
GOLD_TICKER: str = "GC=F"  # Continuous front-month Gold futures contract on Yahoo Finance
CONTRACT_SIZE_OZ: float = 100.0  # 1 Standard Lot = 100 Troy Ounces
POINT_VALUE_PER_LOT: float = 100.0  # $1.00 move in Gold price = $100.00 USD per 1.0 standard lot
MIN_LOT: float = 0.01  # 0.01 lot = 1.0 Troy Ounce (minimum broker micro-lot)
LOT_STEP: float = 0.01
MAX_LOT: float = 10.0

# ==============================================================================
# 2. STRATEGY EXITS & VOLATILITY CUSHION TRAILING
# ==============================================================================
STRATEGY_NAME: str = "Gold-Native Dual-Timeframe CCRS Engine"
STRATEGY_VERSION: str = "1.0.0"
TIMEFRAME: str = "1h"
MACRO_TIMEFRAME: str = "4h"

# CCRS Macro USD Factor
CCRS_LOOKBACK_HOURS: int = 120
CCRS_Z_WINDOW_HOURS: int = 200
CCRS_USD_THRESHOLD: float = 1.75  # |Z_USD| >= 1.75σ establishes macro directional flow

# Volatility-Anchored Dynamic Stops
ATR_PERIOD: int = 14
ATR_MULTIPLIER: float = 2.0
MIN_SL_POINTS: float = 20.0  # $20.00/oz stop loss floor (suppresses intraday noise)
MAX_SL_POINTS: float = 35.0  # $35.00/oz stop loss cap (calibrated to intraday range)
BASE_RISK_REWARD_RATIO: float = 1.50

# Volatility Cushion Trailing Stop
VOLATILITY_CUSHION_ENABLED: bool = True
VOLATILITY_CUSHION_TIER1_R: float = 1.20   # At +1.20R, advance SL to 0.50R initial risk (halves risk)
VOLATILITY_CUSHION_TIER2_R: float = 1.50   # At +1.50R, lock in +0.50R guaranteed profit
VOLATILITY_CUSHION_RUNNER_R: float = 2.00  # Extend runner TP to +2.00R

# Timeouts & Circuit Breaker
MAX_HOLD_HOURS: int = 48
DAILY_LOSS_CIRCUIT_BREAKER_COUNT: int = 2
POST_LOSS_COOLDOWN_MINUTES: float = 60.0

# ==============================================================================
# 3. ACCOUNT RISK BUDGET & SIZING CONSTRAINTS
# ==============================================================================
REFERENCE_ACCOUNT_EQUITY: float = float(os.environ.get("ACCOUNT_EQUITY", "25000.0"))
PROP_FIRM_RISK_PCT: float = float(os.environ.get("RISK_PCT", "1.00"))  # 1.00% calibrated prop risk
REFERENCE_RISK_BUDGET_USD: float = REFERENCE_ACCOUNT_EQUITY * (PROP_FIRM_RISK_PCT / 100.0)

# ==============================================================================
# 4. CROSS-ENGINE CORRELATION INTERLOCK & SESSION TIMING
# ==============================================================================
MAX_CONCURRENT_USD_EXPOSURE: int = 2  # Portfolio-wide ceiling across Forex and Gold

# Rollover Blackout Window (UTC): 20:30 to 22:30
ROLLOVER_BLACKOUT_START_HOUR: int = 20
ROLLOVER_BLACKOUT_START_MINUTE: int = 30
ROLLOVER_BLACKOUT_END_HOUR: int = 22
ROLLOVER_BLACKOUT_END_MINUTE: int = 30

# Friday Cutoff (UTC): Flat exit before weekend
FRIDAY_CUTOFF_HOUR_UTC: int = 16

# Monday Session Window Hours (Option A: 06:00–12:00 UTC)
MONDAY_ENTRY_START_HOUR_UTC: int = 6
MONDAY_ENTRY_CUTOFF_HOUR_UTC: int = 12

# Permitted Active Trading Volume Hours (UTC): 06:00 to 18:00
ACTIVE_TRADING_HOURS: list[int] = list(range(6, 18))

# ==============================================================================
# 5. TRANSACTION COSTS (INSTITUTIONAL ECN COMMODITY PRICING)
# ==============================================================================
TRANSACTION_COSTS: Dict[str, float] = {
    "spread_points": 0.20,       # $0.20/oz standard institutional ECN spread
    "commission_points": 0.06,   # $0.06/oz ($6.00 per 100 oz standard lot)
    "slippage_points": 0.10,     # $0.10/oz realistic execution slippage
    "total_points": 0.36,        # $0.36/oz round-turn total friction ($36/lot)
}

# ==============================================================================
# 6. PERSISTENCE PATHS
# ==============================================================================
ROOT_DIR = Path(__file__).resolve().parent.parent
GOLD_TRADE_RECORDS_PATH: Path = ROOT_DIR / "data" / "gold_trade_records.json"
FOREX_TRADE_RECORDS_PATH: Path = ROOT_DIR / "trade_records.json"
