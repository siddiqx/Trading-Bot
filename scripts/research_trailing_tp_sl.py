#!/usr/bin/env python3
"""
Research Script: Evaluating Trailing TP / SL vs Fixed 30-Pip Targets.
Determines whether letting trades run to 50+ pips with trailing stop loss improves net profitability.

Compares:
1. Model 1 (Baseline Fixed Target): 1:1.50 R:R (~30-33 pips fixed TP, 20-22 pips SL).
2. Model 2 (Fixed Target 50 Pips): Target 50.0 pips fixed (+2.3R), 22.0 pips SL.
3. Model 3 (Breakeven + Runner): At +1.0R (+22p), SL -> Breakeven. Target extended to +55p (+2.5R).
4. Model 4 (Volatility Cushion Trailing):
   - At +1.2R (+26.4p): SL moves to -10p (risk halved).
   - At +1.5R (+33.0p): Lock in +15p profit, extend runner TP to +55p (+2.5R).
5. Model 5 (Dynamic Trailing Stop after +1.5R):
   - Fixed TP removed. Once +1.5R (+33p) is reached, SL locks at +15p and trails 18 pips behind peak MFE.
6. Model 6 (Aggressive Trailing Stop after +1.0R):
   - Once +1.0R (+22p) is reached, SL trails 15 pips behind peak MFE up to unlimited pips.

Tested on 60-day 15M tick-precise execution candles with 1H CCRS Macro Flow across all 6 pairs.
"""

import sys
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import pandas as pd
from market_scanner import fetch_candles, compute_indicators, SYMBOLS, get_usd_directional_bias
from core.config import (
    CCRS_LOOKBACK_HOURS,
    CCRS_Z_WINDOW_HOURS,
    CCRS_Z_THRESHOLD,
    CANONICAL_STOP_LOSS_PIPS,
    CANONICAL_TAKE_PROFIT_PIPS,
    CANONICAL_TRANSACTION_COSTS,
    MAX_CONCURRENT_UNPROTECTED_TRADES,
    MAX_CONCURRENT_USD_EXPOSURE,
)


def load_datasets():
    print("Loading 180 days 1H and 60 days 15M data...")
    dfs_1h = {}
    for p, cfg in SYMBOLS.items():
        df = fetch_candles(cfg["ticker"], "1h", range_days="180d")
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df["close_time"] = df["time"] + pd.Timedelta(hours=1)
        dfs_1h[p] = df.sort_values("time").reset_index(drop=True)

    dfs_15m = {}
    for p, cfg in SYMBOLS.items():
        df = fetch_candles(cfg["ticker"], "15m", range_days="60d")
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df["close_time"] = df["time"] + pd.Timedelta(minutes=15)
        dfs_15m[p] = df.sort_values("time").reset_index(drop=True)

    # 1H CCRS Divergence Matrix
    close_1h = pd.DataFrame({p: df.set_index("close_time")["close"] for p, df in dfs_1h.items()}).dropna()
    lb = CCRS_LOOKBACK_HOURS
    z_win = CCRS_Z_WINDOW_HOURS

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
    ccrs_div_1h = pd.DataFrame(index=close_1h.index)
    ccrs_div_1h["EURUSD"] = z_scores["EUR"] - z_scores["USD"]
    ccrs_div_1h["GBPUSD"] = z_scores["GBP"] - z_scores["USD"]
    ccrs_div_1h["AUDUSD"] = z_scores["AUD"] - z_scores["USD"]
    ccrs_div_1h["USDJPY"] = z_scores["USD"] - z_scores["JPY"]
    ccrs_div_1h["USDCAD"] = z_scores["USD"] - z_scores["CAD"]
    ccrs_div_1h["USDCHF"] = z_scores["USD"] - z_scores["CHF"]

    ind_15m = {}
    for p, df in dfs_15m.items():
        d = compute_indicators(df, donchian_len=20)
        ind_15m[p] = d.set_index("close_time")

    return ccrs_div_1h, ind_15m


def simulate_trailing_model(
    ccrs_div_1h: pd.DataFrame,
    ind_15m: dict,
    model_type: str = "BASELINE",
    risk_pct: float = 0.50,
):
    common_times = sorted(list(set.intersection(*[set(df.index) for df in ind_15m.values()])))
    active_trades = []
    completed_trades = []
    equity = 5000.0
    equity_curve = []

    for t in common_times:
        hour_utc = t.hour
        surviving = []

        for tr in active_trades:
            p = tr["pair"]
            bar = ind_15m[p].loc[t]
            pip = 0.0001 if "JPY" not in p else 0.01
            entry = tr["entry"]
            spread_pips = CANONICAL_TRANSACTION_COSTS.get(p, {}).get("total_pips", 1.3)
            risk_usd = tr["risk_usd"]

            # Intra-bar favorable / adverse excursions
            if tr["direction"] == "LONG":
                bar_mfe = (bar["high"] - entry) / pip
                bar_mae = (entry - bar["low"]) / pip
                bar_close_pnl = (bar["close"] - entry) / pip
            else:
                bar_mfe = (entry - bar["low"]) / pip
                bar_mae = (bar["high"] - entry) / pip
                bar_close_pnl = (entry - bar["close"]) / pip

            # Update trade lifetime max favorable excursion
            tr["peak_mfe"] = max(tr["peak_mfe"], bar_mfe)
            peak_mfe = tr["peak_mfe"]

            # Apply Trailing Logic Based on Model Type
            current_sl_pips = tr["sl_pips"]  # positive means risk, negative means locked profit
            current_tp_pips = tr["tp_pips"]

            if model_type == "BASELINE":
                # Fixed 33p TP / 22p SL
                pass

            elif model_type == "FIXED_50P":
                # Fixed 50p TP / 22p SL
                current_tp_pips = 50.0

            elif model_type == "BREAKEVEN_RUNNER":
                # At +22p (+1.0R), move SL to BE (+0p). TP = 55p (+2.5R)
                if peak_mfe >= 22.0:
                    current_sl_pips = 0.0
                    current_tp_pips = 55.0

            elif model_type == "VOLATILITY_CUSHION":
                # At +1.2R (+26.4p), SL moves to -10p (cuts risk to 10p)
                # At +1.5R (+33.0p), SL moves to +15p (profit lock), TP extends to +55p (+2.5R)
                if peak_mfe >= 33.0:
                    current_sl_pips = -15.0  # locked +15p profit
                    current_tp_pips = 55.0   # extended target
                elif peak_mfe >= 26.4:
                    current_sl_pips = 10.0   # risk reduced from 22p to 10p

            elif model_type == "TRAILING_AFTER_15R":
                # Once +1.5R (+33p) is reached, remove fixed TP, lock +15p, and trail 18p behind peak MFE
                if peak_mfe >= 33.0:
                    current_tp_pips = 999.0  # unconstrained runner
                    # Trail 18 pips behind peak
                    trail_level = peak_mfe - 18.0
                    current_sl_pips = -max(15.0, trail_level)  # guaranteed at least +15p locked

            elif model_type == "AGGRESSIVE_TRAIL_10R":
                # Once +1.0R (+22p) is reached, trail 15p behind peak MFE
                if peak_mfe >= 22.0:
                    current_tp_pips = 999.0
                    trail_level = peak_mfe - 15.0
                    current_sl_pips = -max(0.0, trail_level)  # at least BE

            # Check exits
            hit_sl = False
            hit_tp = False

            # Check SL
            if current_sl_pips > 0:
                # Normal SL above entry
                if bar_mae >= current_sl_pips:
                    hit_sl = True
            else:
                # Locked in profit: if price retraces back to entry + abs(current_sl_pips)
                # i.e. if current candle low/close dropped below locked profit level
                locked_profit = abs(current_sl_pips)
                if tr["direction"] == "LONG":
                    lowest_pnl_in_bar = (bar["low"] - entry) / pip
                else:
                    lowest_pnl_in_bar = (entry - bar["high"]) / pip
                if lowest_pnl_in_bar <= locked_profit:
                    hit_sl = True

            # Check TP
            if bar_mfe >= current_tp_pips:
                hit_tp = True

            # Pessimistic Intra-Candle Assumption: SL takes precedence
            if hit_sl and hit_tp:
                hit_tp = False

            if hit_sl:
                if current_sl_pips > 0:
                    # Loss
                    realized_pips = -(current_sl_pips + spread_pips)
                    r_val = -1.0
                else:
                    # Trailing Profit Exit
                    realized_pips = abs(current_sl_pips) - spread_pips
                    r_val = realized_pips / 22.0

                realized_usd = risk_usd * r_val
                equity += realized_usd
                tr.update({
                    "outcome": "WIN" if realized_pips > 0 else "LOSS",
                    "pnl_pips": realized_pips,
                    "pnl_usd": realized_usd,
                    "r": r_val,
                    "exit_time": t,
                    "exit_reason": "TRAIL_STOP" if current_sl_pips <= 0 else "STOP_LOSS"
                })
                completed_trades.append(tr)

            elif hit_tp:
                realized_pips = current_tp_pips - spread_pips
                r_val = realized_pips / 22.0
                realized_usd = risk_usd * r_val
                equity += realized_usd
                tr.update({
                    "outcome": "WIN",
                    "pnl_pips": realized_pips,
                    "pnl_usd": realized_usd,
                    "r": r_val,
                    "exit_time": t,
                    "exit_reason": "TAKE_PROFIT"
                })
                completed_trades.append(tr)

            elif (t - tr["entry_time"]).total_seconds() >= 48 * 3600:
                # 48h timeout
                realized_pips = bar_close_pnl - spread_pips
                r_val = realized_pips / 22.0
                realized_usd = risk_usd * r_val
                equity += realized_usd
                tr.update({
                    "outcome": "WIN" if realized_pips > 0 else "LOSS",
                    "pnl_pips": realized_pips,
                    "pnl_usd": realized_usd,
                    "r": r_val,
                    "exit_time": t,
                    "exit_reason": "TIMEOUT_48H"
                })
                completed_trades.append(tr)
            else:
                surviving.append(tr)

        active_trades = surviving
        equity_curve.append({"time": t, "equity": equity})

        # Session & Concurrency Filters
        if not (6 <= hour_utc <= 17):
            continue
        if len(active_trades) >= 2:
            continue

        active_pairs = {tr["pair"] for tr in active_trades}
        past_1h = ccrs_div_1h[ccrs_div_1h.index <= t]
        if past_1h.empty:
            continue
        cur_div_row = past_1h.iloc[-1]

        for p in SYMBOLS.keys():
            if p in active_pairs or len(active_trades) >= 2:
                continue

            div_val = cur_div_row[p]
            if abs(div_val) < CCRS_Z_THRESHOLD:
                continue

            is_long = div_val > 0
            direction = "LONG" if is_long else "SHORT"

            # USD exposure cap = 1
            sig_bias = get_usd_directional_bias(p, direction)
            if sig_bias != 0:
                same_bias_cnt = sum(1 for tr in active_trades if get_usd_directional_bias(tr["pair"], tr["direction"]) == sig_bias)
                if same_bias_cnt >= MAX_CONCURRENT_USD_EXPOSURE:
                    continue

            df_bar = ind_15m[p]
            if t not in df_bar.index:
                continue
            idx = df_bar.index.get_loc(t)
            if idx < 20:
                continue
            curr = df_bar.iloc[idx]
            prev = df_bar.iloc[idx - 1]
            pip = 0.0001 if "JPY" not in p else 0.01

            trigger = False
            if is_long:
                tested_ema = (curr["low"] <= curr["ema20"] * 1.0003) and (curr["close"] > curr["open"]) and (curr["close"] > curr["ema20"])
                swept_low = (curr["low"] < prev["donch_low10"]) and (curr["close"] > prev["donch_low10"])
                trigger = tested_ema or swept_low
            else:
                tested_ema = (curr["high"] >= curr["ema20"] * 0.9997) and (curr["close"] < curr["open"]) and (curr["close"] < curr["ema20"])
                swept_high = (curr["high"] > prev["donch_high10"]) and (curr["close"] < prev["donch_high10"])
                trigger = tested_ema or swept_high

            if not trigger:
                continue

            entry = curr["close"]
            sl_pips = CANONICAL_STOP_LOSS_PIPS
            tp_pips = CANONICAL_TAKE_PROFIT_PIPS
            risk_usd = equity * (risk_pct / 100.0)

            active_trades.append({
                "pair": p,
                "direction": direction,
                "entry": entry,
                "sl_pips": sl_pips,
                "tp_pips": tp_pips,
                "peak_mfe": 0.0,
                "risk_usd": risk_usd,
                "entry_time": t
            })
            active_pairs.add(p)

    return pd.DataFrame(completed_trades), pd.DataFrame(equity_curve)


def compute_metrics(df_trades: pd.DataFrame, df_eq: pd.DataFrame, name: str):
    tot = len(df_trades)
    if tot == 0:
        return {"Model": name, "Trades": 0, "WinRate%": 0.0, "PF": 0.0, "NetPips": 0.0, "NetUSD": 0.0, "AvgWinPips": 0.0, "MaxPipsTrade": 0.0, "MaxOverallDD%": 0.0}

    wins = df_trades[df_trades["pnl_pips"] > 0]
    losses = df_trades[df_trades["pnl_pips"] <= 0]
    wr = (len(wins) / tot) * 100.0
    net_pips = df_trades["pnl_pips"].sum()
    net_usd = df_trades["pnl_usd"].sum()

    gw = wins["pnl_usd"].sum()
    gl = abs(losses["pnl_usd"].sum())
    pf = (gw / gl) if gl > 0 else 999.0

    avg_win_pips = wins["pnl_pips"].mean() if len(wins) > 0 else 0.0
    max_pips_trade = df_trades["pnl_pips"].max()

    peak = df_eq["equity"].cummax()
    overall_dd_usd = peak - df_eq["equity"]
    max_overall_dd_pct = (overall_dd_usd.max() / 5000.0) * 100.0

    return {
        "Model": name,
        "Trades": tot,
        "WinRate%": round(wr, 1),
        "PF": round(pf, 2),
        "NetPips": round(net_pips, 1),
        "NetUSD": round(net_usd, 2),
        "AvgWinPips": round(avg_win_pips, 1),
        "MaxPipsTrade": round(max_pips_trade, 1),
        "MaxOverallDD%": round(max_overall_dd_pct, 2),
    }


def main():
    ccrs_div_1h, ind_15m = load_datasets()

    models = [
        ("1. Baseline Fixed (33p TP / 22p SL)", "BASELINE"),
        ("2. Fixed 50-Pip Target (50p TP / 22p SL)", "FIXED_50P"),
        ("3. Breakeven + 55p Runner Target", "BREAKEVEN_RUNNER"),
        ("4. Volatility Cushion (Lock +15p @ 33p, TP 55p)", "VOLATILITY_CUSHION"),
        ("5. Dynamic Trailing Runner after +1.5R (33p)", "TRAILING_AFTER_15R"),
        ("6. Aggressive Trailing Stop after +1.0R (22p)", "AGGRESSIVE_TRAIL_10R"),
    ]

    results = []
    print("\nRunning Trailing Simulation Matrix...")
    for label, mtype in models:
        df_trades, df_eq = simulate_trailing_model(ccrs_div_1h, ind_15m, model_type=mtype)
        m = compute_metrics(df_trades, df_eq, label)
        results.append(m)
        print(f"[{mtype}] Trades: {m['Trades']} | WR: {m['WinRate%']}% | PF: {m['PF']} | Net Pips: {m['NetPips']} | Avg Win: {m['AvgWinPips']}p | Max Trade: {m['MaxPipsTrade']}p | Max DD: {m['MaxOverallDD%']}%")

    res_df = pd.DataFrame(results)
    print("\n" + "=" * 115)
    print("EMPIRICAL TRAILING TP/SL COMPARISON MATRIX (PAST 60 DAYS - 15M DUAL-TF)")
    print("=" * 115)
    print(res_df.to_string(index=False))

    out_path = Path("journals/TRAILING_TP_SL_RESEARCH.md")
    with open(out_path, "w") as f:
        f.write("# EMPIRICAL RESEARCH: FIXED 30-PIP TARGETS VS. TRAILING TP/SL RUNNERS\n\n")
        f.write(res_df.to_markdown(index=False))
        f.write("\n")
    print(f"\nSaved research findings to {out_path}")


if __name__ == "__main__":
    main()
