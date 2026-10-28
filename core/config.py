"""Authoritative Centralized Strategy Configuration.

Single Source of Truth across:
- Standalone Live Market Scanner (market_scanner.py)
- Instrument Validator & Position Sizer (core/instrument_validator.py)
- Historical Backtester & Simulation Engines (scripts/run_canonical_backtest.py)
- Secondary Webhook Framework (app/config.py)
- Telegram Signal Alerting and Edge Relay

Enforces:
1. Canonical Institutional Forex Universe (6 standard pairs only, zero Gold/crypto).
2. Pure Binary 1:1.50 Target Geometry (Fixed 15.0 pips Take Profit, 10.0 pips Stop Loss).
3. Risk Budget: 1.0% per trade on a reference $5,000 equity account ($50.00 max risk).
4. Conservative Lot Sizing: Quote-to-USD conversion, lot flooring, zero-budget breaching.
5. Realistic Institutional Transaction Costs (Spread + Commission + Slippage).
"""

from typing import Dict, List, Any

# ==============================================================================
# 1. CANONICAL ASSET UNIVERSE (FOREX ONLY - ZERO GOLD / DERIVATIVES)
# ==============================================================================
CANONICAL_SYMBOLS: List[str] = [
    "EURUSD",
    "USDCAD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "AUDUSD",
]

# Strict set for O(1) membership checks
ELIGIBLE_FOREX_SYMBOLS = set(CANONICAL_SYMBOLS)

# Explicitly excluded commodities, crypto, and derivatives
EXCLUDED_GOLD_SYMBOLS = {
    "XAUUSD", "GOLD", "XAU", "XAU/USD", "XAU_USD", "OANDA:XAUUSD",
    "FX:XAUUSD", "GC=F", "XAUUSD=X", "GOLDUSD", "XAUJPY", "XAUEUR",
    "PAXGUSDT", "PAXG", "XAUUSD.PRO", "XAUUSD.M",
}

EXCLUDED_SYMBOLS = EXCLUDED_GOLD_SYMBOLS.union({
    "BTCUSD", "ETHUSD", "BTCUSDT", "ETHUSDT", "SOLUSD",
})

# ==============================================================================
# 2. CANONICAL STRATEGY GEOMETRY (PURE 1:1.50 R:R BINARY EXECUTION & NIGHT SCALPER)
# ==============================================================================
STRATEGY_NAME: str = "Asian Night Statistical Mean-Reversion Scalper"
STRATEGY_VERSION: str = "2.0.0"

# Night Session Mean-Reversion Engine Parameters (21:00 to 05:00 UTC)
NIGHT_SESSION_HOURS: List[int] = [21, 23, 0, 1, 2, 3, 4, 5]  # Skips 22:00 rollover spread spike
NIGHT_BOLLINGER_STD: float = 2.0
NIGHT_RSI_OVERSOLD: float = 36.0
NIGHT_RSI_OVERBOUGHT: float = 64.0
NIGHT_MAX_HOLD_BARS: int = 16  # 4-hour max holding window
NIGHT_MAX_SPREAD_PIPS: float = 2.5
NIGHT_MIN_TP_PIPS: float = 5.0

CANONICAL_TAKE_PROFIT_PIPS: float = 15.0
CANONICAL_STOP_LOSS_PIPS: float = 10.0
CANONICAL_RISK_REWARD_RATIO: float = 1.50  # 15.0 / 10.0

# Aliases for backwards compatibility with existing imports
FIXED_TAKE_PROFIT_PIPS: float = CANONICAL_TAKE_PROFIT_PIPS
FIXED_STOP_LOSS_PIPS: float = CANONICAL_STOP_LOSS_PIPS
FIXED_RISK_REWARD_RATIO: float = CANONICAL_RISK_REWARD_RATIO

# ==============================================================================
# 3. ACCOUNT EQUITY, RISK BUDGET & LOT SIZE CONSTRAINTS
# ==============================================================================
REFERENCE_ACCOUNT_EQUITY: float = 5000.0  # Reference Prop Firm Account ($5,000 USD)
REFERENCE_RISK_PCT: float = 1.0           # 1.0% per trade risk allocation
REFERENCE_RISK_BUDGET_USD: float = 50.0   # $5,000.00 * 0.01 = $50.00 max nominal risk

STANDARD_LOT_SIZE: float = 100_000.0      # 1 Standard Lot = 100,000 Base Currency units
DEFAULT_MIN_LOT: float = 0.01             # Broker minimum lot constraint (micro-lot)
DEFAULT_LOT_STEP: float = 0.01            # Broker minimum lot step
DEFAULT_MAX_LOT: float = 100.0            # Institutional max lot ceiling

# ==============================================================================
# 4. PAIR SPECIFICATIONS AND INSTITUTIONAL KILLZONE HOURS (UTC)
# ==============================================================================
PAIR_CONFIGS: Dict[str, Dict[str, Any]] = {
    "EURUSD": {
        "ticker": "EURUSD=X",
        "pip_size": 0.0001,
        "digits": 5,
        "donchian_len": 20,
        "night_hours": NIGHT_SESSION_HOURS,
        "day_hours": [6, 7, 9, 10, 11, 12, 13, 15],
        "hours": sorted(list(set(NIGHT_SESSION_HOURS + [6, 7, 9, 10, 11, 12, 13, 15]))),
        "sl_pips": CANONICAL_STOP_LOSS_PIPS,
        "tp_pips": CANONICAL_TAKE_PROFIT_PIPS,
        "rr": CANONICAL_RISK_REWARD_RATIO,
    },
    "USDCAD": {
        "ticker": "USDCAD=X",
        "pip_size": 0.0001,
        "digits": 5,
        "donchian_len": 20,
        "night_hours": NIGHT_SESSION_HOURS,
        "day_hours": [10, 11, 13, 14, 15],
        "hours": sorted(list(set(NIGHT_SESSION_HOURS + [10, 11, 13, 14, 15]))),
        "sl_pips": CANONICAL_STOP_LOSS_PIPS,
        "tp_pips": CANONICAL_TAKE_PROFIT_PIPS,
        "rr": CANONICAL_RISK_REWARD_RATIO,
    },
    "GBPUSD": {
        "ticker": "GBPUSD=X",
        "pip_size": 0.0001,
        "digits": 5,
        "donchian_len": 20,
        "night_hours": NIGHT_SESSION_HOURS,
        "day_hours": [13, 14, 16],
        "hours": sorted(list(set(NIGHT_SESSION_HOURS + [13, 14, 16]))),
        "sl_pips": CANONICAL_STOP_LOSS_PIPS,
        "tp_pips": CANONICAL_TAKE_PROFIT_PIPS,
        "rr": CANONICAL_RISK_REWARD_RATIO,
    },
    "USDJPY": {
        "ticker": "USDJPY=X",
        "pip_size": 0.01,
        "digits": 3,
        "donchian_len": 20,
        "night_hours": NIGHT_SESSION_HOURS,
        "day_hours": [6, 7, 9, 10, 11, 12, 13, 15],
        "hours": sorted(list(set(NIGHT_SESSION_HOURS + [6, 7, 9, 10, 11, 12, 13, 15]))),
        "sl_pips": CANONICAL_STOP_LOSS_PIPS,
        "tp_pips": CANONICAL_TAKE_PROFIT_PIPS,
        "rr": CANONICAL_RISK_REWARD_RATIO,
    },
    "USDCHF": {
        "ticker": "USDCHF=X",
        "pip_size": 0.0001,
        "digits": 5,
        "donchian_len": 20,
        "night_hours": NIGHT_SESSION_HOURS,
        "day_hours": [6, 7, 10, 12, 13, 15],
        "hours": sorted(list(set(NIGHT_SESSION_HOURS + [6, 7, 10, 12, 13, 15]))),
        "sl_pips": CANONICAL_STOP_LOSS_PIPS,
        "tp_pips": CANONICAL_TAKE_PROFIT_PIPS,
        "rr": CANONICAL_RISK_REWARD_RATIO,
    },
    "AUDUSD": {
        "ticker": "AUDUSD=X",
        "pip_size": 0.0001,
        "digits": 5,
        "donchian_len": 20,
        "night_hours": NIGHT_SESSION_HOURS,
        "day_hours": [6, 7, 9, 10, 11, 15],
        "hours": sorted(list(set(NIGHT_SESSION_HOURS + [6, 7, 9, 10, 11, 15]))),
        "sl_pips": CANONICAL_STOP_LOSS_PIPS,
        "tp_pips": CANONICAL_TAKE_PROFIT_PIPS,
        "rr": CANONICAL_RISK_REWARD_RATIO,
    },
}

# ==============================================================================
# 5. INSTITUTIONAL TRANSACTION COSTS & SLIPPAGE ASSUMPTIONS
# ==============================================================================
# Modeling institutional ECN conditions: raw interbank spread + $4.00/lot round turn
# commission (0.4 pip eq) + 0.2 pip realistic market fill slippage.
CANONICAL_TRANSACTION_COSTS: Dict[str, Dict[str, float]] = {
    "EURUSD": {"spread_pips": 0.6, "commission_pips": 0.4, "slippage_pips": 0.2, "total_pips": 1.2},
    "USDCAD": {"spread_pips": 0.9, "commission_pips": 0.4, "slippage_pips": 0.2, "total_pips": 1.5},
    "GBPUSD": {"spread_pips": 0.8, "commission_pips": 0.4, "slippage_pips": 0.2, "total_pips": 1.4},
    "USDJPY": {"spread_pips": 0.6, "commission_pips": 0.4, "slippage_pips": 0.2, "total_pips": 1.2},
    "USDCHF": {"spread_pips": 0.9, "commission_pips": 0.4, "slippage_pips": 0.2, "total_pips": 1.5},
    "AUDUSD": {"spread_pips": 0.7, "commission_pips": 0.4, "slippage_pips": 0.2, "total_pips": 1.3},
}

# ==============================================================================
# 6. PORTFOLIO RISK & CIRCUIT BREAKER LIMITS
# ==============================================================================
MAX_CONCURRENT_UNPROTECTED_TRADES: int = 3
MAX_CONCURRENT_USD_EXPOSURE: int = 2
POST_LOSS_COOLDOWN_MINUTES: float = 60.0
DAILY_LOSS_CIRCUIT_BREAKER_R: float = -2.50
DAILY_LOSS_CIRCUIT_BREAKER_COUNT: int = 3
