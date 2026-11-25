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

import json
import os
from typing import Any, Dict, List, Optional, Tuple

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

# De-whitelisted / Paused pairs due to empirical negative statistical expectancy:
# 1. USDJPY: 2026 BoJ currency intervention regime (20% live win rate, PF 0.38)
# 2. GBPUSD: Structural sweep traps / negative expectancy (0.0% live win rate, 33.3% 5-year backtest WR, PF 0.72)
# 3. XAUUSD: Negative expectancy in 2-year look-ahead-free backtest (38.4% WR, 0.84 PF, -23.06R drag, 57.4% Friday losses)
DEWHITELISTED_PAIRS: set[str] = {"USDJPY", "GBPUSD", "XAUUSD"}

# Active trading universe (Eligible for fresh signal generation and execution)
ACTIVE_FOREX_SYMBOLS: List[str] = [
    sym for sym in CANONICAL_SYMBOLS if sym not in DEWHITELISTED_PAIRS
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
FLASH_PMI_BUFFER_MINUTES: int = 45  # Extended buffer for preliminary Flash PMIs (protects 07:30 UTC London open setups)
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
PROP_FIRM_RISK_PCT: float = 0.75          # 0.75% per trade prop firm calibrated risk
REFERENCE_RISK_BUDGET_USD: float = 50.0   # $5,000.00 * 0.01 = $50.00 max nominal ceiling
PROP_FIRM_RISK_BUDGET_USD: float = 37.5   # $5,000.00 * 0.0075 = $37.50 prop budget

STANDARD_LOT_SIZE: float = 100_000.0      # 1 Standard Lot = 100,000 Base Currency units
DEFAULT_MIN_LOT: float = 0.01             # Broker minimum lot constraint (micro-lot)
DEFAULT_LOT_STEP: float = 0.01            # Broker minimum lot step
DEFAULT_MAX_LOT: float = 100.0            # Institutional max lot ceiling

# ==============================================================================
# 4. PAIR SPECIFICATIONS AND INSTITUTIONAL KILLZONE HOURS (UTC)
# ==============================================================================
# Institutional Volume Hours (UTC): excludes 10:00 (European pre-lunch lull) and 14:00 (US equity open whipsaw)
INSTITUTIONAL_HOURS: List[int] = [7, 8, 9, 11, 12, 13, 15, 16, 17]

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

# Prop Firm Multi-Tier Risk Guardrails (ROP-03)
FIRM_DAILY_LOSS_LIMIT_PCT: float = float(os.getenv("FIRM_DAILY_LOSS_LIMIT_PCT", "5.0"))
BOT_HALT_DAILY_LOSS_PCT: float = float(os.getenv("BOT_HALT_DAILY_LOSS_PCT", "3.0"))  # Internal circuit-breaker below firm limit
DAILY_RESET_HOUR_UTC: int = int(os.getenv("DAILY_RESET_HOUR_UTC", "0"))  # Daily rollover reset hour in UTC (0 for UTC, or broker rollover)

# Weekend Holding Safeguards (Prop Firm Anti-Ban)
FRIDAY_MARKET_FLAT_HOUR_UTC: int = int(os.getenv("FRIDAY_MARKET_FLAT_HOUR_UTC", "20"))  # Auto-close open positions Friday 20:00 UTC
CLOSE_FOREX_BEFORE_WEEKEND: bool = os.getenv("CLOSE_FOREX_BEFORE_WEEKEND", "true").lower() in ("true", "1", "yes")

# Market Order Slippage Protections (Prop Firm Anti-Ban & Execution Defense)
MAX_SLIPPAGE_PIPS: float = float(os.getenv("MAX_SLIPPAGE_PIPS", "3.0"))  # Max tolerated slippage for Forex in pips (3.0 pips = 30 points)
MAX_GOLD_SLIPPAGE_POINTS: float = float(os.getenv("MAX_GOLD_SLIPPAGE_POINTS", "50.0"))  # Max tolerated slippage for Gold in points ($0.50/oz)

# cTrader Order Execution Mode:
# "MARKET": Standard unconditional market execution with atomic relative SL/TP (recommended; immune to broker range rejection)
# "MARKET_RANGE": Enforces baseSlippagePrice and slippageInPoints boundary (broker rejects if price drifts beyond tolerance)
CTRADER_ORDER_TYPE: str = os.getenv("CTRADER_ORDER_TYPE", "MARKET").strip().upper()

# ==============================================================================
# 7. PHASE-ASYMMETRIC DYNAMIC RISK SIZING (RANK 3 PROP ENGINE)
# ==============================================================================
RISK_MODE_DEFAULT: str = "dynamic_rank3"
ACCOUNT_STAGE_DEFAULT: str = "EVALUATION"
PROP_STANDARD_TIER_BALANCES: Tuple[float, ...] = (
    2500.0, 5000.0, 10000.0, 15000.0, 20000.0, 25000.0, 50000.0, 100000.0, 200000.0
)

# Evaluation (Phase 1 & Phase 2): accelerate above -1.5% DD, throttle hard in drawdown
RANK3_EVAL_BOOST_RISK_PCT: float = 1.25
RANK3_EVAL_CAUTION_RISK_PCT: float = 0.75
RANK3_EVAL_CRASH_GUARD_RISK_PCT: float = 0.40
RANK3_EVAL_CAUTION_DD_PCT: float = -1.5
RANK3_EVAL_CRASH_DD_PCT: float = -4.0

# Funded Stage: protect payout license with conservative base & drawdown step-down
RANK3_FUNDED_NORMAL_RISK_PCT: float = 0.75
RANK3_FUNDED_DD_GUARD_RISK_PCT: float = 0.50
RANK3_FUNDED_GUARD_DD_PCT: float = -3.0


def _lookup_account_env_override(env_var: str, account_id: Optional[Any]) -> Optional[str]:
    """Look up a per-account JSON map override (e.g. ACCOUNT_STAGES, INITIAL_BALANCES)."""
    raw = (os.environ.get(env_var) or "").strip()
    if not raw or account_id is None:
        return None
    try:
        mapping = json.loads(raw)
        if isinstance(mapping, dict):
            key = str(account_id).strip()
            if key in mapping:
                return str(mapping[key]).strip()
    except Exception:
        return None
    return None


def infer_prop_initial_balance(current_equity: float, configured_initial: float = 0.0) -> float:
    """Resolve starting prop balance from explicit setting or nearest standard prop tier."""
    if configured_initial > 0.0:
        return float(configured_initial)
    if current_equity <= 0.0:
        return REFERENCE_ACCOUNT_EQUITY

    best_tier: Optional[float] = None
    best_rel_dist = float("inf")
    for tier in PROP_STANDARD_TIER_BALANCES:
        if 0.88 * tier <= current_equity <= 1.12 * tier:
            rel_dist = abs(current_equity - tier) / tier
            if rel_dist < best_rel_dist:
                best_rel_dist = rel_dist
                best_tier = tier

    return float(best_tier) if best_tier is not None else float(current_equity)


def resolve_rank3_risk_pct(
    current_equity: float,
    initial_balance: float = 0.0,
    account_stage: str = ACCOUNT_STAGE_DEFAULT,
) -> Tuple[float, Dict[str, Any]]:
    """Compute Rank 3 Phase-Asymmetric Drawdown-Gated Risk % and diagnostic metadata."""
    base_bal = infer_prop_initial_balance(current_equity, initial_balance)
    dd_pct = ((current_equity - base_bal) / base_bal) * 100.0 if base_bal > 0.0 else 0.0

    raw_stage = str(account_stage or ACCOUNT_STAGE_DEFAULT).strip().upper()
    if raw_stage in ("FUNDED", "LIVE", "PAYOUT"):
        norm_stage = "FUNDED"
        if dd_pct >= RANK3_FUNDED_GUARD_DD_PCT:
            risk_pct = RANK3_FUNDED_NORMAL_RISK_PCT
            tier = "FUNDED_NORMAL"
        else:
            risk_pct = RANK3_FUNDED_DD_GUARD_RISK_PCT
            tier = "FUNDED_DD_GUARD"
    else:
        norm_stage = "EVALUATION"
        if dd_pct >= RANK3_EVAL_CAUTION_DD_PCT:
            risk_pct = RANK3_EVAL_BOOST_RISK_PCT
            tier = "EVAL_BOOST"
        elif dd_pct >= RANK3_EVAL_CRASH_DD_PCT:
            risk_pct = RANK3_EVAL_CAUTION_RISK_PCT
            tier = "EVAL_CAUTION"
        else:
            risk_pct = RANK3_EVAL_CRASH_GUARD_RISK_PCT
            tier = "EVAL_CRASH_GUARD"

    return risk_pct, {
        "mode": RISK_MODE_DEFAULT,
        "stage": norm_stage,
        "tier": tier,
        "initial_balance": round(base_bal, 2),
        "dd_pct": round(dd_pct, 2),
    }


def resolve_effective_risk_pct(
    current_equity: float,
    explicit_risk_pct: Optional[float] = None,
    account_id: Optional[Any] = None,
    default_risk_pct: float = PROP_FIRM_RISK_PCT,
    prefer_dynamic_over_signal: bool = False,
) -> Tuple[float, Dict[str, Any]]:
    """Resolve effective risk % dynamically for live equity, honoring explicit flat overrides.

    Precedence:
    1. Caller-supplied explicit flat risk (`explicit_risk_pct > 0` when `prefer_dynamic_over_signal=False`).
    2. Explicit flat mode (`RISK_MODE=flat` or `ENABLE_DYNAMIC_RISK=false`).
    3. Dynamic Rank 3 mode when `RISK_MODE` is `dynamic`/`dynamic_rank3`/`rank3`.
    4. When `RISK_MODE` is unset: honor explicit `RISK_PCT` env pin if provided; otherwise run Rank 3.
    """
    if explicit_risk_pct is not None and float(explicit_risk_pct) > 0.0 and not prefer_dynamic_over_signal:
        return float(explicit_risk_pct), {
            "mode": "explicit_signal",
            "stage": "CUSTOM",
            "tier": "EXPLICIT",
            "initial_balance": float(current_equity),
            "dd_pct": 0.0,
        }

    enable_dyn = (os.environ.get("ENABLE_DYNAMIC_RISK") or "true").strip().lower() in ("true", "1", "yes")
    risk_mode = (os.environ.get("RISK_MODE") or "").strip().lower()
    env_risk_raw = (os.environ.get("RISK_PCT") or "").strip()

    try:
        env_risk_val = float(env_risk_raw) if env_risk_raw else 0.0
    except ValueError:
        env_risk_val = 0.0

    use_flat = (not enable_dyn) or (risk_mode in ("flat", "fixed", "manual"))
    if not use_flat and not risk_mode and env_risk_val > 0.0:
        # Honor explicit RISK_PCT env pin when RISK_MODE is not explicitly dynamic
        return env_risk_val, {
            "mode": "flat_env_override",
            "stage": "CUSTOM",
            "tier": "ENV_RISK_PCT",
            "initial_balance": float(current_equity),
            "dd_pct": 0.0,
        }

    if use_flat:
        flat_val = env_risk_val if env_risk_val > 0.0 else float(default_risk_pct)
        return flat_val, {
            "mode": "flat",
            "stage": "CUSTOM",
            "tier": "FLAT",
            "initial_balance": float(current_equity),
            "dd_pct": 0.0,
        }

    # Resolve per-account or global INITIAL_BALANCE & ACCOUNT_STAGE
    stage_override = _lookup_account_env_override("ACCOUNT_STAGES", account_id)
    account_stage = stage_override or os.environ.get("ACCOUNT_STAGE") or ACCOUNT_STAGE_DEFAULT

    init_override = _lookup_account_env_override("INITIAL_BALANCES", account_id)
    raw_init = init_override if init_override is not None else (os.environ.get("INITIAL_BALANCE") or "")
    try:
        configured_init = float(raw_init) if str(raw_init).strip() else 0.0
    except ValueError:
        configured_init = 0.0

    return resolve_rank3_risk_pct(
        current_equity=float(current_equity),
        initial_balance=configured_init,
        account_stage=account_stage,
    )



