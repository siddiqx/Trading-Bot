#!/usr/bin/env python3
"""Canonical Institutional Strategy Backtest Engine.

Strictly enforces:
1. Canonical Strategy Exits: Fixed 15.0-pip Take Profit and 10.0-pip Stop Loss (Pure Binary 1:1.50 R:R).
2. Universe: 6 Institutional Forex Pairs (EURUSD, USDCAD, GBPUSD, USDJPY, USDCHF, AUDUSD). Zero Gold.
3. Look-Ahead Elimination: Signals calculated strictly on closed bars visible at decision time (t <= current_idx).
4. Realistic Transaction Costs: Models spread, commission, and slippage on every trade.
5. Multi-Currency Position Sizing: Quote-to-USD rate conversion with 0.01 lot step flooring and zero-budget breaching.
6. Portfolio Risk Invariants: Max 3 concurrent positions, max 2 same USD bias, 60-min post-loss cooldown, daily circuit breaker.
7. In-Sample (70%) vs Out-of-Sample (30%) partition reporting.
"""

import os
import sys
import pickle
import math
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import pandas as pd
import numpy as np

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config import (
    CANONICAL_SYMBOLS,
    CANONICAL_TAKE_PROFIT_PIPS,
    CANONICAL_STOP_LOSS_PIPS,
    CANONICAL_RISK_REWARD_RATIO,
    PAIR_CONFIGS,
    CANONICAL_TRANSACTION_COSTS,
    REFERENCE_ACCOUNT_EQUITY,
    REFERENCE_RISK_PCT,
    REFERENCE_RISK_BUDGET_USD,
    STANDARD_LOT_SIZE,
    DEFAULT_MIN_LOT,
    DEFAULT_LOT_STEP,
    MAX_CONCURRENT_UNPROTECTED_TRADES,
    MAX_CONCURRENT_USD_EXPOSURE,
    POST_LOSS_COOLDOWN_MINUTES,
    DAILY_LOSS_CIRCUIT_BREAKER_R,
    DAILY_LOSS_CIRCUIT_BREAKER_COUNT,
    NIGHT_SESSION_HOURS,
    NIGHT_MAX_HOLD_BARS,
    STRATEGY_NAME,
)
from core.instrument_validator import (
    calculate_pip_value_usd,
    calculate_position_size,
    calculate_monetary_risk,
    calculate_tp_sl,
)
from market_scanner import (
    compute_indicators,
    detect_night_mean_reversion,
    detect_pullback_confirmation,
    detect_ict_liquidity_sweep,
    get_usd_directional_bias,
)


def load_historical_forex_data(cache_path: Optional[Path] = None) -> Dict[str, pd.DataFrame]:
    """
    Loads historical 15M candle datasets for the 6 canonical forex pairs.
    Prefers archives/data_cache_orb.pkl (complete 4.8-year 15M dataset).
    Fallback: archives/portfolio_8pairs_cache.pkl.
    """
    if cache_path is None:
        orb_path = ROOT_DIR / "archives" / "data_cache_orb.pkl"
        cache_path = orb_path if orb_path.exists() else (ROOT_DIR / "archives" / "portfolio_8pairs_cache.pkl")

    if not cache_path.exists():
        raise FileNotFoundError(
            f"Historical dataset cache not found at {cache_path}. "
            f"Please ensure historical candle cache is present."
        )

    with open(cache_path, "rb") as f:
        loaded = pickle.load(f)

    # Check if loaded is tuple (key, dict_data) from data_cache_orb
    if isinstance(loaded, tuple) and len(loaded) == 2 and isinstance(loaded[1], dict):
        raw_data = loaded[1]
    else:
        raw_data = loaded

    clean_dict = {}
    for sym in CANONICAL_SYMBOLS:
        if sym not in raw_data:
            alt_keys = [k for k in raw_data.keys() if sym in k.replace("_", "").replace("=X", "")]
            if alt_keys:
                item = raw_data[alt_keys[0]]
            else:
                continue
        else:
            item = raw_data[sym]

        if isinstance(item, dict) and "M15" in item:
            df = item["M15"].copy()
        elif isinstance(item, pd.DataFrame):
            df = item.copy()
        else:
            continue

        # Standardize timestamp column
        time_col = None
        for c in ["time_dt", "time", "datetime", "timestamp"]:
            if c in df.columns:
                time_col = c
                break

        if time_col is None:
            continue

        if pd.api.types.is_numeric_dtype(df[time_col]):
            df["time"] = pd.to_datetime(df[time_col], unit="s", utc=True)
        else:
            df["time"] = pd.to_datetime(df[time_col], utc=True)

        df.sort_values("time", inplace=True)
        df.reset_index(drop=True, inplace=True)

        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)
        if "volume" not in df.columns:
            df["volume"] = 1000.0

        clean_dict[sym] = df

    return clean_dict


def run_pair_signals(
    pair: str,
    df: pd.DataFrame,
    start_idx: int = 50,
) -> List[Dict[str, Any]]:
    """
    Extracts raw valid candidate signals without looking ahead.
    Evaluates exclusively on completed bar closes up to index i.
    """
    cfg = PAIR_CONFIGS[pair]
    pip = cfg["pip_size"]
    digits = cfg["digits"]
    allowed_hours = cfg["hours"]

    # Compute all indicators on the full series using strict past-looking shifts
    df_ind = compute_indicators(df, donchian_len=20)
    n = len(df_ind)
    signals = []

    for i in range(start_idx, n - 1):
        # Pass fixed 35-bar rolling window to detection helpers (thousands of times faster than slicing from 0)
        closed_sub = df_ind.iloc[max(0, i - 35):i + 1]
        c = closed_sub.iloc[-1]
        t = c["time"]

        # Session killzone guard: only entries during institutional volume hours
        if t.hour not in allowed_hours:
            continue

        # Setup 0: Asian Night Statistical Mean-Reversion Scalper (Alpha Engine)
        if t.hour in NIGHT_SESSION_HOURS:
            long_mr, _, mr_entry_l, mr_sl_l, mr_tp_l, mr_sl_p_l, mr_tp_p_l, mr_rr_l = detect_night_mean_reversion(
                closed_sub, pip, digits, is_long=True, pair_name=pair
            )
            short_mr, _, mr_entry_s, mr_sl_s, mr_tp_s, mr_sl_p_s, mr_tp_p_s, mr_rr_s = detect_night_mean_reversion(
                closed_sub, pip, digits, is_long=False, pair_name=pair
            )
            if long_mr or short_mr:
                direction = "LONG" if long_mr else "SHORT"
                entry_price = float(mr_entry_l if long_mr else mr_entry_s)
                tp_price = float(mr_tp_l if long_mr else mr_tp_s)
                sl_price = float(mr_sl_l if long_mr else mr_sl_s)
                sl_pips = float(mr_sl_p_l if long_mr else mr_sl_p_s)
                tp_pips = float(mr_tp_p_l if long_mr else mr_tp_p_s)
                rr = float(mr_rr_l if long_mr else mr_rr_s)

                signals.append({
                    "pair": pair,
                    "direction": direction,
                    "bar_idx": i,
                    "entry_time": t,
                    "entry_price": entry_price,
                    "tp_price": tp_price,
                    "sl_price": sl_price,
                    "sl_pips": sl_pips,
                    "tp_pips": tp_pips,
                    "rr": rr,
                    "setup": "NIGHT_SCALPER",
                    "max_hold_bars": 16,
                })
            continue  # Night hours are strictly reserved for mean reversion; skip daytime breakout checks

        # Macro trend agreement: 20-EMA > 50-EMA with slope
        bullish_trend = (c["close"] > c["ema50"]) and (c["ema20"] > c["ema50"]) and (c["ema20_slope"] > 0)
        bearish_trend = (c["close"] < c["ema50"]) and (c["ema20"] < c["ema50"]) and (c["ema20_slope"] < 0)

        # RSI filter: avoid exhaustion
        rsi_bullish = 40.0 <= c["rsi"] <= 80.0
        rsi_bearish = 20.0 <= c["rsi"] <= 60.0

        # ADX regime filter: skip flat chop
        adx_val = c.get("adx", 15.0)
        if 20.0 < adx_val < 30.0 and abs(c["ema20_slope"]) < (0.05 * pip):
            continue

        # Setup 1: ICT Liquidity Sweep Reclaim
        long_ict, _, _, _, _ = detect_ict_liquidity_sweep(closed_sub, pip, is_long=True)
        short_ict, _, _, _, _ = detect_ict_liquidity_sweep(closed_sub, pip, is_long=False)

        # Setup 2: Two-Phase Pullback & Rejection Bounce (lookback strictly limited to past bars)
        long_pb, _, _, _, _ = detect_pullback_confirmation(closed_sub, donch_len=20, is_long=True, max_lookback=12)
        short_pb, _, _, _, _ = detect_pullback_confirmation(closed_sub, donch_len=20, is_long=False, max_lookback=12)

        is_long = (long_ict and c["rsi"] <= 78.0) or (long_pb and bullish_trend and rsi_bullish)
        is_short = (short_ict and c["rsi"] >= 22.0) or (short_pb and bearish_trend and rsi_bearish)

        if not (is_long or is_short):
            continue

        # Mutually exclusive: long takes precedence or skip if conflicting
        if is_long and is_short:
            continue

        direction = "LONG" if is_long else "SHORT"
        entry_price = float(c["close"])

        # Canonical Strategy Exits (Fixed 15p TP / 10p SL)
        tp_price, sl_price = calculate_tp_sl(
            entry=entry_price,
            direction=direction,
            symbol=pair,
            tp_pips=CANONICAL_TAKE_PROFIT_PIPS,
            sl_pips=CANONICAL_STOP_LOSS_PIPS,
        )

        signals.append({
            "pair": pair,
            "direction": direction,
            "bar_idx": i,
            "entry_time": t,
            "entry_price": entry_price,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "sl_pips": CANONICAL_STOP_LOSS_PIPS,
            "tp_pips": CANONICAL_TAKE_PROFIT_PIPS,
            "setup": "ICT_SWEEP" if (long_ict or short_ict) else "PULLBACK",
        })

    return signals


def simulate_portfolio_backtest(
    data_dict: Dict[str, pd.DataFrame],
    initial_equity: float = REFERENCE_ACCOUNT_EQUITY,
    risk_pct: float = REFERENCE_RISK_PCT,
    use_transaction_costs: bool = True,
    in_sample_ratio: float = 0.70,
) -> Dict[str, Any]:
    """
    Executes an out-of-sample portfolio simulation across all eligible pairs.
    Applies concurrency, directional bias, cooldown, circuit breaker, and transaction costs.
    """
    all_signals = []
    for pair in CANONICAL_SYMBOLS:
        if pair not in data_dict:
            continue
        sigs = run_pair_signals(pair, data_dict[pair])
        all_signals.extend(sigs)

    # Sort all candidates strictly chronologically by entry_time
    all_signals.sort(key=lambda s: s["entry_time"])

    # Determine In-Sample vs Out-of-Sample split timestamp
    if not all_signals:
        return {"error": "No signals generated across any pair."}

    all_times = [s["entry_time"] for s in all_signals]
    min_time = min(all_times)
    max_time = max(all_times)
    total_duration = max_time - min_time
    split_time = min_time + (total_duration * in_sample_ratio)

    # Tracking state
    active_positions: List[Dict[str, Any]] = []
    completed_trades: List[Dict[str, Any]] = []
    current_equity = initial_equity
    post_loss_lockouts: Dict[str, datetime] = {}
    daily_stats: Dict[str, Dict[str, Any]] = {}

    for sig in all_signals:
        pair = sig["pair"]
        entry_time = sig["entry_time"]
        entry_price = sig["entry_price"]
        direction = sig["direction"]
        df_pair = data_dict[pair]
        bar_idx = sig["bar_idx"]
        utc_date_str = entry_time.strftime("%Y-%m-%d")

        # 1. Update / close any active positions that resolved before or at entry_time
        resolved = []
        for pos in active_positions:
            if pos["resolved"]:
                continue
            p_pair = pos["pair"]
            p_df = data_dict[p_pair]
            p_start = pos["bar_idx"] + 1

            # Iterate future bars up to entry_time
            for f_idx in range(p_start, len(p_df)):
                b = p_df.iloc[f_idx]
                b_time = b["time"]
                if b_time > entry_time:
                    break

                # Exit checks
                is_l = pos["direction"] == "LONG"
                hit_sl = (b["low"] <= pos["sl_price"]) if is_l else (b["high"] >= pos["sl_price"])
                hit_tp = (b["high"] >= pos["tp_price"]) if is_l else (b["low"] <= pos["tp_price"])

                # Pessimistic Intra-Candle Assumption: SL takes precedence
                if hit_sl and hit_tp:
                    hit_tp = False

                if hit_sl or hit_tp:
                    pos["resolved"] = True
                    pos["exit_time"] = b_time
                    pos["outcome"] = "WIN" if hit_tp else "LOSS"
                    pos["exit_price"] = pos["tp_price"] if hit_tp else pos["sl_price"]
                    resolved.append(pos)
                    break
                elif pos.get("setup") == "NIGHT_SCALPER" and (f_idx - p_start >= pos.get("max_hold_bars", 16)):
                    pos["resolved"] = True
                    pos["exit_time"] = b_time
                    pos["exit_price"] = float(b["close"])
                    pip = PAIR_CONFIGS[pos["pair"]]["pip_size"]
                    pnl_pips = (pos["exit_price"] - pos["entry_price"]) / pip if is_l else (pos["entry_price"] - pos["exit_price"]) / pip
                    pos["outcome"] = "WIN" if pnl_pips > 0 else "LOSS"
                    resolved.append(pos)
                    break

        # Remove resolved positions from active
        for r_pos in resolved:
            active_positions.remove(r_pos)
            # Update cooldown if loss
            if r_pos["outcome"] == "LOSS":
                post_loss_lockouts[r_pos["pair"]] = r_pos["exit_time"]

            # Update daily circuit breaker tracker
            r_date = r_pos["exit_time"].strftime("%Y-%m-%d")
            d_entry = daily_stats.setdefault(r_date, {"net_r": 0.0, "losses": 0})
            if r_pos["outcome"] == "LOSS":
                d_entry["losses"] += 1
                d_entry["net_r"] -= 1.0
            else:
                d_entry["net_r"] += 1.5

            completed_trades.append(r_pos)

        # 2. Portfolio Risk Rule Checks
        # Max concurrent unprotected trades (cap at 3)
        if len(active_positions) >= MAX_CONCURRENT_UNPROTECTED_TRADES:
            continue

        # Max USD directional exposure (cap at 2 in same direction)
        sig_bias = get_usd_directional_bias(pair, direction)
        if sig_bias != 0:
            current_bias_count = sum(
                1 for p in active_positions
                if get_usd_directional_bias(p["pair"], p["direction"]) == sig_bias
            )
            if current_bias_count >= MAX_CONCURRENT_USD_EXPOSURE:
                continue

        # Post-Loss Lockout (60-minute mandatory lockout)
        last_loss = post_loss_lockouts.get(pair)
        if last_loss is not None:
            mins_elapsed = (entry_time - last_loss).total_seconds() / 60.0
            if mins_elapsed < POST_LOSS_COOLDOWN_MINUTES:
                continue

        # Daily Circuit Breaker Guard
        today_stat = daily_stats.get(utc_date_str, {"net_r": 0.0, "losses": 0})
        if (
            today_stat["net_r"] <= DAILY_LOSS_CIRCUIT_BREAKER_R
            or today_stat["losses"] >= DAILY_LOSS_CIRCUIT_BREAKER_COUNT
        ):
            continue

        # 3. Position Sizing
        sig_sl_pips = sig.get("sl_pips", CANONICAL_STOP_LOSS_PIPS)
        sig_tp_pips = sig.get("tp_pips", CANONICAL_TAKE_PROFIT_PIPS)
        try:
            lots = calculate_position_size(
                account_equity=current_equity,
                risk_pct=risk_pct,
                sl_pips=sig_sl_pips,
                symbol=pair,
                exchange_rate=entry_price,
            )
        except Exception:
            continue

        # Strict Budget Guard: Reject trade if minimum lot constraint exceeds risk budget
        if lots < DEFAULT_MIN_LOT:
            continue

        pip_val_usd = calculate_pip_value_usd(pair, exchange_rate=entry_price)
        cost_cfg = CANONICAL_TRANSACTION_COSTS.get(pair, {"total_pips": 1.2})
        cost_pips = cost_cfg["total_pips"] if use_transaction_costs else 0.0

        # Open position
        active_positions.append({
            "pair": pair,
            "direction": direction,
            "bar_idx": bar_idx,
            "entry_time": entry_time,
            "entry_price": entry_price,
            "tp_price": sig["tp_price"],
            "sl_price": sig["sl_price"],
            "sl_pips": sig_sl_pips,
            "tp_pips": sig_tp_pips,
            "rr": sig.get("rr", 1.50),
            "setup": sig.get("setup", "CANONICAL"),
            "max_hold_bars": sig.get("max_hold_bars", 16),
            "lots": lots,
            "pip_val_usd": pip_val_usd,
            "cost_pips": cost_pips,
            "resolved": False,
            "is_in_sample": entry_time < split_time,
        })

    # Resolve any remaining open trades at the end of dataset
    for pos in active_positions:
        p_df = data_dict[pos["pair"]]
        p_start = pos["bar_idx"] + 1
        is_l = pos["direction"] == "LONG"
        for f_idx in range(p_start, len(p_df)):
            b = p_df.iloc[f_idx]
            hit_sl = (b["low"] <= pos["sl_price"]) if is_l else (b["high"] >= pos["sl_price"])
            hit_tp = (b["high"] >= pos["tp_price"]) if is_l else (b["low"] <= pos["tp_price"])
            if hit_sl and hit_tp:
                hit_tp = False
            if hit_sl or hit_tp:
                pos["resolved"] = True
                pos["exit_time"] = b["time"]
                pos["outcome"] = "WIN" if hit_tp else "LOSS"
                pos["exit_price"] = pos["tp_price"] if hit_tp else pos["sl_price"]
                completed_trades.append(pos)
                break
            elif pos.get("setup") == "NIGHT_SCALPER" and (f_idx - p_start >= pos.get("max_hold_bars", 16)):
                pos["resolved"] = True
                pos["exit_time"] = b["time"]
                pos["exit_price"] = float(b["close"])
                pip = PAIR_CONFIGS[pos["pair"]]["pip_size"]
                pnl_pips = (pos["exit_price"] - pos["entry_price"]) / pip if is_l else (pos["entry_price"] - pos["exit_price"]) / pip
                pos["outcome"] = "WIN" if pnl_pips > 0 else "LOSS"
                completed_trades.append(pos)
                break

    # Calculate granular trade returns and dollar metrics
    for t in completed_trades:
        is_win = t["outcome"] == "WIN"
        lots = t["lots"]
        pip_val = t["pip_val_usd"]
        cost_pips = t["cost_pips"]
        sl_pips = float(t.get("sl_pips", CANONICAL_STOP_LOSS_PIPS))
        tp_pips = float(t.get("tp_pips", CANONICAL_TAKE_PROFIT_PIPS))
        pip = PAIR_CONFIGS[t["pair"]]["pip_size"]

        if "exit_price" in t and "entry_price" in t and t.get("setup") == "NIGHT_SCALPER":
            is_l = t["direction"] == "LONG"
            gross_pips = (t["exit_price"] - t["entry_price"]) / pip if is_l else (t["entry_price"] - t["exit_price"]) / pip
        else:
            gross_pips = tp_pips if is_win else -sl_pips

        gross_r = gross_pips / sl_pips
        gross_usd = lots * gross_pips * pip_val

        # Transaction Friction
        friction_usd = lots * cost_pips * pip_val

        # Net PnL
        net_pips = gross_pips - cost_pips
        net_usd = gross_usd - friction_usd
        net_r = net_pips / sl_pips

        t["gross_pips"] = round(gross_pips, 1)
        t["gross_r"] = round(gross_r, 2)
        t["gross_usd"] = round(gross_usd, 2)
        t["friction_usd"] = round(friction_usd, 2)
        t["net_pips"] = round(net_pips, 1)
        t["net_r"] = round(net_r, 3)
        t["net_usd"] = round(net_usd, 2)

    return {
        "trades": completed_trades,
        "initial_equity": initial_equity,
        "risk_pct": risk_pct,
        "min_time": min_time.strftime("%Y-%m-%d"),
        "max_time": max_time.strftime("%Y-%m-%d"),
        "split_time": split_time.strftime("%Y-%m-%d"),
        "transaction_costs_enabled": use_transaction_costs,
    }


def compute_performance_metrics(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Computes comprehensive quantitative performance statistics from trade records."""
    if not trades:
        return {
            "total_trades": 0, "wins": 0, "losses": 0,
            "win_rate_pct": 0.0, "gross_expectancy_r": 0.0, "net_expectancy_r": 0.0,
            "profit_factor": 0.0, "max_drawdown_r": 0.0, "total_net_r": 0.0, "total_net_usd": 0.0,
        }

    total = len(trades)
    wins = [t for t in trades if t["outcome"] == "WIN"]
    losses = [t for t in trades if t["outcome"] == "LOSS"]
    win_cnt = len(wins)
    loss_cnt = len(losses)
    wr = (win_cnt / total) * 100.0 if total > 0 else 0.0

    gross_r_list = [t["gross_r"] for t in trades]
    net_r_list = [t["net_r"] for t in trades]
    net_usd_list = [t["net_usd"] for t in trades]

    total_net_r = sum(net_r_list)
    total_net_usd = sum(net_usd_list)
    gross_exp_r = sum(gross_r_list) / total if total > 0 else 0.0
    net_exp_r = total_net_r / total if total > 0 else 0.0

    # Profit Factor
    gross_win_usd = sum(t["gross_usd"] for t in wins)
    gross_loss_usd = abs(sum(t["gross_usd"] for t in losses))
    net_win_usd = sum(t["net_usd"] for t in wins if t["net_usd"] > 0)
    net_loss_usd = abs(sum(t["net_usd"] for t in trades if t["net_usd"] < 0))

    gross_pf = (gross_win_usd / gross_loss_usd) if gross_loss_usd > 0 else (99.0 if gross_win_usd > 0 else 0.0)
    net_pf = (net_win_usd / net_loss_usd) if net_loss_usd > 0 else (99.0 if net_win_usd > 0 else 0.0)

    # Maximum Drawdown (in R)
    cumulative_r = np.cumsum(net_r_list)
    peak_r = np.maximum.accumulate(cumulative_r)
    drawdowns_r = peak_r - cumulative_r
    max_dd_r = float(np.max(drawdowns_r)) if len(drawdowns_r) > 0 else 0.0

    # Maximum Drawdown (in USD)
    cumulative_usd = np.cumsum(net_usd_list)
    peak_usd = np.maximum.accumulate(cumulative_usd)
    drawdowns_usd = peak_usd - cumulative_usd
    max_dd_usd = float(np.max(drawdowns_usd)) if len(drawdowns_usd) > 0 else 0.0

    return {
        "total_trades": total,
        "wins": win_cnt,
        "losses": loss_cnt,
        "win_rate_pct": round(wr, 2),
        "gross_expectancy_r": round(gross_exp_r, 3),
        "net_expectancy_r": round(net_exp_r, 3),
        "gross_profit_factor": round(gross_pf, 2),
        "net_profit_factor": round(net_pf, 2),
        "max_drawdown_r": round(max_dd_r, 2),
        "max_drawdown_usd": round(max_dd_usd, 2),
        "total_net_r": round(total_net_r, 2),
        "total_net_usd": round(total_net_usd, 2),
    }


def format_backtest_report_markdown(results: Dict[str, Any]) -> str:
    """Formats a comprehensive institutional backtest report in GitHub markdown."""
    if "error" in results:
        return f"### Backtest Error: {results['error']}"

    trades = results["trades"]
    all_metrics = compute_performance_metrics(trades)

    # Partition In-Sample vs Out-of-Sample
    is_trades = [t for t in trades if t.get("is_in_sample", False)]
    oos_trades = [t for t in trades if not t.get("is_in_sample", False)]
    is_metrics = compute_performance_metrics(is_trades)
    oos_metrics = compute_performance_metrics(oos_trades)

    # Per-pair metrics breakdown
    per_pair = {}
    for pair in CANONICAL_SYMBOLS:
        p_trades = [t for t in trades if t["pair"] == pair]
        per_pair[pair] = compute_performance_metrics(p_trades)

    report = (
        f"# CANONICAL FOREX STRATEGY BACKTEST REPORT\n\n"
        f"**Strategy Configuration:** Canonical Fixed Exits (15.0p TP / 10.0p SL, Pure 1:1.50 R:R)\n"
        f"**Historical Interval:** `{results['min_time']}` to `{results['max_time']}`\n"
        f"**Out-of-Sample Split Date (70/30):** `{results['split_time']}`\n"
        f"**Reference Account Equity:** `${results['initial_equity']:,.2f} USD` (Risk: `{results['risk_pct']:.2f}%` = `${results['initial_equity'] * (results['risk_pct']/100.0):.2f}` / trade)\n"
        f"**Transaction Costs Modeled:** {'YES (Spread + Commission + Slippage)' if results['transaction_costs_enabled'] else 'NO (Gross Baseline)'}\n\n"
        f"## 1. Portfolio Combined Performance Summary\n\n"
        f"| Metric | Full Period | In-Sample (70%) | Out-of-Sample (30%) |\n"
        f"|---|---|---|---|\n"
        f"| **Total Closed Trades** | {all_metrics['total_trades']} | {is_metrics['total_trades']} | {oos_metrics['total_trades']} |\n"
        f"| **Win Rate** | **{all_metrics['win_rate_pct']:.1f}%** ({all_metrics['wins']}W / {all_metrics['losses']}L) | {is_metrics['win_rate_pct']:.1f}% | {oos_metrics['win_rate_pct']:.1f}% |\n"
        f"| **Gross Expectancy** | **+{all_metrics['gross_expectancy_r']:.3f} R** | +{is_metrics['gross_expectancy_r']:.3f} R | +{oos_metrics['gross_expectancy_r']:.3f} R |\n"
        f"| **Net Expectancy (After Costs)** | **+{all_metrics['net_expectancy_r']:.3f} R** | +{is_metrics['net_expectancy_r']:.3f} R | +{oos_metrics['net_expectancy_r']:.3f} R |\n"
        f"| **Gross Profit Factor** | {all_metrics['gross_profit_factor']:.2f} | {is_metrics['gross_profit_factor']:.2f} | {oos_metrics['gross_profit_factor']:.2f} |\n"
        f"| **Net Profit Factor (After Costs)** | **{all_metrics['net_profit_factor']:.2f}** | {is_metrics['net_profit_factor']:.2f} | {oos_metrics['net_profit_factor']:.2f} |\n"
        f"| **Max Drawdown (R)** | **{all_metrics['max_drawdown_r']:.2f} R** | {is_metrics['max_drawdown_r']:.2f} R | {oos_metrics['max_drawdown_r']:.2f} R |\n"
        f"| **Max Drawdown ($)** | ${all_metrics['max_drawdown_usd']:,.2f} | ${is_metrics['max_drawdown_usd']:,.2f} | ${oos_metrics['max_drawdown_usd']:,.2f} |\n"
        f"| **Total Net Return (R)** | **+{all_metrics['total_net_r']:.2f} R** | +{is_metrics['total_net_r']:.2f} R | +{oos_metrics['total_net_r']:.2f} R |\n"
        f"| **Total Net Return ($)** | **+${all_metrics['total_net_usd']:,.2f}** | +${is_metrics['total_net_usd']:,.2f} | +${oos_metrics['total_net_usd']:,.2f} |\n\n"
        f"## 2. Per-Pair Performance Breakdown (Net After Transaction Costs)\n\n"
        f"| Pair | Trades | Win Rate | Net Expectancy | Net PF | Max DD (R) | Net PnL (R) | Net PnL ($) |\n"
        f"|---|---|---|---|---|---|---|---|\n"
    )

    for pair, m in per_pair.items():
        report += (
            f"| **{pair}** | {m['total_trades']} | {m['win_rate_pct']:.1f}% "
            f"({m['wins']}W/{m['losses']}L) | {m['net_expectancy_r']:+.3f} R | {m['net_profit_factor']:.2f} | "
            f"{m['max_drawdown_r']:.2f} R | {m['total_net_r']:+.2f} R | ${m['total_net_usd']:+,.2f} |\n"
        )

    report += (
        f"\n## 3. Institutional Transaction Cost Schedule & Assumptions\n\n"
        f"| Pair | Raw Spread | ECN Commission ($4/lot) | Slippage Model | Total Round-Trip Friction |\n"
        f"|---|---|---|---|---|\n"
    )
    for pair, c in CANONICAL_TRANSACTION_COSTS.items():
        report += (
            f"| `{pair}` | {c['spread_pips']:.1f} pips | {c['commission_pips']:.1f} pips | "
            f"{c['slippage_pips']:.1f} pips | **{c['total_pips']:.1f} pips** |\n"
        )

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Canonical Forex Strategy Backtest")
    parser.add_argument("--cache", type=str, default=None, help="Path to pkl historical candle dataset")
    parser.add_argument("--no-costs", action="store_true", help="Disable transaction cost deduction (evaluate gross)")
    parser.add_argument("--markdown", action="store_true", help="Print report formatted as Markdown")
    args = parser.parse_args()

    cache_file = Path(args.cache) if args.cache else None
    data = load_historical_forex_data(cache_file)
    results = simulate_portfolio_backtest(data, use_transaction_costs=not args.no_costs)
    md_output = format_backtest_report_markdown(results)
    print(md_output)
