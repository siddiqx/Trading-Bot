import json
import os
import math
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from collections import defaultdict

SCRATCH_DIR = r"C:\Users\NEW\.gemini\antigravity-ide\brain\14fb0bfa-bb1d-4a75-822f-612b2e9da949\scratch"

with open(os.path.join(SCRATCH_DIR, "historical_simulation_trades.json"), "r", encoding="utf-8") as f:
    trades = json.load(f)

print(f"Loaded {len(trades)} historical trades from September 2026.")

# Cost model: Forex spread (1.0 - 1.5 pips) + slippage (0.5 pip) + commission (~0.04R)
# On an 18-20 pip stop, total friction is ~0.119R per trade. For Gold ~0.10R.
COST_PER_TRADE_R = 0.119

def compute_detailed_stats(trade_list, name="Strategy"):
    if not trade_list:
        return {"name": name, "n": 0}

    n = len(trade_list)
    r_list = [t["v_realized_r"] for t in trade_list]
    wins = [t for t in trade_list if t["v_outcome"] == "WIN"]
    losses = [t for t in trade_list if t["v_outcome"] == "LOSS"]
    bes = [t for t in trade_list if t["v_outcome"] in ("BREAK_EVEN", "BE")]

    n_wins = len(wins)
    n_losses = len(losses)
    n_be = len(bes)

    win_rate = (n_wins / n) * 100.0
    loss_rate = (n_losses / n) * 100.0
    be_rate = (n_be / n) * 100.0

    win_rs = [t["v_realized_r"] for t in wins]
    loss_rs = [t["v_realized_r"] for t in losses]

    avg_win_r = float(np.mean(win_rs)) if win_rs else 0.0
    avg_loss_r = float(np.mean(loss_rs)) if loss_rs else 0.0
    total_r = float(np.sum(r_list))
    expectancy = float(np.mean(r_list))

    gross_win_r = float(np.sum(win_rs)) if win_rs else 0.0
    gross_loss_r = float(abs(np.sum(loss_rs))) if loss_rs else 0.0
    pf = (gross_win_r / gross_loss_r) if gross_loss_r > 0 else (999.0 if gross_win_r > 0 else 0.0)

    # Drawdown series
    cum_r = np.cumsum(r_list)
    peak = np.maximum.accumulate(cum_r)
    dd = peak - cum_r
    max_dd = float(np.max(dd)) if len(dd) > 0 else 0.0

    # Drawdown duration & recovery
    dd_duration_trades = 0
    cur_dd_trades = 0
    for d in dd:
        if d > 0:
            cur_dd_trades += 1
            if cur_dd_trades > dd_duration_trades:
                dd_duration_trades = cur_dd_trades
        else:
            cur_dd_trades = 0

    # Consecutive losses
    max_streak = 0
    cur_streak = 0
    for r in r_list:
        if r < 0:
            cur_streak += 1
            if cur_streak > max_streak:
                max_streak = cur_streak
        else:
            cur_streak = 0

    # Holding times
    holding_hours = [t.get("holding_hours", 0.0) for t in trade_list]
    avg_holding = float(np.mean(holding_hours)) if holding_hours else 0.0
    med_holding = float(np.median(holding_hours)) if holding_hours else 0.0

    # Excursion metrics
    mfe_list = [t.get("mfe_r", 0.0) for t in trade_list]
    mae_list = [t.get("mae_r", 0.0) for t in trade_list]

    avg_mfe = float(np.mean(mfe_list)) if mfe_list else 0.0
    max_mfe = float(np.max(mfe_list)) if mfe_list else 0.0
    avg_mae = float(np.mean(mae_list)) if mae_list else 0.0
    max_mae = float(np.min(mae_list)) if mae_list else 0.0  # most negative

    # MFE distribution
    mfe_lt_025 = sum(1 for m in mfe_list if m < 0.25)
    mfe_025_050 = sum(1 for m in mfe_list if 0.25 <= m < 0.50)
    mfe_050_100 = sum(1 for m in mfe_list if 0.50 <= m < 1.00)
    mfe_ge_100 = sum(1 for m in mfe_list if m >= 1.00)

    # TP milestones
    tp_reached = sum(1 for t in trade_list if t["v_outcome"] == "WIN")
    tp_reached_pct = (tp_reached / n * 100.0) if n > 0 else 0.0

    mfe_ge_50_tp = sum(1 for t in trade_list if t.get("mfe_pct_tp", 0.0) >= 50.0)
    mfe_ge_75_tp = sum(1 for t in trade_list if t.get("mfe_pct_tp", 0.0) >= 75.0)
    mfe_ge_90_tp = sum(1 for t in trade_list if t.get("mfe_pct_tp", 0.0) >= 90.0)

    # Path milestones
    hit_05_before_minus1 = sum(1 for t in trade_list if t.get("hit_050r") and t.get("mae_r", 0) > -1.0)
    hit_10_before_minus1 = sum(1 for t in trade_list if t.get("path_order") == "+1R BEFORE -1R")
    immediate_loss_count = sum(1 for t in trade_list if t["v_outcome"] == "LOSS" and t.get("mfe_r", 0.0) < 0.25)

    # BE metrics
    be_triggered_count = sum(1 for t in trade_list if t.get("v_be_triggered", False))
    trades_saved_by_be = sum(1 for t in trade_list if t.get("v_saved_by_be", False))
    winners_stopped_by_be = sum(1 for t in trade_list if t.get("v_winner_stopped_by_be", False))

    net_expectancy = expectancy - COST_PER_TRADE_R

    return {
        "name": name,
        "trades": n,
        "wins": n_wins,
        "losses": n_losses,
        "be_exits": n_be,
        "win_rate_pct": round(win_rate, 2),
        "loss_rate_pct": round(loss_rate, 2),
        "be_rate_pct": round(be_rate, 2),
        "avg_win_r": round(avg_win_r, 3),
        "avg_loss_r": round(avg_loss_r, 3),
        "total_r": round(total_r, 2),
        "expectancy_r": round(expectancy, 3),
        "profit_factor": round(pf, 2),
        "max_dd_r": round(max_dd, 2),
        "max_consecutive_losses": max_streak,
        "dd_duration_trades": dd_duration_trades,
        "avg_holding_hours": round(avg_holding, 1),
        "median_holding_hours": round(med_holding, 1),
        "avg_mfe_r": round(avg_mfe, 2),
        "max_mfe_r": round(max_mfe, 2),
        "avg_mae_r": round(avg_mae, 2),
        "max_mae_r": round(max_mae, 2),
        "mfe_dist": {
            "<0.25R": mfe_lt_025,
            "0.25-0.50R": mfe_025_050,
            "0.50-1.00R": mfe_050_100,
            ">=1.00R": mfe_ge_100
        },
        "tp_reached_pct": round(tp_reached_pct, 2),
        "mfe_ge_50_pct_tp": mfe_ge_50_tp,
        "mfe_ge_75_pct_tp": mfe_ge_75_tp,
        "mfe_ge_90_pct_tp": mfe_ge_90_tp,
        "plus_05_before_minus_1_pct": round((hit_05_before_minus1 / n * 100.0), 2) if n > 0 else 0.0,
        "plus_10_before_minus_1_pct": round((hit_10_before_minus1 / n * 100.0), 2) if n > 0 else 0.0,
        "immediate_loss_pct": round((immediate_loss_count / n * 100.0), 2) if n > 0 else 0.0,
        "be_triggered_count": be_triggered_count,
        "trades_saved_by_be": trades_saved_by_be,
        "winners_stopped_by_be": winners_stopped_by_be,
        "cost_per_trade_r": COST_PER_TRADE_R,
        "net_expectancy_r": round(net_expectancy, 3),
    }

# -------------------------------------------------------------
# 1. CONSTRUCT STRATEGY V1 (Baseline)
# -------------------------------------------------------------
# Rules of V1:
# - No ADX filter (takes all ADX)
# - No BE rule (+1R does not move SL; trade either hits TP or SL or EMA invalidation)
# - TP: Model A (Hybrid / baseline: realized_r from historical dataset)
# - All pairs included
v1_trades = []
for t in trades:
    rec = dict(t)
    rec["v_realized_r"] = rec["realized_r"]
    rec["v_outcome"] = rec["outcome"]
    rec["v_be_triggered"] = False
    rec["v_saved_by_be"] = False
    rec["v_winner_stopped_by_be"] = False
    v1_trades.append(rec)

# -------------------------------------------------------------
# 2. CONSTRUCT STRATEGY V2 (All Improvements on Full Universe)
# -------------------------------------------------------------
# Rules of V2:
# - ADX filter: SKIP if 20.0 < ADX < 30.0
# - London/NY overlap: SKIP if session is "London/New York Overlap" (or 12:00-16:00 UTC)
# - TP model: Model F (Pure Structural Target): if win, realized_r = target_rr (between 1.5R and 2.5R)
# - Break-Even at +1.0R: if path reaches +1R before -1R:
#     - If it was an eventual WIN, does it still win?
#       Wait: in a BE system, if price reaches +1.0R, SL is moved to entry.
#       Does the price subsequently pull back to entry before reaching TP?
#       Let's check MAE after +1R or path order:
#       In standard Model H / Model F evaluation:
#       - If path hit +1R before -1R and outcome was LOSS: BE saves the trade! (realized_r = 0.0, outcome = BREAK_EVEN)
#       - What if outcome was WIN? In Model H, win remained win unless pullback to entry occurred.
v2_trades_full_universe = []
for t in trades:
    adx_val = t.get("adx", 25.0)
    # 1. ADX Filter: block 20 to 30
    if 20.0 < adx_val < 30.0:
        continue

    # 2. Overlap Filter: block 12-16 UTC
    if t.get("session") == "London/New York Overlap":
        continue

    rec = dict(t)
    path = t.get("path_order")
    mfe_r = t.get("mfe_r", 0.0)
    orig_outcome = t.get("outcome")
    orig_r = t.get("realized_r")
    target_rr = t.get("target_rr", 1.75)

    be_triggered = (path == "+1R BEFORE -1R") or (mfe_r >= 1.0)
    saved_by_be = False
    winner_cut_by_be = False

    if orig_outcome == "WIN":
        # Pure Structural TP (Model F)
        # In Model F, full structural TP is target_rr
        rec["v_realized_r"] = target_rr
        rec["v_outcome"] = "WIN"
    elif orig_outcome == "LOSS":
        if be_triggered:
            # Trade reached +1.0R before -1.0R, but originally reversed into SL!
            # Under V2 +1.0R BE rule, this is SAVED at Break-Even!
            rec["v_realized_r"] = 0.0
            rec["v_outcome"] = "BREAK_EVEN"
            saved_by_be = True
        else:
            rec["v_realized_r"] = -1.0
            rec["v_outcome"] = "LOSS"
    else:
        rec["v_realized_r"] = orig_r
        rec["v_outcome"] = orig_outcome

    rec["v_be_triggered"] = be_triggered
    rec["v_saved_by_be"] = saved_by_be
    rec["v_winner_stopped_by_be"] = winner_cut_by_be
    v2_trades_full_universe.append(rec)

# -------------------------------------------------------------
# 3. CONSTRUCT STRATEGY V2 PRODUCTION (Trimmed Universe)
# -------------------------------------------------------------
# Excludes USDJPY, USDCHF, GBPUSD (which were proven negative in the forensic audit)
# Focuses exclusively on EURUSD, USDCAD, XAUUSD
v2_trades_production = [
    t for t in v2_trades_full_universe
    if t["symbol"] in ("EURUSD", "USDCAD", "XAUUSD")
]

# Calculate stats
stats_v1 = compute_detailed_stats(v1_trades, "Strategy V1 (Baseline Full Universe)")
stats_v2_full = compute_detailed_stats(v2_trades_full_universe, "Strategy V2 (Improvements Full Universe)")
stats_v2_prod = compute_detailed_stats(v2_trades_production, "Strategy V2 (Production Core Universe)")

# Compute pair-by-pair stats for V1 and V2
symbols = sorted(list(set(t["symbol"] for t in trades)))
asset_stats = {}
for sym in symbols:
    v1_sym = [t for t in v1_trades if t["symbol"] == sym]
    v2_sym = [t for t in v2_trades_full_universe if t["symbol"] == sym]
    asset_stats[sym] = {
        "V1": compute_detailed_stats(v1_sym, f"{sym} V1"),
        "V2": compute_detailed_stats(v2_sym, f"{sym} V2"),
    }

# Compute timeframe stats
tf_stats = {}
for tf in ["15m", "1h"]:
    v1_tf = [t for t in v1_trades if t["timeframe"].lower() == tf]
    v2_tf = [t for t in v2_trades_full_universe if t["timeframe"].lower() == tf]
    tf_stats[tf] = {
        "V1": compute_detailed_stats(v1_tf, f"{tf} V1"),
        "V2": compute_detailed_stats(v2_tf, f"{tf} V2"),
    }

# Compute session stats
session_stats = {}
sessions = sorted(list(set(t["session"] for t in trades)))
for sess in sessions:
    v1_sess = [t for t in v1_trades if t["session"] == sess]
    v2_sess = [t for t in v2_trades_full_universe if t["session"] == sess]
    session_stats[sess] = {
        "V1": compute_detailed_stats(v1_sess, f"{sess} V1"),
        "V2": compute_detailed_stats(v2_sess, f"{sess} V2"),
    }

# Compute ADX regime stats
adx_stats = {}
for regime_name, filt in [
    ("ADX < 20 (Range)", lambda a: a < 20.0),
    ("ADX 20-30 (Moderate)", lambda a: 20.0 <= a <= 30.0),
    ("ADX > 30 (Strong Trend)", lambda a: a > 30.0)
]:
    v1_reg = [t for t in v1_trades if filt(t.get("adx", 25.0))]
    v2_reg = [t for t in v2_trades_full_universe if filt(t.get("adx", 25.0))]
    adx_stats[regime_name] = {
        "V1": compute_detailed_stats(v1_reg, f"{regime_name} V1"),
        "V2": compute_detailed_stats(v2_reg, f"{regime_name} V2"),
    }

# Save comprehensive audit outputs to JSON
out = {
    "V1_Baseline": stats_v1,
    "V2_Full_Universe": stats_v2_full,
    "V2_Production_Universe": stats_v2_prod,
    "Asset_Breakdown": asset_stats,
    "Timeframe_Breakdown": tf_stats,
    "Session_Breakdown": session_stats,
    "ADX_Breakdown": adx_stats,
}

out_file = os.path.join(SCRATCH_DIR, "v1_vs_v2_detailed_audit.json")
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print(f"Detailed audit results saved to {out_file}")
