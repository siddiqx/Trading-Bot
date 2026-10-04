"""
Exhaustive Pattern Optimization & Sensitivity Audit
Tests systematic improvements identified from the 2-Year Monthly Cohort Audit:
1. Sunday Market Entry Exclusion (9.1% WR -> eradicate toxic Sunday gap entries)
2. Early Capital Protection / Break-Even threshold sensitivity (0.6R, 0.7R, 0.8R vs 1.0R)
3. Partial Take-Profit at 1.0R (Bank 50% at 1.0R, trail remainder to 1.75R)
4. Gold specific tuning (Donchian length, SL bounds, session filters)
5. Weekday session filtering (Thursday high-expectancy boost vs Wednesday reduction)
"""

import sys
import os
sys.path.insert(0, ".")
import pickle
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from scripts.deep_historical_2year_audit import compute_indicators, is_forex_market_open, get_session


def run_parameterized_sim(
    pairs_data,
    be_threshold_r=1.0,
    be_lock_pips=1.0,
    take_partial=False,
    partial_r=1.0,
    partial_pct=0.5,
    skip_sunday=True,
    gold_donch_len=20,
    gold_max_sl_pips=120.0,
    gold_min_sl_pips=15.0,
    skip_wednesday=False
):
    pairs = ["EURUSD", "USDCAD", "XAUUSD"]
    all_trades = []

    for pair in pairs:
        df = pairs_data[pair].copy()
        if "time_dt" not in df.columns:
            df["time_dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
        else:
            df["time_dt"] = pd.to_datetime(df["time_dt"], utc=True)
        df = df.sort_values("time_dt").reset_index(drop=True)

        pip = 0.10 if pair == "XAUUSD" else 0.0001
        digits = 2 if pair == "XAUUSD" else 5
        donch_len = gold_donch_len if pair == "XAUUSD" else 20
        min_sl_dist = (gold_min_sl_pips * pip) if pair == "XAUUSD" else 18.0 * pip
        max_sl_dist = (gold_max_sl_pips * pip) if pair == "XAUUSD" else 65.0 * pip
        rr = 1.75

        df = compute_indicators(df, donch_len=donch_len)
        active_trade = None
        start_idx = 50
        n = len(df)

        for i in range(start_idx, n):
            row = df.iloc[i]
            prev_row = df.iloc[i-1]
            t = row["time_dt"]

            if active_trade is not None:
                is_long = active_trade["direction"] == "LONG"
                entry = active_trade["entry"]
                sl = active_trade["stop_loss"]
                tp = active_trade["take_profit"]
                sl_dist = active_trade["sl_dist"]
                be_active = active_trade["be_active"]
                partial_taken = active_trade["partial_taken"]
                h_open = active_trade["opened_at"]
                holding_hours = (t - h_open).total_seconds() / 3600.0

                # Check partial take profit
                if take_partial and not partial_taken:
                    partial_target_dist = partial_r * sl_dist
                    if is_long and (row["high"] - entry) >= partial_target_dist:
                        active_trade["partial_taken"] = True
                        active_trade["partial_r_banked"] = partial_r * partial_pct
                    elif (not is_long) and (entry - row["low"]) >= partial_target_dist:
                        active_trade["partial_taken"] = True
                        active_trade["partial_r_banked"] = partial_r * partial_pct

                # Dynamic BE Lock at be_threshold_r
                if not be_active:
                    be_trigger_dist = be_threshold_r * sl_dist
                    if is_long and (row["high"] - entry) >= be_trigger_dist:
                        active_trade["stop_loss"] = entry + (be_lock_pips * pip)
                        active_trade["be_active"] = True
                        sl = active_trade["stop_loss"]
                    elif (not is_long) and (entry - row["low"]) >= be_trigger_dist:
                        active_trade["stop_loss"] = entry - (be_lock_pips * pip)
                        active_trade["be_active"] = True
                        sl = active_trade["stop_loss"]

                resolved = False
                exit_reason = None
                exit_price = None

                if is_long:
                    if row["low"] <= sl:
                        resolved = True
                        exit_price = sl
                        exit_reason = "BREAKEVEN" if active_trade["be_active"] else "STOP_LOSS"
                    elif row["high"] >= tp:
                        resolved = True
                        exit_price = tp
                        exit_reason = "TAKE_PROFIT"
                    elif holding_hours >= 24.0 and row["close"] < row["ema20"]:
                        resolved = True
                        exit_price = row["close"]
                        exit_reason = "EMA20_INVALIDATION"
                else:
                    if row["high"] >= sl:
                        resolved = True
                        exit_price = sl
                        exit_reason = "BREAKEVEN" if active_trade["be_active"] else "STOP_LOSS"
                    elif row["low"] <= tp:
                        resolved = True
                        exit_price = tp
                        exit_reason = "TAKE_PROFIT"
                    elif holding_hours >= 24.0 and row["close"] > row["ema20"]:
                        resolved = True
                        exit_price = row["close"]
                        exit_reason = "EMA20_INVALIDATION"

                if resolved:
                    initial_sl_pips = sl_dist / pip
                    if is_long:
                        rem_pips = (exit_price - entry) / pip
                    else:
                        rem_pips = (entry - exit_price) / pip

                    rem_r = rem_pips / (initial_sl_pips + 1e-9)

                    if take_partial and active_trade["partial_taken"]:
                        final_r = active_trade["partial_r_banked"] + (rem_r * (1.0 - partial_pct))
                        final_pips = (partial_r * initial_sl_pips * partial_pct) + (rem_pips * (1.0 - partial_pct))
                    else:
                        final_r = rem_r
                        final_pips = rem_pips

                    outcome = "WIN" if final_r > 0.1 else ("LOSS" if final_r < -0.1 else "BREAKEVEN")

                    record = {
                        "pair": pair,
                        "direction": active_trade["direction"],
                        "opened_at": active_trade["opened_at"],
                        "closed_at": t,
                        "exit_reason": exit_reason,
                        "outcome": outcome,
                        "realized_pips": round(final_pips, 1),
                        "realized_r": round(final_r, 2),
                        "holding_hours": round(holding_hours, 1),
                        "month_cohort": active_trade["opened_at"].strftime("%Y-%m")
                    }
                    all_trades.append(record)
                    active_trade = None

            if active_trade is None:
                if not is_forex_market_open(t):
                    continue
                if skip_sunday and t.weekday() == 6:
                    continue
                if skip_wednesday and t.weekday() == 2:
                    continue
                if 12 <= t.hour < 16:
                    continue
                adx_val = row["adx"]
                if 20.0 <= adx_val <= 30.0:
                    continue

                min_body = 0.60 if pair == "XAUUSD" else 0.55
                if row["body_ratio"] < min_body:
                    continue

                long_breakout = (row["close"] > row["donch_high"]) and (prev_row["close"] <= prev_row["donch_high"])
                short_breakout = (row["close"] < row["donch_low"]) and (prev_row["close"] >= prev_row["donch_low"])

                if pair == "XAUUSD":
                    if long_breakout and row["upper_wick_ratio"] > 0.35:
                        continue
                    if short_breakout and row["lower_wick_ratio"] > 0.35:
                        continue

                bullish_trend = (row["close"] > row["ema50"]) and (row["ema20"] > row["ema50"]) and (row["ema20_slope"] > 0) and (row["close"] > row["ema200"])
                bearish_trend = (row["close"] < row["ema50"]) and (row["ema20"] < row["ema50"]) and (row["ema20_slope"] < 0) and (row["close"] < row["ema200"])

                rsi_bullish = 40.0 <= row["rsi"] <= 80.0
                rsi_bearish = 20.0 <= row["rsi"] <= 60.0

                if long_breakout and bullish_trend and rsi_bullish:
                    ob_low = row["low"]
                    for b_i in range(i - 1, max(0, i - 10), -1):
                        if df.iloc[b_i]["close"] < df.iloc[b_i]["open"]:
                            ob_low = df.iloc[b_i]["low"]
                            break
                    entry = row["close"]
                    sl_cand = ob_low - (0.50 * row["atr"])
                    sl_dist = max(min_sl_dist, min(max_sl_dist, entry - sl_cand))
                    stop_loss = entry - sl_dist
                    take_profit = entry + (rr * sl_dist)

                    active_trade = {
                        "pair": pair,
                        "direction": "LONG",
                        "opened_at": t,
                        "entry": round(entry, digits),
                        "stop_loss": round(stop_loss, digits),
                        "take_profit": round(take_profit, digits),
                        "sl_dist": sl_dist,
                        "be_active": False,
                        "partial_taken": False,
                        "partial_r_banked": 0.0
                    }

                elif short_breakout and bearish_trend and rsi_bearish:
                    ob_high = row["high"]
                    for b_i in range(i - 1, max(0, i - 10), -1):
                        if df.iloc[b_i]["close"] > df.iloc[b_i]["open"]:
                            ob_high = df.iloc[b_i]["high"]
                            break
                    entry = row["close"]
                    sl_cand = ob_high + (0.50 * row["atr"])
                    sl_dist = max(min_sl_dist, min(max_sl_dist, sl_cand - entry))
                    stop_loss = entry + sl_dist
                    take_profit = entry - (rr * sl_dist)

                    active_trade = {
                        "pair": pair,
                        "direction": "SHORT",
                        "opened_at": t,
                        "entry": round(entry, digits),
                        "stop_loss": round(stop_loss, digits),
                        "take_profit": round(take_profit, digits),
                        "sl_dist": sl_dist,
                        "be_active": False,
                        "partial_taken": False,
                        "partial_r_banked": 0.0
                    }

    df_t = pd.DataFrame(all_trades)
    if len(df_t) == 0:
        return 0, 0, 0, 0, 0, 0

    tot = len(df_t)
    w = len(df_t[df_t["outcome"] == "WIN"])
    l = len(df_t[df_t["outcome"] == "LOSS"])
    be = len(df_t[df_t["outcome"] == "BREAKEVEN"])
    wr = (w / tot) * 100.0
    net_r = df_t["realized_r"].sum()
    net_pips = df_t["realized_pips"].sum()
    g_win = df_t[df_t["realized_r"] > 0]["realized_r"].sum()
    g_loss = abs(df_t[df_t["realized_r"] < 0]["realized_r"].sum())
    pf = (g_win / g_loss) if g_loss > 0 else 99.0

    return tot, wr, net_r, net_pips, pf, df_t

def main():
    with open("archives/portfolio_8pairs_cache.pkl", "rb") as f:
        data_8pairs = pickle.load(f)

    print("=================== STRATEGY PARAMETER SENSITIVITY GRID ===================")
    configs = [
        ("1. Baseline (Current System)", dict(be_threshold_r=1.0, skip_sunday=False, take_partial=False)),
        ("2. Baseline + Exclude Sunday", dict(be_threshold_r=1.0, skip_sunday=True, take_partial=False)),
        ("3. Advance BE to +0.8R (+Sunday Excl)", dict(be_threshold_r=0.8, skip_sunday=True, take_partial=False)),
        ("4. Advance BE to +0.7R (+Sunday Excl)", dict(be_threshold_r=0.7, skip_sunday=True, take_partial=False)),
        ("5. Advance BE to +0.6R (+Sunday Excl)", dict(be_threshold_r=0.6, skip_sunday=True, take_partial=False)),
        ("6. Partial TP (Bank 50% at 1.0R, BE at +0.7R)", dict(be_threshold_r=0.7, skip_sunday=True, take_partial=True, partial_r=1.0, partial_pct=0.5)),
        ("7. Gold Calibrated: Donchian 25 + Max SL 100p + BE 0.7R", dict(be_threshold_r=0.7, skip_sunday=True, take_partial=False, gold_donch_len=25, gold_max_sl_pips=100.0)),
        ("8. Optimized Hybrid: Partial TP 1.0R + BE 0.7R + Gold Donch 25", dict(be_threshold_r=0.7, skip_sunday=True, take_partial=True, partial_r=1.0, partial_pct=0.5, gold_donch_len=25, gold_max_sl_pips=100.0)),
    ]

    for label, kwargs in configs:
        tot, wr, net_r, net_pips, pf, df_t = run_parameterized_sim(data_8pairs, **kwargs)
        print(f"\n{label}")
        print(f"   Trades: {tot} | Win Rate: {wr:.1f}% | Net R: {net_r:+6.2f}R | Net Pips: {net_pips:+8.1f}p | Profit Factor: {pf:.2f}")

        # Per pair breakdown
        for p in ["EURUSD", "USDCAD", "XAUUSD"]:
            sub = df_t[df_t["pair"] == p]
            if len(sub) > 0:
                p_w = len(sub[sub["outcome"] == "WIN"])
                p_wr = (p_w / len(sub)) * 100.0
                p_r = sub["realized_r"].sum()
                p_pips = sub["realized_pips"].sum()
                print(f"     -> {p:7s}: {len(sub):3d} trades | WR: {p_wr:4.1f}% | Net R: {p_r:+6.2f}R | Net Pips: {p_pips:+8.1f}p")

if __name__ == "__main__":
    main()
