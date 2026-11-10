#!/usr/bin/env python3
"""
Research Script: Impact of Removing Losing Factors on Win Rate, Performance, and Frequency.

Evaluates:
1. Baseline Production (v3.3.0)
2. ADX Filter variants (ADX <= 45, ADX <= 35, ADX <= 30)
3. Candle Body Ratio Filter (>= 50%)
4. Strict USD Directional Bias (Max 1 concurrent USD exposure)
5. Weekend Holding Filter (No Friday entries >= 12:00 UTC)
6. Session Cutoff Filter (No entries >= 16:00 UTC)
7. Synergistic Portfolio Combinations:
   - Combo A: Strict USD Bias (<=1) + Weekend Hold (No Fri >= 12:00)
   - Combo B: Strict USD Bias (<=1) + Weekend Hold + Session Cutoff (<16:00)
   - Combo C: Strict USD Bias (<=1) + Weekend Hold + Mild ADX Exhaustion (<=45)
"""

import sys
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import pandas as pd
from market_scanner import fetch_candles, compute_indicators, SYMBOLS
from core.config import (
    CCRS_LOOKBACK_HOURS,
    CCRS_Z_WINDOW_HOURS,
    CCRS_Z_THRESHOLD,
    CANONICAL_STOP_LOSS_PIPS,
    CANONICAL_TAKE_PROFIT_PIPS,
    CANONICAL_TRANSACTION_COSTS,
    MAX_CONCURRENT_UNPROTECTED_TRADES,
)
from market_scanner import get_usd_directional_bias


def load_datasets():
    print("Loading 180 days of 1H data and 60 days of 15M data from Yahoo Finance...")
    dfs_1h = {}
    for p, cfg in SYMBOLS.items():
        df = fetch_candles(cfg["ticker"], "1h", range_days="180d")
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df["close_time"] = df["time"] + pd.Timedelta(hours=1)
        df = df.sort_values("time").reset_index(drop=True)
        dfs_1h[p] = df

    dfs_15m = {}
    for p, cfg in SYMBOLS.items():
        df = fetch_candles(cfg["ticker"], "15m", range_days="60d")
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df["close_time"] = df["time"] + pd.Timedelta(minutes=15)
        df = df.sort_values("time").reset_index(drop=True)
        dfs_15m[p] = df

    # Precompute 1H CCRS Matrix
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


def run_simulation(
    ccrs_div_1h: pd.DataFrame,
    ind_15m: dict,
    max_adx: float = None,
    min_body_ratio: float = None,
    max_usd_exposure: int = 2,
    session_cutoff_hour: int = None,
    restrict_friday_after_noon: bool = False,
    risk_pct: float = 0.50,
):
    common_times = sorted(list(set.intersection(*[set(df.index) for df in ind_15m.values()])))
    active_trades = []
    completed_trades = []
    equity = 5000.0
    equity_curve = []

    for t in common_times:
        hour_utc = t.hour
        weekday = t.weekday()

        surviving = []
        for tr in active_trades:
            p = tr["pair"]
            bar = ind_15m[p].loc[t]
            pip = 0.0001 if "JPY" not in p else 0.01
            entry = tr["entry"]
            sl = tr["sl"]
            tp = tr["tp"]
            sl_pips = tr["sl_pips"]
            tp_pips = tr["tp_pips"]
            spread_pips = CANONICAL_TRANSACTION_COSTS.get(p, {}).get("total_pips", 1.3)
            risk_usd = tr["risk_usd"]

            if tr["direction"] == "LONG":
                hit_sl = bar["low"] <= sl
                hit_tp = bar["high"] >= tp
                if hit_sl and hit_tp:
                    hit_tp = False  # SL takes precedence

                if hit_sl:
                    pnl_pips = -(sl_pips + spread_pips)
                    realized_usd = -risk_usd * (1.0 + (spread_pips / sl_pips))
                    equity += realized_usd
                    tr.update({"outcome": "LOSS", "pnl_pips": pnl_pips, "pnl_usd": realized_usd, "r": -1.0, "exit_time": t})
                    completed_trades.append(tr)
                elif hit_tp:
                    pnl_pips = tp_pips - spread_pips
                    realized_usd = (risk_usd * 1.50) - (risk_usd * (spread_pips / sl_pips))
                    equity += realized_usd
                    tr.update({"outcome": "WIN", "pnl_pips": pnl_pips, "pnl_usd": realized_usd, "r": 1.50 - (spread_pips / sl_pips), "exit_time": t})
                    completed_trades.append(tr)
                elif (t - tr["entry_time"]).total_seconds() >= 36 * 3600:
                    pnl_raw = ((bar["close"] - entry) / pip) - spread_pips
                    r_val = pnl_raw / sl_pips
                    realized_usd = risk_usd * r_val
                    equity += realized_usd
                    tr.update({"outcome": "WIN" if pnl_raw > 0 else "LOSS", "pnl_pips": pnl_raw, "pnl_usd": realized_usd, "r": r_val, "exit_time": t})
                    completed_trades.append(tr)
                else:
                    surviving.append(tr)
            else:
                hit_sl = bar["high"] >= sl
                hit_tp = bar["low"] <= tp
                if hit_sl and hit_tp:
                    hit_tp = False

                if hit_sl:
                    pnl_pips = -(sl_pips + spread_pips)
                    realized_usd = -risk_usd * (1.0 + (spread_pips / sl_pips))
                    equity += realized_usd
                    tr.update({"outcome": "LOSS", "pnl_pips": pnl_pips, "pnl_usd": realized_usd, "r": -1.0, "exit_time": t})
                    completed_trades.append(tr)
                elif hit_tp:
                    pnl_pips = tp_pips - spread_pips
                    realized_usd = (risk_usd * 1.50) - (risk_usd * (spread_pips / sl_pips))
                    equity += realized_usd
                    tr.update({"outcome": "WIN", "pnl_pips": pnl_pips, "pnl_usd": realized_usd, "r": 1.50 - (spread_pips / sl_pips), "exit_time": t})
                    completed_trades.append(tr)
                elif (t - tr["entry_time"]).total_seconds() >= 36 * 3600:
                    pnl_raw = ((entry - bar["close"]) / pip) - spread_pips
                    r_val = pnl_raw / sl_pips
                    realized_usd = risk_usd * r_val
                    equity += realized_usd
                    tr.update({"outcome": "WIN" if pnl_raw > 0 else "LOSS", "pnl_pips": pnl_raw, "pnl_usd": realized_usd, "r": r_val, "exit_time": t})
                    completed_trades.append(tr)
                else:
                    surviving.append(tr)

        active_trades = surviving
        equity_curve.append({"time": t, "equity": equity})

        # Session Filter: Canonical 06:00 to 17:00 UTC
        if not (6 <= hour_utc <= 17):
            continue

        if session_cutoff_hour is not None and hour_utc >= session_cutoff_hour:
            continue

        if restrict_friday_after_noon and weekday == 4 and hour_utc >= 12:
            continue

        if len(active_trades) >= MAX_CONCURRENT_UNPROTECTED_TRADES:
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

            sig_bias = get_usd_directional_bias(p, direction)
            if sig_bias != 0:
                current_same_bias_count = sum(
                    1 for tr in active_trades
                    if get_usd_directional_bias(tr["pair"], tr["direction"]) == sig_bias
                )
                if current_same_bias_count >= max_usd_exposure:
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

            curr_adx = curr.get("adx", 0.0)
            if max_adx is not None and curr_adx > max_adx:
                continue

            candle_range = curr["high"] - curr["low"]
            body_size = abs(curr["close"] - curr["open"])
            body_ratio = (body_size / candle_range) if candle_range > 0 else 0.0
            is_directional = (curr["close"] > curr["open"]) if is_long else (curr["close"] < curr["open"])

            if min_body_ratio is not None:
                if body_ratio < min_body_ratio or not is_directional:
                    continue

            entry = curr["close"]
            sl_pips = CANONICAL_STOP_LOSS_PIPS
            tp_pips = CANONICAL_TAKE_PROFIT_PIPS

            if direction == "LONG":
                sl = entry - (sl_pips * pip)
                tp = entry + (tp_pips * pip)
            else:
                sl = entry + (sl_pips * pip)
                tp = entry - (tp_pips * pip)

            risk_usd = equity * (risk_pct / 100.0)
            active_trades.append({
                "pair": p,
                "direction": direction,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "sl_pips": sl_pips,
                "tp_pips": tp_pips,
                "risk_usd": risk_usd,
                "entry_time": t,
                "adx_at_entry": curr_adx,
                "body_ratio_at_entry": body_ratio,
                "usd_bias": sig_bias,
            })
            active_pairs.add(p)

    return pd.DataFrame(completed_trades), pd.DataFrame(equity_curve)


def compute_metrics(df_trades: pd.DataFrame, df_eq: pd.DataFrame, name: str, base_trades_cnt: int = 0):
    tot = len(df_trades)
    if tot == 0:
        return {
            "variant": name, "trades": 0, "trades_per_month": 0.0,
            "freq_retained_pct": 0.0, "win_rate_pct": 0.0, "profit_factor": 0.0,
            "expectancy_r": 0.0, "net_pips": 0.0, "net_usd": 0.0,
            "max_daily_dd_pct": 0.0, "max_overall_dd_pct": 0.0,
        }

    wins = len(df_trades[df_trades["pnl_pips"] > 0])
    losses = len(df_trades[df_trades["pnl_pips"] <= 0])
    wr = (wins / tot) * 100.0
    net_pips = df_trades["pnl_pips"].sum()
    net_usd = df_trades["pnl_usd"].sum()
    exp_r = df_trades["r"].mean()

    gw = df_trades[df_trades["pnl_usd"] > 0]["pnl_usd"].sum()
    gl = abs(df_trades[df_trades["pnl_usd"] < 0]["pnl_usd"].sum())
    pf = (gw / gl) if gl > 0 else 999.0

    days = (df_trades["exit_time"].max() - df_trades["entry_time"].min()).total_seconds() / 86400.0
    tpm = (tot / days) * 30.4 if days > 0 else 0.0
    freq_retained = (tot / base_trades_cnt * 100.0) if base_trades_cnt > 0 else 100.0

    df_eq["date"] = pd.to_datetime(df_eq["time"]).dt.date
    daily_start = df_eq.groupby("date")["equity"].first()
    daily_min = df_eq.groupby("date")["equity"].min()
    daily_dd_usd = daily_start - daily_min
    max_daily_dd_pct = (daily_dd_usd.max() / 5000.0) * 100.0

    peak = df_eq["equity"].cummax()
    overall_dd_usd = peak - df_eq["equity"]
    max_overall_dd_pct = (overall_dd_usd.max() / 5000.0) * 100.0

    return {
        "variant": name,
        "trades": tot,
        "trades_per_month": round(tpm, 1),
        "freq_retained_pct": round(freq_retained, 1),
        "win_rate_pct": round(wr, 1),
        "profit_factor": round(pf, 2),
        "expectancy_r": round(exp_r, 3),
        "net_pips": round(net_pips, 1),
        "net_usd": round(net_usd, 2),
        "max_daily_dd_pct": round(max_daily_dd_pct, 2),
        "max_overall_dd_pct": round(max_overall_dd_pct, 2),
    }


def main():
    ccrs_div_1h, ind_15m = load_datasets()

    print("\nRunning Granular Empirical Comparison...")
    variants = [
        {"name": "0. Baseline (Production v3.3.0)", "max_adx": None, "min_body_ratio": None, "max_usd_exposure": 2, "session_cutoff_hour": None, "restrict_friday_after_noon": False},
        {"name": "1. Filter ADX <= 45 (Extreme Climax Cap)", "max_adx": 45.0, "min_body_ratio": None, "max_usd_exposure": 2, "session_cutoff_hour": None, "restrict_friday_after_noon": False},
        {"name": "2. Filter ADX <= 35 (Exhaustion Cap)", "max_adx": 35.0, "min_body_ratio": None, "max_usd_exposure": 2, "session_cutoff_hour": None, "restrict_friday_after_noon": False},
        {"name": "3. Filter ADX <= 30 (Strict Trend Cap)", "max_adx": 30.0, "min_body_ratio": None, "max_usd_exposure": 2, "session_cutoff_hour": None, "restrict_friday_after_noon": False},
        {"name": "4. Filter Body Ratio >= 50% (Displacement Only)", "max_adx": None, "min_body_ratio": 0.50, "max_usd_exposure": 2, "session_cutoff_hour": None, "restrict_friday_after_noon": False},
        {"name": "5. Filter Strict USD Bias <= 1 (Max 1 Correlated USD)", "max_adx": None, "min_body_ratio": None, "max_usd_exposure": 1, "session_cutoff_hour": None, "restrict_friday_after_noon": False},
        {"name": "6. Filter Session Cutoff < 16:00 UTC", "max_adx": None, "min_body_ratio": None, "max_usd_exposure": 2, "session_cutoff_hour": 16, "restrict_friday_after_noon": False},
        {"name": "7. Filter Weekend Hold (No Fri >= 12:00 UTC)", "max_adx": None, "min_body_ratio": None, "max_usd_exposure": 2, "session_cutoff_hour": None, "restrict_friday_after_noon": True},
        {"name": "8. Synergistic Combo A: USD <= 1 + Weekend Hold", "max_adx": None, "min_body_ratio": None, "max_usd_exposure": 1, "session_cutoff_hour": None, "restrict_friday_after_noon": True},
        {"name": "9. Synergistic Combo B: USD <= 1 + Weekend Hold + Session < 16:00", "max_adx": None, "min_body_ratio": None, "max_usd_exposure": 1, "session_cutoff_hour": 16, "restrict_friday_after_noon": True},
        {"name": "10. Synergistic Combo C: USD <= 1 + Weekend Hold + ADX <= 45", "max_adx": 45.0, "min_body_ratio": None, "max_usd_exposure": 1, "session_cutoff_hour": None, "restrict_friday_after_noon": True},
    ]

    results = []
    base_trades_cnt = 0

    for i, v in enumerate(variants):
        df_trades, df_eq = run_simulation(
            ccrs_div_1h,
            ind_15m,
            max_adx=v["max_adx"],
            min_body_ratio=v["min_body_ratio"],
            max_usd_exposure=v["max_usd_exposure"],
            session_cutoff_hour=v["session_cutoff_hour"],
            restrict_friday_after_noon=v["restrict_friday_after_noon"],
        )
        if i == 0:
            base_trades_cnt = len(df_trades)

        met = compute_metrics(df_trades, df_eq, v["name"], base_trades_cnt=base_trades_cnt)
        results.append(met)
        print(f"[{i+1}/{len(variants)}] {v['name']}: {met['trades']} trades | WR: {met['win_rate_pct']}% | PF: {met['profit_factor']} | Net Pips: {met['net_pips']} | DD: {met['max_daily_dd_pct']}%")

    res_df = pd.DataFrame(results)
    print("\n" + "=" * 125)
    print("EMPIRICAL FACTOR ISOLATION & SYNERGY MATRIX (60-DAY 15M DUAL-TF EXECUTION)")
    print("=" * 125)
    print(res_df.to_string(index=False))

    out_md = Path("journals/LOSING_FACTORS_RESEARCH.md")
    with open(out_md, "w") as f:
        f.write("# EMPIRICAL RESEARCH: REMOVING LOSING FACTORS ON WIN RATE, PERFORMANCE & FREQUENCY\n\n")
        f.write(res_df.to_markdown(index=False))
        f.write("\n")
    print(f"\nSaved report to {out_md}")


if __name__ == "__main__":
    main()
