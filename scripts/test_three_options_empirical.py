#!/usr/bin/env python3
"""Empirical Backtest: Testing 3 Expectancy Enhancement Options on v3.3.0 CCRS Engine.

Options Tested:
1. Option 1: Dynamic Target Expansion (TP = 1.75R when |D| >= 2.50σ).
2. Option 2: 4H Trend Confluence (Trade with 4H 50-EMA trend).
3. Option 3: Breakeven Profit Lock at +1.20R (Prevent reversal stop-outs).
4. All Three Combined.

Evaluates across the Clean Core 4 pairs (EURUSD, USDCAD, USDCHF, AUDUSD).
Strictly measures:
- Total Trades (Frequency Check)
- Win Rate (%)
- Decisive Win Rate (excluding BE)
- Profit Factor
- Net R Return
- Max Drawdown (R)
- Average Win / Average Loss
"""

import pickle
import math
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timezone

def run_empirical_test():
    print("=" * 105)
    print("EMPIRICAL EXPECTANCY TEST: EVALUATING 3 STRATEGY ENHANCEMENTS")
    print("=" * 105)

    print("\n[Step 1] Loading historical 1H and 15M candles from archives/data_cache_orb.pkl...")
    with open("archives/data_cache_orb.pkl", "rb") as f:
        orb_data = pickle.load(f)[1]

    pairs = ["EURUSD", "USDCAD", "USDCHF", "AUDUSD", "GBPUSD", "USDJPY"]
    core_pairs = ["EURUSD", "USDCAD", "USDCHF", "AUDUSD"]

    dfs_1h = {}
    dfs_15m = {}
    dfs_4h = {}

    for p in pairs:
        df1h = orb_data[p]["H1"].copy()
        df1h["time"] = pd.to_datetime(df1h["time"], unit="s", utc=True)
        df1h = df1h.sort_values("time").reset_index(drop=True)
        dfs_1h[p] = df1h

        df15 = orb_data[p]["M15"].copy()
        df15["time"] = pd.to_datetime(df15["time"], unit="s", utc=True)
        df15 = df15.sort_values("time").reset_index(drop=True)
        dfs_15m[p] = df15

        # Build 4H bars for trend confluence
        df_idx = df1h.set_index("time")
        df4h = df_idx.resample("4h").agg({
            "open": "first", "high": "max", "low": "min", "close": "last"
        }).dropna().reset_index()
        df4h["ema50"] = df4h["close"].ewm(span=50, adjust=False).mean()
        df4h["ema20"] = df4h["close"].ewm(span=20, adjust=False).mean()
        df4h["ema20_slope"] = df4h["ema20"] - df4h["ema20"].shift(1)
        dfs_4h[p] = df4h

    # Align 1H for 6-currency CCRS calculation
    close_1h = pd.DataFrame({p: df.set_index("time")["close"] for p, df in dfs_1h.items()}).dropna()
    lb = 120
    z_win = 200

    ret_eur = np.log(close_1h["EURUSD"] / close_1h["EURUSD"].shift(lb))
    ret_gbp = np.log(close_1h["GBPUSD"] / close_1h["GBPUSD"].shift(lb))
    ret_aud = np.log(close_1h["AUDUSD"] / close_1h["AUDUSD"].shift(lb))
    ret_jpy = -np.log(close_1h["USDJPY"] / close_1h["USDJPY"].shift(lb))
    ret_cad = -np.log(close_1h["USDCAD"] / close_1h["USDCAD"].shift(lb))
    ret_chf = -np.log(close_1h["USDCHF"] / close_1h["USDCHF"].shift(lb))
    ret_usd = -(ret_eur + ret_gbp + ret_aud + ret_jpy + ret_cad + ret_chf) / 6.0

    curr_returns = pd.DataFrame({
        "EUR": ret_eur, "GBP": ret_gbp, "AUD": ret_aud,
        "JPY": ret_jpy, "CAD": ret_cad, "CHF": ret_chf, "USD": ret_usd
    })
    z_scores = (curr_returns - curr_returns.rolling(z_win).mean()) / (curr_returns.rolling(z_win).std() + 1e-9)

    ccrs_div = pd.DataFrame(index=close_1h.index)
    ccrs_div["EURUSD"] = z_scores["EUR"] - z_scores["USD"]
    ccrs_div["AUDUSD"] = z_scores["AUD"] - z_scores["USD"]
    ccrs_div["USDCAD"] = z_scores["USD"] - z_scores["CAD"]
    ccrs_div["USDCHF"] = z_scores["USD"] - z_scores["CHF"]

    # Precalculate 15M indicators for core pairs
    ind_15m = {}
    for p in core_pairs:
        df = dfs_15m[p].copy()
        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["donch_h10"] = df["high"].shift(1).rolling(10).max()
        df["donch_l10"] = df["low"].shift(1).rolling(10).min()
        
        # 1H ATR resampled to 15m
        df1h_p = dfs_1h[p].copy()
        tr = np.maximum(df1h_p["high"] - df1h_p["low"], np.maximum(
            np.abs(df1h_p["high"] - df1h_p["close"].shift(1)),
            np.abs(df1h_p["low"] - df1h_p["close"].shift(1))
        ))
        df1h_p["atr14"] = tr.rolling(14).mean().bfill()
        atr_map = df1h_p.set_index("time")["atr14"].to_dict()
        
        # 4H trend map
        df4h_p = dfs_4h[p].copy()
        ema50_4h_map = df4h_p.set_index("time")["ema50"].to_dict()
        ema20_slope_4h_map = df4h_p.set_index("time")["ema20_slope"].to_dict()
        
        df["h1_time"] = df["time"].dt.floor("1h")
        df["h4_time"] = df["time"].dt.floor("4h")
        df["atr"] = df["h1_time"].map(atr_map).bfill()
        df["ema50_4h"] = df["h4_time"].map(ema50_4h_map).bfill()
        df["ema20_slope_4h"] = df["h4_time"].map(ema20_slope_4h_map).bfill()
        
        ind_15m[p] = df.set_index("time")

    # Simulation engine function
    def run_variant(
        opt1_dynamic_tp: bool = False,
        opt2_htf_confluence: bool = False,
        opt3_be_lock: bool = False,
        htf_mode: str = "soft",  # "soft" (slope or price) vs "strict" (price only)
    ):
        completed_trades = []
        active_trades = []
        friction_pips = {"EURUSD": 1.2, "USDCAD": 1.5, "USDCHF": 1.5, "AUDUSD": 1.3}

        # Use recent 2-year sample from the dataset for rapid precise simulation
        start_time = pd.Timestamp("2024-09-01", tz="UTC")
        end_time = pd.Timestamp("2026-09-01", tz="UTC")

        # Get common 15m timestamps
        common_times = ind_15m["EURUSD"].loc[start_time:end_time].index

        for t in common_times:
            h1_time = t.floor("1h")
            if h1_time not in ccrs_div.index:
                continue

            # Update existing active trades
            remaining_trades = []
            for tr in active_trades:
                p = tr["pair"]
                df_bar = ind_15m[p]
                if t not in df_bar.index:
                    remaining_trades.append(tr)
                    continue

                b = df_bar.loc[t]
                pip = 0.0001
                entry = tr["entry"]
                direction = tr["direction"]
                sl_pips = tr["sl_pips"]
                tp_pips = tr["tp_pips"]
                initial_sl_pips = tr["initial_sl_pips"]
                is_be = tr.get("is_be", False)

                b_high = b["high"]
                b_low = b["low"]

                # Check Option 3: Breakeven lock at +1.20R
                if opt3_be_lock and not is_be:
                    if direction == "LONG":
                        cur_mfe_pips = (b_high - entry) / pip
                    else:
                        cur_mfe_pips = (entry - b_low) / pip

                    if cur_mfe_pips >= (1.20 * initial_sl_pips):
                        tr["is_be"] = True
                        is_be = True
                        # Move SL to Breakeven + 0.5 pip
                        tr["sl_pips"] = -0.5  # Locked in 0.5 pip profit (zero loss)

                # Check SL / TP hits
                hit_sl = False
                hit_tp = False

                if direction == "LONG":
                    sl_price = entry - (tr["sl_pips"] * pip)
                    tp_price = entry + (tp_pips * pip)
                    if b_low <= sl_price:
                        hit_sl = True
                    elif b_high >= tp_price:
                        hit_tp = True
                else:
                    sl_price = entry + (tr["sl_pips"] * pip)
                    tp_price = entry - (tp_pips * pip)
                    if b_high >= sl_price:
                        hit_sl = True
                    elif b_low <= tp_price:
                        hit_tp = True

                if hit_sl:
                    if is_be:
                        # Breakeven exit
                        r_outcome = 0.0
                        pnl_pips = 0.0
                    else:
                        r_outcome = -1.0
                        pnl_pips = -initial_sl_pips - friction_pips[p]
                    completed_trades.append({
                        "pair": p, "direction": direction, "r": r_outcome,
                        "pips": pnl_pips, "outcome": "BE" if is_be else "LOSS",
                        "entry_time": tr["entry_time"], "exit_time": t
                    })
                elif hit_tp:
                    target_r = (tp_pips / initial_sl_pips)
                    net_pips = tp_pips - friction_pips[p]
                    net_r = target_r - (friction_pips[p] / initial_sl_pips)
                    completed_trades.append({
                        "pair": p, "direction": direction, "r": round(net_r, 2),
                        "pips": net_pips, "outcome": "WIN",
                        "entry_time": tr["entry_time"], "exit_time": t
                    })
                else:
                    remaining_trades.append(tr)

            active_trades = remaining_trades

            # Check new entry signals
            # Session filter: London & NY overlap (07:00 - 17:00 UTC, skip 10:00 & 14:00)
            hour = t.hour
            weekday = t.weekday()
            if weekday == 6 or (weekday == 4 and hour >= 12):
                continue
            if hour < 7 or hour >= 17 or hour in (10, 14):
                continue

            for p in core_pairs:
                # Check active slot
                if any(tr["pair"] == p for tr in active_trades):
                    continue
                if len(active_trades) >= 3:
                    continue

                div = ccrs_div.loc[h1_time, p]
                if abs(div) < 1.75:
                    continue

                is_long = div >= 1.75
                df_p = ind_15m[p]
                if t not in df_p.index:
                    continue

                curr = df_p.loc[t]

                # Option 2: 4H Trend Confluence Check
                if opt2_htf_confluence:
                    ema50_4h = curr["ema50_4h"]
                    slope20_4h = curr["ema20_slope_4h"]
                    px = curr["close"]
                    if is_long:
                        # For Long: price above 4H 50-EMA or 4H 20-EMA slope positive
                        if htf_mode == "soft":
                            if not (px >= ema50_4h or slope20_4h >= 0):
                                continue
                        else:
                            if px < ema50_4h:
                                continue
                    else:
                        # For Short: price below 4H 50-EMA or 4H 20-EMA slope negative
                        if htf_mode == "soft":
                            if not (px <= ema50_4h or slope20_4h <= 0):
                                continue
                        else:
                            if px > ema50_4h:
                                continue

                # 15M Technical Trigger: confirmed 20-EMA pullback or Donchian 10 sweep
                trigger = False
                prev_high = curr["donch_h10"]
                prev_low = curr["donch_l10"]
                c_open = curr["open"]
                c_close = curr["close"]
                c_high = curr["high"]
                c_low = curr["low"]
                ema20 = curr["ema20"]

                if is_long:
                    tested_ema = (c_low <= ema20 * 1.0004) and (c_close > c_open)
                    swept_don = (c_low < prev_low) and (c_close > prev_low)
                    trigger = tested_ema or swept_don
                else:
                    tested_ema = (c_high >= ema20 * 0.9996) and (c_close < c_open)
                    swept_don = (c_high > prev_high) and (c_close < prev_high)
                    trigger = tested_ema or swept_don

                if not trigger:
                    continue

                # Stop Loss & Take Profit sizing
                pip = 0.0001
                atr = curr["atr"]
                sl_pips = max(20.0, min(25.0, (atr / pip) * 2.0))

                # Option 1: Dynamic Target Expansion
                if opt1_dynamic_tp and abs(div) >= 2.50:
                    tp_pips = sl_pips * 1.75  # 1:1.75 RR on extreme macro flow
                else:
                    tp_pips = sl_pips * 1.50  # Canonical 1:1.50 RR

                active_trades.append({
                    "pair": p,
                    "direction": "LONG" if is_long else "SHORT",
                    "entry": c_close,
                    "initial_sl_pips": sl_pips,
                    "sl_pips": sl_pips,
                    "tp_pips": tp_pips,
                    "entry_time": t,
                    "is_be": False
                })

        # Calculate metrics
        df_res = pd.DataFrame(completed_trades)
        if df_res.empty:
            return {"trades": 0, "win_rate": 0, "pf": 0, "net_r": 0, "max_dd": 0}

        total = len(df_res)
        wins = len(df_res[df_res["outcome"] == "WIN"])
        losses = len(df_res[df_res["outcome"] == "LOSS"])
        bes = len(df_res[df_res["outcome"] == "BE"])

        wr_total = (wins / total) * 100.0
        decisive_total = wins + losses
        decisive_wr = (wins / decisive_total * 100.0) if decisive_total > 0 else 0.0

        net_r = df_res["r"].sum()
        gross_win = df_res[df_res["r"] > 0]["r"].sum()
        gross_loss = abs(df_res[df_res["r"] < 0]["r"].sum())
        pf = (gross_win / gross_loss) if gross_loss > 0 else 999.0

        # Drawdown calculation
        df_res["cum_r"] = df_res["r"].cumsum()
        roll_max = df_res["cum_r"].cummax()
        dd = roll_max - df_res["cum_r"]
        max_dd_r = dd.max()

        avg_win_r = (gross_win / wins) if wins > 0 else 0.0
        avg_loss_r = (gross_loss / losses) if losses > 0 else 1.0
        expectancy_r = (net_r / total)

        return {
            "trades": total,
            "wins": wins,
            "losses": losses,
            "be": bes,
            "win_rate": round(wr_total, 1),
            "decisive_wr": round(decisive_wr, 1),
            "avg_win_r": round(avg_win_r, 2),
            "avg_loss_r": round(avg_loss_r, 2),
            "expectancy_r": round(expectancy_r, 3),
            "profit_factor": round(pf, 2),
            "net_r": round(net_r, 2),
            "max_dd_r": round(max_dd_r, 2)
        }

    print("\n[Step 2] Executing backtests across 2 years (Sep 2024 - Sep 2026)...")
    res_base = run_variant(False, False, False)
    res_opt1 = run_variant(opt1_dynamic_tp=True, opt2_htf_confluence=False, opt3_be_lock=False)
    res_opt2_soft = run_variant(opt1_dynamic_tp=False, opt2_htf_confluence=True, opt3_be_lock=False, htf_mode="soft")
    res_opt1_plus_opt2 = run_variant(opt1_dynamic_tp=True, opt2_htf_confluence=True, opt3_be_lock=False, htf_mode="soft")
    res_opt3 = run_variant(opt1_dynamic_tp=False, opt2_htf_confluence=False, opt3_be_lock=True)
    res_combined_soft = run_variant(opt1_dynamic_tp=True, opt2_htf_confluence=True, opt3_be_lock=True, htf_mode="soft")

    summary = pd.DataFrame([
        {"Model": "0. Baseline (Current v3.3.0)", **res_base},
        {"Model": "1. + Opt 1: Target Expansion (|D|>=2.5σ)", **res_opt1},
        {"Model": "2. + Opt 2: 4H Confluence (Soft)", **res_opt2_soft},
        {"Model": "3. + Opt 1 & Opt 2 (Expansion + 4H Soft, NO Breakeven Lock)", **res_opt1_plus_opt2},
        {"Model": "4. + Opt 3: Breakeven Lock (+1.2R)", **res_opt3},
        {"Model": "5. ALL THREE COMBINED: Opt 1 + Opt 2 + Opt 3", **res_combined_soft},
    ])

    print("\n" + "=" * 115)
    print("EMPIRICAL COMPARISON RESULTS (2-YEAR WALK-FORWARD)")
    print("=" * 115)
    print(summary.to_string(index=False))
    print("=" * 115)

if __name__ == "__main__":
    run_empirical_test()
