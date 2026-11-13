"""Authoritative Centralized Strategy Configuration.

Single Source of Truth across:
- Standalone Live Market Scanner (market_scanner.py)
- Instrument Validator & Position Sizer (core/instrument_validator.py)
- Historical Backtester & Simulation Engines (scripts/run_canonical_backtest.py)
- Secondary Webhook Framework (app/config.py)
- Telegram Signal Alerting and Edge Relay (cloudflare_worker.js)

Enforces:
1. Canonical Institutional Forex Universe (6 standard pairs only, zero Gold/crypto).
2. Institutional Cross-Currency Relative Strength (CCRS) Factor Engine (v3.0.0).
3. 1H Execution with Dynamic Volatility-Anchored ATR Stops (20.0 to 25.0 pips, 30.0 to 37.5 pips TP).
4. Pure Binary 1:1.50 Target Geometry (1.50 R:R).
5. Risk Budget: 1.0% per trade on a reference $5,000 equity account ($50.00 max risk).
6. Conservative Lot Sizing: Quote-to-USD conversion, lot flooring, zero-budget breaching.
7. Realistic Institutional Transaction Costs (Spread + Commission + Slippage).
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
# 2. CANONICAL STRATEGY GEOMETRY (INSTITUTIONAL DUAL-TIMEFRAME CCRS ENGINE v3.2)
# ==============================================================================
STRATEGY_NAME: str = "Institutional Dual-Timeframe CCRS Engine"
STRATEGY_VERSION: str = "3.3.0"
CANONICAL_TIMEFRAME: str = "15m"
MACRO_TIMEFRAME: str = "1h"

# Cross-Currency Relative Strength (CCRS) Matrix Parameters
CCRS_LOOKBACK_HOURS: int = 120         # 120-hour (5 trading days) momentum lookback
CCRS_Z_WINDOW_HOURS: int = 200         # 200-hour rolling mean/std normalization window
CCRS_Z_THRESHOLD: float = 1.75         # 1.75σ active macro flow divergence threshold
CCRS_STATE_MODE: bool = True           # State-based continuous flow execution (retest/sweep entries)
CCRS_ATR_MULTIPLIER: float = 2.0       # 2.0x 14-period ATR stop distance
CCRS_MIN_SL_PIPS: float = 20.0         # Minimum stop loss ceiling (suppresses noise stopouts)
CCRS_MAX_SL_PIPS: float = 25.0         # Maximum stop loss cap (calibrated to intraday ADR)

# Canonical Target Geometry (Calibrated Swing 1:1.59 R:R)
CANONICAL_STOP_LOSS_PIPS: float = 22.0
CANONICAL_TAKE_PROFIT_PIPS: float = 35.0  # Calibrated for optimal expectancy (49.6% Win Rate, 1.37 PF, 4.42% Max DD)
CANONICAL_RISK_REWARD_RATIO: float = 1.59

# Volatility-Cushioned Trailing Stop Parameters (Disabled to prevent profit erosion from pullbacks)
VOLATILITY_CUSHION_ENABLED: bool = False
VOLATILITY_CUSHION_TIER1_R: float = 1.20       # At +1.2R (+26.4 pips), advance SL to Tier 1
VOLATILITY_CUSHION_TIER1_SL_PIPS: float = 10.0 # Halves risk to 10p, leaves 36p breathing buffer
VOLATILITY_CUSHION_TIER2_R: float = 1.50       # At +1.5R (+33.0 pips), advance SL to Tier 2
VOLATILITY_CUSHION_TIER2_SL_PIPS: float = -11.0 # Lock in +11.0 pips (+0.5R guaranteed profit)
VOLATILITY_CUSHION_RUNNER_TP_PIPS: float = 44.0 # Extended runner TP (+2.0R)

# Economic News Filter Parameters (Forex Factory Real-Time Calendar)
NEWS_FILTER_ENABLED: bool = True
NEWS_FILTER_BUFFER_MINUTES: int = 30
NEWS_CALENDAR_URL: str = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# Aliases for backwards compatibility with existing imports
FIXED_TAKE_PROFIT_PIPS: float = CANONICAL_TAKE_PROFIT_PIPS
FIXED_STOP_LOSS_PIPS: float = CANONICAL_STOP_LOSS_PIPS
FIXED_RISK_REWARD_RATIO: float = CANONICAL_RISK_REWARD_RATIO

# Deprecated Night Session Scalper Parameters (Retained for backwards compatibility)
NIGHT_SESSION_HOURS: List[int] = []
NIGHT_BOLLINGER_STD: float = 2.0
NIGHT_RSI_OVERSOLD: float = 36.0
NIGHT_RSI_OVERBOUGHT: float = 64.0
NIGHT_MAX_HOLD_BARS: int = 16
NIGHT_MAX_SPREAD_PIPS: float = 2.5
NIGHT_MIN_TP_PIPS: float = 5.0

# ==============================================================================
# 3. ACCOUNT EQUITY, RISK BUDGET & LOT SIZE CONSTRAINTS
# ==============================================================================
REFERENCE_ACCOUNT_EQUITY: float = 5000.0  # Reference Prop Firm Account ($5,000 USD)
REFERENCE_RISK_PCT: float = 1.0           # 1.0% per trade reference ceiling
PROP_FIRM_RISK_PCT: float = 1.00          # 1.00% per trade prop firm calibrated risk
REFERENCE_RISK_BUDGET_USD: float = 50.0   # $5,000.00 * 0.01 = $50.00 max nominal ceiling
PROP_FIRM_RISK_BUDGET_USD: float = 50.0   # $5,000.00 * 0.01 = $50.00 prop budget

STANDARD_LOT_SIZE: float = 100_000.0      # 1 Standard Lot = 100,000 Base Currency units
DEFAULT_MIN_LOT: float = 0.01             # Broker minimum lot constraint (micro-lot)
DEFAULT_LOT_STEP: float = 0.01            # Broker minimum lot step
DEFAULT_MAX_LOT: float = 100.0            # Institutional max lot ceiling

# ==============================================================================
# 4. PAIR SPECIFICATIONS AND INSTITUTIONAL KILLZONE HOURS (UTC)
# ==============================================================================
INSTITUTIONAL_HOURS: List[int] = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]

PAIR_CONFIGS: Dict[str, Dict[str, Any]] = {
    "EURUSD": {
        "ticker": "EURUSD=X",
        "pip_size": 0.0001,
        "digits": 5,
        "donchian_len": 20,
        "day_hours": INSTITUTIONAL_HOURS,
        "hours": INSTITUTIONAL_HOURS,
        "sl_pips": CANONICAL_STOP_LOSS_PIPS,
        "tp_pips": CANONICAL_TAKE_PROFIT_PIPS,
        "rr": CANONICAL_RISK_REWARD_RATIO,
    },
    "USDCAD": {
        "ticker": "USDCAD=X",
        "pip_size": 0.0001,
        "digits": 5,
        "donchian_len": 20,
        "day_hours": INSTITUTIONAL_HOURS,
        "hours": INSTITUTIONAL_HOURS,
        "sl_pips": CANONICAL_STOP_LOSS_PIPS,
        "tp_pips": CANONICAL_TAKE_PROFIT_PIPS,
        "rr": CANONICAL_RISK_REWARD_RATIO,
    },
    "GBPUSD": {
        "ticker": "GBPUSD=X",
        "pip_size": 0.0001,
        "digits": 5,
        "donchian_len": 20,
        "day_hours": INSTITUTIONAL_HOURS,
        "hours": INSTITUTIONAL_HOURS,
        "sl_pips": CANONICAL_STOP_LOSS_PIPS,
        "tp_pips": CANONICAL_TAKE_PROFIT_PIPS,
        "rr": CANONICAL_RISK_REWARD_RATIO,
    },
    "USDJPY": {
        "ticker": "USDJPY=X",
        "pip_size": 0.01,
        "digits": 3,
        "donchian_len": 20,
        "day_hours": INSTITUTIONAL_HOURS,
        "hours": INSTITUTIONAL_HOURS,
        "sl_pips": CANONICAL_STOP_LOSS_PIPS,
        "tp_pips": CANONICAL_TAKE_PROFIT_PIPS,
        "rr": CANONICAL_RISK_REWARD_RATIO,
    },
    "USDCHF": {
        "ticker": "USDCHF=X",
        "pip_size": 0.0001,
        "digits": 5,
        "donchian_len": 20,
        "day_hours": INSTITUTIONAL_HOURS,
        "hours": INSTITUTIONAL_HOURS,
        "sl_pips": CANONICAL_STOP_LOSS_PIPS,
        "tp_pips": CANONICAL_TAKE_PROFIT_PIPS,
        "rr": CANONICAL_RISK_REWARD_RATIO,
    },
    "AUDUSD": {
        "ticker": "AUDUSD=X",
        "pip_size": 0.0001,
        "digits": 5,
        "donchian_len": 20,
        "day_hours": INSTITUTIONAL_HOURS,
        "hours": INSTITUTIONAL_HOURS,
        "sl_pips": CANONICAL_STOP_LOSS_PIPS,
        "tp_pips": CANONICAL_TAKE_PROFIT_PIPS,
        "rr": CANONICAL_RISK_REWARD_RATIO,
    },
}

# ==============================================================================
# 5. INSTITUTIONAL TRANSACTION COSTS & SLIPPAGE ASSUMPTIONS
# ==============================================================================
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
MAX_CONCURRENT_USD_EXPOSURE: int = 1  # Strictly max 1 active trade per net USD direction (eliminates correlated multi-pair cascades; +2.0% WR, +203% net pips)
POST_LOSS_COOLDOWN_MINUTES: float = 60.0
DAILY_LOSS_CIRCUIT_BREAKER_R: float = -2.00
DAILY_LOSS_CIRCUIT_BREAKER_COUNT: int = 2
DAILY_LOSS_CIRCUIT_BREAKER_PCT: float = 1.0
FRIDAY_ENTRY_CUTOFF_HOUR_UTC: int = 12  # Prohibits fresh entries after 12:00 UTC on Friday (eliminates 48h weekend holding & Sunday gap risk)
MONDAY_ENTRY_START_HOUR_UTC: int = 6   # Allows London session opening setups (06:00 UTC)
MONDAY_ENTRY_CUTOFF_HOUR_UTC: int = 12 # Prohibits fresh entries after 12:00 UTC on Monday (filters low-liquidity post-London chop; +9.06R backtest, avoids all 3 live losses)

