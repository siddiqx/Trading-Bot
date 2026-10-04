"""
Deep Historical 2-Year Monthly Cohort Audit & Strategy Pattern Mining Engine
Tests the production strategy from market_scanner.py across 24 separate monthly sets
(October 2024 to September 2026) for EURUSD, USDCAD, and XAUUSD.
Extracts winning patterns, failure modes, and optimization vectors.
"""

import sys
import os
import pickle
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

def is_forex_market_open(dt):
    """Checks whether Forex & Spot Gold markets are open (closes Fri 17:00 NY to Sun 17:00 NY)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ny_tz = ZoneInfo("America/New_York")
    ny_time = dt.astimezone(ny_tz)
    day = ny_time.weekday()  # 0=Mon ... 4=Fri, 5=Sat, 6=Sun
    h = ny_time.hour
    m = ny_time.minute
    if day == 5:
        return False
    if day == 4 and (h > 17 or (h == 17 and m >= 0)):
        return False
    if day == 6 and (h < 17):
        return False
    return True

def get_session(dt):
    h = dt.hour
    if 5 <= h < 12:
        return "London"
    elif 16 <= h < 20:
        return "NY_Afternoon"
    elif 12 <= h < 16:
        return "London_NY_Overlap"
    else:
        return "Asian_Tokyo"

def compute_indicators(df, donch_len=20):
    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    open_ = df["open"]

    df["ema20"] = close.ewm(span=20, adjust=False).mean()
    df["ema50"] = close.ewm(span=50, adjust=False).mean()
    df["ema200"] = close.ewm(span=200, adjust=False).mean()
    df["ema20_slope"] = df["ema20"] - df["ema20"].shift(2)

    df["donch_high"] = high.shift(1).rolling(donch_len).max()
    df["donch_low"] = low.shift(1).rolling(donch_len).min()

    # True Range & ATR (14)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1.0/14.0, adjust=False).mean()

    # RSI (14)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1.0/14.0, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0/14.0, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    df["rsi"] = 100.0 - (100.0 / (1.0 + rs))

    # ADX (14)
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    plus_dm = (high - prev_high).clip(lower=0)
    minus_dm = (prev_low - low).clip(lower=0)
    cond_plus = plus_dm > minus_dm
    cond_minus = minus_dm > plus_dm
    plus_dm_clean = np.where(cond_plus, plus_dm, 0.0)
    minus_dm_clean = np.where(cond_minus, minus_dm, 0.0)
    tr14 = tr.ewm(alpha=1.0/14.0, adjust=False).mean()
    plus_di = 100.0 * pd.Series(plus_dm_clean, index=df.index).ewm(alpha=1.0/14.0, adjust=False).mean() / (tr14 + 1e-9)
    minus_di = 100.0 * pd.Series(minus_dm_clean, index=df.index).ewm(alpha=1.0/14.0, adjust=False).mean() / (tr14 + 1e-9)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    df["adx"] = dx.ewm(alpha=1.0/14.0, adjust=False).mean()

    # Candle geometry
    bar_range = high - low
    bar_body = (close - open_).abs()
    df["body_ratio"] = bar_body / (bar_range + 1e-9)
    df["upper_wick"] = np.where(close >= open_, high - close, high - open_)
    df["lower_wick"] = np.where(close >= open_, open_ - low, close - low)
    df["upper_wick_ratio"] = df["upper_wick"] / (bar_range + 1e-9)
    df["lower_wick_ratio"] = df["lower_wick"] / (bar_range + 1e-9)

    return df

def run_pair_simulation(pair, df, tf="1H"):
    pip = 0.10 if pair == "XAUUSD" else 0.0001
    digits = 2 if pair == "XAUUSD" else 5
    donch_len = 20
    min_sl_dist = 15.0 * pip if pair == "XAUUSD" else 18.0 * pip
    max_sl_dist = 150.0 * pip if pair == "XAUUSD" else 65.0 * pip
    rr = 1.75

    df = compute_indicators(df, donch_len=donch_len)
    
    trades = []
    active_trade = None
    
    # We iterate bar by bar starting after warmup
    start_idx = 50
    n = len(df)

    for i in range(start_idx, n):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        t = row["time_dt"]

        # 1. Manage active trade if floating
        if active_trade is not None:
            is_long = active_trade["direction"] == "LONG"
            entry = active_trade["entry"]
            sl = active_trade["stop_loss"]
            tp = active_trade["take_profit"]
            sl_dist = active_trade["sl_dist"]
            be_active = active_trade["be_active"]
            h_open = active_trade["opened_at"]
            holding_hours = (t - h_open).total_seconds() / 3600.0

            # Update MFE / MAE
            if is_long:
                curr_mfe = max(active_trade["mfe_pips"], (row["high"] - entry) / pip)
                curr_mae = min(active_trade["mae_pips"], (row["low"] - entry) / pip)
            else:
                curr_mfe = max(active_trade["mfe_pips"], (entry - row["low"]) / pip)
                curr_mae = min(active_trade["mae_pips"], (entry - row["high"]) / pip)
            active_trade["mfe_pips"] = curr_mfe
            active_trade["mae_pips"] = curr_mae

            # Model H Break-Even Lock at +1.0R
            if not be_active:
                if is_long and (row["high"] - entry) >= sl_dist:
                    active_trade["stop_loss"] = entry + (1.0 * pip)
                    active_trade["be_active"] = True
                    sl = active_trade["stop_loss"]
                elif (not is_long) and (entry - row["low"]) >= sl_dist:
                    active_trade["stop_loss"] = entry - (1.0 * pip)
                    active_trade["be_active"] = True
                    sl = active_trade["stop_loss"]

            resolved = False
            exit_reason = None
            exit_price = None
            realized_pips = 0.0
            realized_r = 0.0

            if is_long:
                # Check SL hit
                if row["low"] <= sl:
                    resolved = True
                    exit_price = sl
                    exit_reason = "BREAKEVEN" if active_trade["be_active"] else "STOP_LOSS"
                # Check TP hit
                elif row["high"] >= tp:
                    resolved = True
                    exit_price = tp
                    exit_reason = "TAKE_PROFIT"
                # Check EMA20 Invalidation (>24h held & closes below EMA20)
                elif holding_hours >= 24.0 and row["close"] < row["ema20"]:
                    resolved = True
                    exit_price = row["close"]
                    exit_reason = "EMA20_INVALIDATION"
            else:
                # SHORT
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
                if is_long:
                    realized_pips = (exit_price - entry) / pip
                else:
                    realized_pips = (entry - exit_price) / pip

                initial_sl_pips = sl_dist / pip
                realized_r = realized_pips / (initial_sl_pips + 1e-9)
                outcome = "WIN" if realized_pips > 2.0 else ("LOSS" if realized_pips < -2.0 else "BREAKEVEN")

                record = {
                    **active_trade,
                    "closed_at": t,
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "outcome": outcome,
                    "realized_pips": round(realized_pips, 1),
                    "realized_r": round(realized_r, 2),
                    "holding_hours": round(holding_hours, 1),
                    "month_cohort": active_trade["opened_at"].strftime("%Y-%m")
                }
                trades.append(record)
                active_trade = None

        # 2. If no active trade, scan for entry on closed bar `row`
        if active_trade is None:
            # Weekend Guard
            if not is_forex_market_open(t):
                continue

            # London/NY Overlap Whipsaw Guard (12:00 - 16:00 UTC)
            if 12 <= t.hour < 16:
                continue

            # ADX Killing Zone (skip 20 to 30)
            adx_val = row["adx"]
            if 20.0 <= adx_val <= 30.0:
                continue

            # Candle Body Ratio Guard
            min_body = 0.60 if pair == "XAUUSD" else 0.55
            if tf == "15m" and row["body_ratio"] < min_body:
                continue

            # Donchian Breakout
            long_breakout = (row["close"] > row["donch_high"]) and (prev_row["close"] <= prev_row["donch_high"])
            short_breakout = (row["close"] < row["donch_low"]) and (prev_row["close"] >= prev_row["donch_low"])

            # Gold Rejection Wick Guard
            if pair == "XAUUSD":
                if long_breakout and row["upper_wick_ratio"] > 0.35:
                    continue
                if short_breakout and row["lower_wick_ratio"] > 0.35:
                    continue

            # Macro Trend Filter (EMA 20/50/200)
            bullish_trend = (row["close"] > row["ema50"]) and (row["ema20"] > row["ema50"]) and (row["ema20_slope"] > 0) and (row["close"] > row["ema200"])
            bearish_trend = (row["close"] < row["ema50"]) and (row["ema20"] < row["ema50"]) and (row["ema20_slope"] < 0) and (row["close"] < row["ema200"])

            # RSI Filter
            rsi_bullish = 40.0 <= row["rsi"] <= 80.0
            rsi_bearish = 20.0 <= row["rsi"] <= 60.0

            if long_breakout and bullish_trend and rsi_bullish:
                # Find origin OB
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
                    "timeframe": tf,
                    "opened_at": t,
                    "day_of_week": t.strftime("%A"),
                    "hour": t.hour,
                    "session": get_session(t),
                    "entry": round(entry, digits),
                    "stop_loss": round(stop_loss, digits),
                    "take_profit": round(take_profit, digits),
                    "sl_dist": sl_dist,
                    "sl_pips": round(sl_dist / pip, 1),
                    "tp_pips": round((rr * sl_dist) / pip, 1),
                    "rr": rr,
                    "be_active": False,
                    "mfe_pips": 0.0,
                    "mae_pips": 0.0,
                    "rsi_at_entry": round(row["rsi"], 1),
                    "adx_at_entry": round(row["adx"], 1),
                    "atr_at_entry": round(row["atr"], digits),
                    "body_ratio_at_entry": round(row["body_ratio"], 3),
                    "upper_wick_ratio": round(row["upper_wick_ratio"], 3),
                    "lower_wick_ratio": round(row["lower_wick_ratio"], 3)
                }

            elif short_breakout and bearish_trend and rsi_bearish:
                # Find origin OB
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
                    "timeframe": tf,
                    "opened_at": t,
                    "day_of_week": t.strftime("%A"),
                    "hour": t.hour,
                    "session": get_session(t),
                    "entry": round(entry, digits),
                    "stop_loss": round(stop_loss, digits),
                    "take_profit": round(take_profit, digits),
                    "sl_dist": sl_dist,
                    "sl_pips": round(sl_dist / pip, 1),
                    "tp_pips": round((rr * sl_dist) / pip, 1),
                    "rr": rr,
                    "be_active": False,
                    "mfe_pips": 0.0,
                    "mae_pips": 0.0,
                    "rsi_at_entry": round(row["rsi"], 1),
                    "adx_at_entry": round(row["adx"], 1),
                    "atr_at_entry": round(row["atr"], digits),
                    "body_ratio_at_entry": round(row["body_ratio"], 3),
                    "upper_wick_ratio": round(row["upper_wick_ratio"], 3),
                    "lower_wick_ratio": round(row["lower_wick_ratio"], 3)
                }

    return trades

def main():
    print("Loading 2-year multi-asset cache...")
    with open("archives/portfolio_8pairs_cache.pkl", "rb") as f:
        data_8pairs = pickle.load(f)

    # Let's inspect available pairs in Triad
    pairs = ["EURUSD", "USDCAD", "XAUUSD"]
    all_trades = []

    for p in pairs:
        df = data_8pairs[p].copy()
        if "time_dt" not in df.columns:
            df["time_dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
        else:
            df["time_dt"] = pd.to_datetime(df["time_dt"], utc=True)
        df = df.sort_values("time_dt").reset_index(drop=True)

        print(f"Running simulation for {p} 1H ({len(df)} bars, {df['time_dt'].min().strftime('%Y-%m')} to {df['time_dt'].max().strftime('%Y-%m')})...")
        p_trades = run_pair_simulation(p, df, tf="1H")
        print(f"  -> Generated {len(p_trades)} completed trades for {p}.")
        all_trades.extend(p_trades)

    df_trades = pd.DataFrame(all_trades)
    print(f"\nTotal Simulated Trades Across 2 Years: {len(df_trades)}")

    # Group by Month Cohort
    months = sorted(df_trades["month_cohort"].unique())
    print(f"Number of Monthly Cohorts: {len(months)} (from {months[0]} to {months[-1]})")

    monthly_summary = []
    for m in months:
        m_df = df_trades[df_trades["month_cohort"] == m]
        n_trades = len(m_df)
        wins = len(m_df[m_df["outcome"] == "WIN"])
        losses = len(m_df[m_df["outcome"] == "LOSS"])
        be = len(m_df[m_df["outcome"] == "BREAKEVEN"])
        wr = (wins / n_trades * 100.0) if n_trades > 0 else 0.0
        net_pips = m_df["realized_pips"].sum()
        net_r = m_df["realized_r"].sum()
        gross_win_r = m_df[m_df["realized_r"] > 0]["realized_r"].sum()
        gross_loss_r = abs(m_df[m_df["realized_r"] < 0]["realized_r"].sum())
        pf = (gross_win_r / gross_loss_r) if gross_loss_r > 0 else 99.0

        monthly_summary.append({
            "Month": m,
            "Trades": n_trades,
            "Wins": wins,
            "Losses": losses,
            "Breakeven": be,
            "WinRate%": round(wr, 1),
            "NetPips": round(net_pips, 1),
            "NetR": round(net_r, 2),
            "ProfitFactor": round(pf, 2)
        })

    df_monthly = pd.DataFrame(monthly_summary)
    print("\n--- MONTHLY PERFORMANCE SUMMARY (24 MONTHS) ---")
    print(df_monthly.to_string(index=False))

    # Overall Metrics
    total_trades = len(df_trades)
    total_wins = len(df_trades[df_trades["outcome"] == "WIN"])
    total_losses = len(df_trades[df_trades["outcome"] == "LOSS"])
    total_be = len(df_trades[df_trades["outcome"] == "BREAKEVEN"])
    global_wr = (total_wins / total_trades) * 100.0
    total_net_pips = df_trades["realized_pips"].sum()
    total_net_r = df_trades["realized_r"].sum()
    total_gross_win_r = df_trades[df_trades["realized_r"] > 0]["realized_r"].sum()
    total_gross_loss_r = abs(df_trades[df_trades["realized_r"] < 0]["realized_r"].sum())
    total_pf = total_gross_win_r / total_gross_loss_r if total_gross_loss_r > 0 else 99.0

    print(f"\n================ OVERALL 2-YEAR PORTFOLIO METRICS ================")
    print(f"Total Trades: {total_trades}")
    print(f"Wins: {total_wins} | Losses: {total_losses} | Breakevens: {total_be}")
    print(f"Global Win Rate: {global_wr:.1f}%")
    print(f"Net Realized Pips: {total_net_pips:.1f} pips")
    print(f"Net Realized R: {total_net_r:.2f} R")
    print(f"Profit Factor: {total_pf:.2f}")

    # PATTERN ANALYSIS: WINNING TRADES VS LOSING TRADES
    df_win = df_trades[df_trades["outcome"] == "WIN"]
    df_loss = df_trades[df_trades["outcome"] == "LOSS"]

    print("\n================ PATTERN ANALYSIS: WINNING TRADES ================")
    print(f"Number of Winning Trades: {len(df_win)}")
    print(f"Average Winner R: +{df_win['realized_r'].mean():.2f}R")
    print(f"Average Winner Pips: +{df_win['realized_pips'].mean():.1f} pips")
    print(f"Average Holding Time: {df_win['holding_hours'].mean():.1f} hours")
    print(f"Average Entry RSI: {df_win['rsi_at_entry'].mean():.1f}")
    print(f"Average Entry ADX: {df_win['adx_at_entry'].mean():.1f}")
    print(f"Average Body Ratio: {df_win['body_ratio_at_entry'].mean():.1%}")

    print("\n--- Win Rate by Session ---")
    session_grp = df_trades.groupby("session")["outcome"].value_counts().unstack().fillna(0)
    for sess in session_grp.index:
        w = session_grp.loc[sess].get("WIN", 0)
        l = session_grp.loc[sess].get("LOSS", 0)
        b = session_grp.loc[sess].get("BREAKEVEN", 0)
        tot = w + l + b
        wr_s = (w / tot * 100.0) if tot > 0 else 0
        r_sum = df_trades[df_trades["session"] == sess]["realized_r"].sum()
        print(f"  {sess:20s}: {tot:3.0f} trades | WR: {wr_s:5.1f}% | Net R: {r_sum:+6.2f}R | (W:{w:.0f} L:{l:.0f} BE:{b:.0f})")

    print("\n--- Win Rate by Day of Week ---")
    day_grp = df_trades.groupby("day_of_week")["outcome"].value_counts().unstack().fillna(0)
    days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Sunday"]
    for day in days_order:
        if day in day_grp.index:
            w = day_grp.loc[day].get("WIN", 0)
            l = day_grp.loc[day].get("LOSS", 0)
            b = day_grp.loc[day].get("BREAKEVEN", 0)
            tot = w + l + b
            wr_d = (w / tot * 100.0) if tot > 0 else 0
            r_sum = df_trades[df_trades["day_of_week"] == day]["realized_r"].sum()
            print(f"  {day:12s}: {tot:3.0f} trades | WR: {wr_d:5.1f}% | Net R: {r_sum:+6.2f}R | (W:{w:.0f} L:{l:.0f} BE:{b:.0f})")

    print("\n--- Win Rate by Pair ---")
    for p in pairs:
        p_df = df_trades[df_trades["pair"] == p]
        tot = len(p_df)
        w = len(p_df[p_df["outcome"] == "WIN"])
        l = len(p_df[p_df["outcome"] == "LOSS"])
        b = len(p_df[p_df["outcome"] == "BREAKEVEN"])
        wr_p = (w / tot * 100.0) if tot > 0 else 0
        r_sum = p_df["realized_r"].sum()
        pips_sum = p_df["realized_pips"].sum()
        print(f"  {p:10s}: {tot:3d} trades | WR: {wr_p:5.1f}% | Net R: {r_sum:+6.2f}R | Net Pips: {pips_sum:+8.1f}p | (W:{w} L:{l} BE:{b})")

    print("\n--- Win Rate by Direction ---")
    for d in ["LONG", "SHORT"]:
        d_df = df_trades[df_trades["direction"] == d]
        tot = len(d_df)
        w = len(d_df[d_df["outcome"] == "WIN"])
        l = len(d_df[d_df["outcome"] == "LOSS"])
        b = len(d_df[d_df["outcome"] == "BREAKEVEN"])
        wr_d = (w / tot * 100.0) if tot > 0 else 0
        r_sum = d_df["realized_r"].sum()
        print(f"  {d:10s}: {tot:3d} trades | WR: {wr_d:5.1f}% | Net R: {r_sum:+6.2f}R | (W:{w} L:{l} BE:{b})")

    print("\n--- Win Rate by ADX Regime at Entry ---")
    adx_bins = [(0, 20, "ADX < 20 (Low ADX / Choppy Compression)"),
                (30, 45, "ADX 30-45 (Strong Momentum Expansion)"),
                (45, 100, "ADX > 45 (Exhaustion / Hyper-Trend)")]
    for low_b, high_b, label in adx_bins:
        b_df = df_trades[(df_trades["adx_at_entry"] >= low_b) & (df_trades["adx_at_entry"] < high_b)]
        tot = len(b_df)
        if tot > 0:
            w = len(b_df[b_df["outcome"] == "WIN"])
            l = len(b_df[b_df["outcome"] == "LOSS"])
            b = len(b_df[b_df["outcome"] == "BREAKEVEN"])
            wr_b = (w / tot * 100.0)
            r_sum = b_df["realized_r"].sum()
            print(f"  {label:45s}: {tot:3d} trades | WR: {wr_b:5.1f}% | Net R: {r_sum:+6.2f}R")

    print("\n--- Win Rate by RSI Quartile at Entry ---")
    rsi_bins = [(20, 40, "RSI 20-40 (Deep Bearish Zone)"),
                (40, 50, "RSI 40-50 (Moderate Bearish/Neutral)"),
                (50, 60, "RSI 50-60 (Moderate Bullish/Neutral)"),
                (60, 80, "RSI 60-80 (Deep Bullish Zone)")]
    for low_b, high_b, label in rsi_bins:
        b_df = df_trades[(df_trades["rsi_at_entry"] >= low_b) & (df_trades["rsi_at_entry"] < high_b)]
        tot = len(b_df)
        if tot > 0:
            w = len(b_df[b_df["outcome"] == "WIN"])
            wr_b = (w / tot * 100.0)
            r_sum = b_df["realized_r"].sum()
            print(f"  {label:35s}: {tot:3d} trades | WR: {wr_b:5.1f}% | Net R: {r_sum:+6.2f}R")

    print("\n================ PATTERN ANALYSIS: LOSING TRADES ================")
    print(f"Number of Losing Trades: {len(df_loss)}")
    print(f"Average Loser R: {df_loss['realized_r'].mean():.2f}R")
    print(f"Average Loser Pips: {df_loss['realized_pips'].mean():.1f} pips")
    print(f"Average Holding Time: {df_loss['holding_hours'].mean():.1f} hours")
    print(f"Average Entry RSI: {df_loss['rsi_at_entry'].mean():.1f}")
    print(f"Average Entry ADX: {df_loss['adx_at_entry'].mean():.1f}")
    print(f"Average Body Ratio: {df_loss['body_ratio_at_entry'].mean():.1%}")

    print("\n--- Failure Exit Mode Distribution ---")
    exit_modes = df_loss["exit_reason"].value_counts()
    for mode, cnt in exit_modes.items():
        pct = (cnt / len(df_loss)) * 100.0
        avg_loss_r = df_loss[df_loss["exit_reason"] == mode]["realized_r"].mean()
        avg_loss_pips = df_loss[df_loss["exit_reason"] == mode]["realized_pips"].mean()
        print(f"  {mode:22s}: {cnt:3d} trades ({pct:5.1f}%) | Avg R: {avg_loss_r:+.2f}R | Avg Pips: {avg_loss_pips:+.1f}p")

    # MFE of Losing Trades: How far did losers run into profit before reversing?
    print("\n--- MFE (Max Favorable Excursion) Distribution of Losers ---")
    mfe_0 = len(df_loss[df_loss["mfe_pips"] < 5.0])
    mfe_small = len(df_loss[(df_loss["mfe_pips"] >= 5.0) & (df_loss["mfe_pips"] < 20.0)])
    mfe_large = len(df_loss[df_loss["mfe_pips"] >= 20.0])
    print(f"  Instant Reversals (MFE < 5 pips)     : {mfe_0:3d} ({mfe_0/len(df_loss)*100:.1f}%) -> Immediate false breakout / fakeout")
    print(f"  Moderate Move (5 <= MFE < 20 pips)   : {mfe_small:3d} ({mfe_small/len(df_loss)*100:.1f}%) -> Failed continuation")
    print(f"  Deep Runners (MFE >= 20 pips)        : {mfe_large:3d} ({mfe_large/len(df_loss)*100:.1f}%) -> Reversals that almost reached target")

    # Save output artifacts
    output_dir = "data/backtests"
    os.makedirs(output_dir, exist_ok=True)
    df_trades.to_json(os.path.join(output_dir, "2year_trades_full.json"), orient="records", indent=2, date_format="iso")
    df_monthly.to_json(os.path.join(output_dir, "2year_monthly_summary.json"), orient="records", indent=2)
    print(f"\nSaved trade ledger to {output_dir}/2year_trades_full.json and {output_dir}/2year_monthly_summary.json.")

if __name__ == "__main__":
    main()
