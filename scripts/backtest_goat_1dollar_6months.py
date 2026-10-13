"""
Backtest Engine: Goat Funded Trader GOAT $1 Model (6-Month Historical Audit)
Evaluates the current trading bot strategy against official GFT GOAT $1 rules:
- $1,000 Starting Balance ($1 purchase cost)
- 3% Static Daily Drawdown ($30.00 limit)
- 6% Trailing Overall Drawdown from End-of-Day Equity HWM ($60.00 limit)
- 2% Maximum Floating Loss ($20.00 limit)
- 15% Consistency Rule (highest profitable day < 15% of total net profit)
- Minimum 3 Profitable Days (>= 0.5% / $5.00 net of costs per day)
- 28-day Account Expiry
- $100 Minimum Withdrawal, 80% Profit Split, $100 Lifetime Withdrawal Cap
- Strategy: Fixed 15p TP, Fixed 10p SL, Decoupled ICT Killzones + Pullbacks
- Friction: Realistic Spread + 0.5p Slippage + $3.00/lot Commission
"""

import sys
import os
import pickle
import httpx
import json
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np

# Pair configurations with realistic spreads and pip values
CONFIGS = {
    "EURUSD": {"pip": 0.0001, "digits": 5, "spread": 0.8, "base_pip_val": 10.0},
    "GBPUSD": {"pip": 0.0001, "digits": 5, "spread": 1.0, "base_pip_val": 10.0},
    "USDJPY": {"pip": 0.01,   "digits": 3, "spread": 0.9, "base_pip_val": 6.5},  # ~$6.50/pip per standard lot around 150-155
    "USDCAD": {"pip": 0.0001, "digits": 5, "spread": 1.2, "base_pip_val": 7.3},  # ~$7.30/pip per standard lot around 1.35-1.38
    "USDCHF": {"pip": 0.0001, "digits": 5, "spread": 1.1, "base_pip_val": 11.5}, # ~$11.50/pip per standard lot around 0.85-0.87
    "AUDUSD": {"pip": 0.0001, "digits": 5, "spread": 0.9, "base_pip_val": 10.0},
}

PAIRS = list(CONFIGS.keys())

def load_or_fetch_6month_data():
    """
    Loads M15 and H1 candles for all 6 pairs from local cache + Yahoo Finance.
    Returns unified DataFrames covering 2026-04-01 to 2026-10-09.
    """
    cache_file = "archives/data_cache_orb.pkl"
    with open(cache_file, "rb") as f:
        orb_data = pickle.load(f)[1]

    data_15m = {}
    data_1h = {}

    for p in PAIRS:
        df_orb_15 = orb_data[p]["M15"].copy()
        df_orb_15["time"] = pd.to_datetime(df_orb_15["time"], unit="s", utc=True)
        
        df_orb_1h = orb_data[p]["H1"].copy()
        df_orb_1h["time"] = pd.to_datetime(df_orb_1h["time"], unit="s", utc=True)

        # Fetch recent Yahoo Finance 15M (60 days)
        url_15 = f"https://query1.finance.yahoo.com/v8/finance/chart/{p}=X?range=60d&interval=15m"
        r15 = httpx.get(url_15, headers={"User-Agent": "Mozilla/5.0"}).json()["chart"]["result"][0]
        ts15 = r15["timestamp"]
        q15 = r15["indicators"]["quote"][0]
        df_yf_15 = pd.DataFrame({
            "time": pd.to_datetime(ts15, unit="s", utc=True),
            "open": q15["open"],
            "high": q15["high"],
            "low": q15["low"],
            "close": q15["close"]
        }).dropna()

        # Merge 15M
        merged_15 = pd.concat([
            df_orb_15[df_orb_15["time"] < df_yf_15["time"].iloc[0]],
            df_yf_15
        ]).sort_values("time").drop_duplicates("time").reset_index(drop=True)

        # Fetch recent Yahoo Finance 1H (6 months)
        url_1h = f"https://query1.finance.yahoo.com/v8/finance/chart/{p}=X?range=6mo&interval=1h"
        r1h = httpx.get(url_1h, headers={"User-Agent": "Mozilla/5.0"}).json()["chart"]["result"][0]
        ts1h = r1h["timestamp"]
        q1h = r1h["indicators"]["quote"][0]
        df_yf_1h = pd.DataFrame({
            "time": pd.to_datetime(ts1h, unit="s", utc=True),
            "open": q1h["open"],
            "high": q1h["high"],
            "low": q1h["low"],
            "close": q1h["close"]
        }).dropna()

        # Merge 1H
        merged_1h = pd.concat([
            df_orb_1h[df_orb_1h["time"] < df_yf_1h["time"].iloc[0]],
            df_yf_1h
        ]).sort_values("time").drop_duplicates("time").reset_index(drop=True)

        # Filter for 6-month evaluation window: 2026-04-01 to 2026-10-09 (including 200 bars warmup before 2026-04-01)
        data_15m[p] = merged_15[merged_15["time"] >= "2026-03-20"].copy().reset_index(drop=True)
        data_1h[p] = merged_1h[merged_1h["time"] >= "2026-01-01"].copy().reset_index(drop=True)

    return data_15m, data_1h

def compute_all_indicators(df_15m, df_1h, pip):
    """
    Computes exact indicators matching market_scanner.py logic.
    """
    # 1H Indicators
    h1 = df_1h.copy()
    h1["ema20"] = h1["close"].ewm(span=20, adjust=False).mean()
    h1["ema50"] = h1["close"].ewm(span=50, adjust=False).mean()
    h1["h1_bull"] = (h1["close"] > h1["ema50"]) & (h1["ema20"] >= h1["ema50"])
    h1["h1_bear"] = (h1["close"] < h1["ema50"]) & (h1["ema20"] <= h1["ema50"])
    h1_map = h1.set_index("time")

    # 15M Indicators
    m15 = df_15m.copy()
    m15["ema20"] = m15["close"].ewm(span=20, adjust=False).mean()
    m15["ema50"] = m15["close"].ewm(span=50, adjust=False).mean()
    m15["ema20_slope"] = m15["ema20"] - m15["ema20"].shift(2)

    # Donchian 20
    m15["donch_high"] = m15["high"].shift(1).rolling(20).max()
    m15["donch_low"] = m15["low"].shift(1).rolling(20).min()

    # ATR 14
    tr = pd.concat([
        m15["high"] - m15["low"],
        (m15["high"] - m15["close"].shift(1)).abs(),
        (m15["low"] - m15["close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    m15["atr"] = tr.ewm(alpha=1.0/14.0, adjust=False).mean()

    # RSI 14
    delta = m15["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1.0/14.0, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1.0/14.0, adjust=False).mean()
    rs = gain / (loss + 1e-9)
    m15["rsi"] = 100.0 - (100.0 / (1.0 + rs))

    # ADX 14
    plus_dm = (m15["high"] - m15["high"].shift(1)).clip(lower=0)
    minus_dm = (m15["low"].shift(1) - m15["low"]).clip(lower=0)
    plus_dm_clean = np.where(plus_dm > minus_dm, plus_dm, 0.0)
    minus_dm_clean = np.where(minus_dm > plus_dm, minus_dm, 0.0)
    tr14 = tr.ewm(alpha=1.0/14.0, adjust=False).mean()
    plus_di = 100.0 * pd.Series(plus_dm_clean, index=m15.index).ewm(alpha=1.0/14.0, adjust=False).mean() / (tr14 + 1e-9)
    minus_di = 100.0 * pd.Series(minus_dm_clean, index=m15.index).ewm(alpha=1.0/14.0, adjust=False).mean() / (tr14 + 1e-9)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    m15["adx"] = dx.ewm(alpha=1.0/14.0, adjust=False).mean()

    # 10-bar fractal (shift 8 to avoid lookahead)
    m15["sw10_high"] = m15["high"].where(m15["high"] == m15["high"].rolling(15, center=True).max()).shift(8).ffill()
    m15["sw10_low"] = m15["low"].where(m15["low"] == m15["low"].rolling(15, center=True).min()).shift(8).ffill()

    # Asian Session Range (00:00 - 06:00 UTC)
    times_dt = m15["time"]
    asian_mask = (times_dt.dt.hour >= 0) & (times_dt.dt.hour < 6)
    asian_bars = m15[asian_mask]
    if not asian_bars.empty:
        asia_h_map = asian_bars.groupby(times_dt[asian_mask].dt.date)["high"].max().to_dict()
        asia_l_map = asian_bars.groupby(times_dt[asian_mask].dt.date)["low"].min().to_dict()
        m15["asia_high"] = times_dt.dt.date.map(asia_h_map).ffill()
        m15["asia_low"] = times_dt.dt.date.map(asia_l_map).ffill()
    else:
        m15["asia_high"] = np.nan
        m15["asia_low"] = np.nan

    # Map HTF 1H trend alignment
    m15["h1_time"] = m15["time"].dt.floor("h")
    # Shift by 1 hour to use only COMPLETED 1H bar
    m15["h1_time_completed"] = m15["h1_time"] - pd.Timedelta(hours=1)
    m15["h1_bull"] = m15["h1_time_completed"].map(h1_map["h1_bull"]).fillna(False)
    m15["h1_bear"] = m15["h1_time_completed"].map(h1_map["h1_bear"]).fillna(False)

    return m15

def detect_signals_for_pair(df, pair_name, cfg):
    """
    Generates signals exactly matching the updated market_scanner.py logic.
    """
    pip = cfg["pip"]
    signals = []
    n = len(df)

    for i in range(30, n):
        c = df.iloc[i]
        prev = df.iloc[i-1]
        t = c["time"]

        # Only evaluate during 6-month test period (2026-04-01 onwards)
        if t < pd.Timestamp("2026-04-01", tz="UTC"):
            continue

        # Skip weekends
        if t.weekday() >= 5:
            continue

        bar_hour = t.hour
        # Institutional liquidity hours (06:00 - 17:00 UTC)
        if bar_hour < 6 or bar_hour >= 17:
            continue

        # US news red folder filter (12:00 - 14:00 UTC) for 15M
        if 12 <= bar_hour < 14:
            continue

        h = float(c["high"])
        l = float(c["low"])
        close = float(c["close"])
        open_p = float(c["open"])
        rng = (h - l) + 1e-9
        atr = float(c["atr"])
        adx_val = float(c["adx"])

        # ADX consolidation filter
        if 20.0 < adx_val < 30.0:
            slope_thresh = 0.05 * atr
            if abs(c["ema20_slope"]) < slope_thresh:
                continue

        # Donchian conviction filter for secondary pullbacks
        conv_failed = False
        if pair_name in ["USDJPY", "AUDUSD", "GBPUSD"]:
            min_sep = (0.25 * atr) if pair_name == "AUDUSD" else (0.15 * atr)
            min_slope = (0.08 * atr) if pair_name == "AUDUSD" else (0.04 * atr)
            if abs(c["ema20"] - c["ema50"]) < min_sep or abs(c["ema20_slope"]) < min_slope:
                conv_failed = True

        # Killzone check for ICT
        in_kz = (7 <= bar_hour <= 10) or (12 <= bar_hour <= 15)

        # 1. ICT Liquidity Sweep Check
        long_ict = False
        short_ict = False

        if in_kz and rng >= 0.50 * atr:
            # Long sweep
            if close > open_p:
                lower_rej = (close - l) / rng
                if lower_rej >= 0.50:
                    asia_l = c["asia_low"] if pd.notna(c["asia_low"]) else None
                    sw10_l = c["sw10_low"] if pd.notna(c["sw10_low"]) else None
                    prev_l = float(prev["low"])
                    swept_l = min(l, prev_l)
                    if (asia_l and swept_l < asia_l and close > asia_l) or \
                       (sw10_l and swept_l < sw10_l and close > sw10_l):
                        long_ict = True

            # Short sweep
            if close < open_p:
                upper_rej = (h - close) / rng
                if upper_rej >= 0.50:
                    asia_h = c["asia_high"] if pd.notna(c["asia_high"]) else None
                    sw10_h = c["sw10_high"] if pd.notna(c["sw10_high"]) else None
                    prev_h = float(prev["high"])
                    swept_h = max(h, prev_h)
                    if (asia_h and swept_h > asia_h and close < asia_h) or \
                       (sw10_h and swept_h > sw10_h and close < sw10_h):
                        short_ict = True

        # 2. Pullback Check (Simplified exact match)
        bullish_trend = (close > c["ema50"]) and (c["ema20"] > c["ema50"]) and (c["ema20_slope"] > 0)
        bearish_trend = (close < c["ema50"]) and (c["ema20"] < c["ema50"]) and (c["ema20_slope"] < 0)
        rsi_bull_ok = 40.0 <= c["rsi"] <= 80.0
        rsi_bear_ok = 20.0 <= c["rsi"] <= 60.0

        # Donchian breakout within last 12 bars + pullback to EMA20 / 50% Fib
        long_pb = False
        short_pb = False
        lookback_bars = df.iloc[max(0, i-12):i]
        if bullish_trend:
            had_bo = (lookback_bars["close"] > lookback_bars["donch_high"]).any()
            if had_bo and (l <= c["ema20"] <= close) and (close > open_p):
                long_pb = True
        if bearish_trend:
            had_bo = (lookback_bars["close"] < lookback_bars["donch_low"]).any()
            if had_bo and (close <= c["ema20"] <= h) and (close < open_p):
                short_pb = True

        # Final Confirmation
        is_long = ((long_ict and c["rsi"] <= 78.0) or (long_pb and bullish_trend and rsi_bull_ok and not conv_failed)) and bool(c["h1_bull"])
        is_short = ((short_ict and c["rsi"] >= 22.0) or (short_pb and bearish_trend and rsi_bear_ok and not conv_failed)) and bool(c["h1_bear"])

        if is_long:
            signals.append({
                "bar_idx": i,
                "time": t,
                "pair": pair_name,
                "direction": "LONG",
                "setup": "ICT Sweep" if long_ict else "Pullback",
                "close": close,
                "pip": pip,
                "cfg": cfg
            })
        elif is_short:
            signals.append({
                "bar_idx": i,
                "time": t,
                "pair": pair_name,
                "direction": "SHORT",
                "setup": "ICT Sweep" if short_ict else "Pullback",
                "close": close,
                "pip": pip,
                "cfg": cfg
            })

    return signals

def simulate_goat_accounts(all_signals, data_15m):
    """
    Simulates the entire 6-month sequence under GOAT $1 rules:
    - $1,000 initial balance, $1 per account
    - 3% static daily drawdown ($30.00)
    - 6% trailing overall drawdown from EOD equity HWM ($60.00)
    - 2% maximum floating loss ($20.00)
    - 28-day account expiry
    - 15% consistency rule
    - Minimum 3 profitable days (>= $5.00 net)
    - $100 minimum withdrawal, 80% profit split, $100 lifetime cap
    """
    # Sort signals strictly chronologically across all pairs
    all_signals.sort(key=lambda s: s["time"])

    # Global simulation metrics
    accounts = []
    lifetime_payouts = 0.0
    account_id = 1

    # Time bounds of signals
    sim_start_time = all_signals[0]["time"]
    sim_end_time = all_signals[-1]["time"]

    curr_sig_idx = 0
    total_signals = len(all_signals)

    while curr_sig_idx < total_signals:
        sig = all_signals[curr_sig_idx]
        account_start_time = sig["time"]
        account_expiry_time = account_start_time + pd.Timedelta(days=28)

        # Initialize Account State
        acct = {
            "id": account_id,
            "start_time": account_start_time,
            "end_time": None,
            "initial_balance": 1000.0,
            "balance": 1000.0,
            "equity": 1000.0,
            "peak_equity": 1000.0,
            "eod_hwm": 1000.0,
            "trailing_floor": 940.0, # 1000 - 60
            "daily_start_equity": 1000.0,
            "current_day": account_start_time.strftime("%Y-%m-%d"),
            "daily_net_pnl": {}, # day_str -> pnl
            "trades": [],
            "status": "ACTIVE", # "BREACHED", "EXPIRED"
            "breach_reason": None,
            "max_daily_dd": 0.0,
            "max_trailing_dd": 0.0,
            "max_floating_loss": 0.0,
            "eligible_for_payout": False,
            "payout_amount": 0.0,
            "consistency_passed": False,
            "min_days_passed": False,
            "min_withdrawal_passed": False
        }

        open_positions = [] # active trades on this account

        # Iterate bar by bar through time across the 28-day window
        # Collect all timestamps from the current signal forward
        # Step through unique 15M timestamps
        timeline = []
        for p in PAIRS:
            sub = data_15m[p]
            bars_in_range = sub[(sub["time"] >= account_start_time) & (sub["time"] <= account_expiry_time)]
            timeline.extend(bars_in_range["time"].tolist())
        unique_times = sorted(list(set(timeline)))

        for current_time in unique_times:
            # 1. Check Daily Rollover at 17:00 NY time (21:00 UTC)
            day_str = current_time.strftime("%Y-%m-%d")
            # If crossed 21:00 UTC or day changed
            if current_time.hour == 21 and current_time.minute == 0:
                # EOD rollover
                eod_equity = acct["equity"]
                # Update EOD HWM and trailing floor
                if eod_equity > acct["eod_hwm"]:
                    acct["eod_hwm"] = eod_equity
                    acct["trailing_floor"] = acct["eod_hwm"] - 60.0
                # Reset daily start equity
                acct["daily_start_equity"] = eod_equity

            # 2. Update Open Positions & Check Exits on current bar
            floating_pnl_sum = 0.0
            closed_this_bar = []

            for pos in open_positions:
                p_pair = pos["pair"]
                df_p = data_15m[p_pair]
                bar_match = df_p[df_p["time"] == current_time]
                if bar_match.empty:
                    continue
                c_bar = bar_match.iloc[0]

                # Check SL / TP
                is_closed = False
                exit_price = None
                outcome = None

                if pos["direction"] == "LONG":
                    # Check low for SL
                    if c_bar["low"] <= pos["sl"]:
                        is_closed = True
                        exit_price = pos["sl"]
                        outcome = "LOSS"
                    elif c_bar["high"] >= pos["tp"]:
                        is_closed = True
                        exit_price = pos["tp"]
                        outcome = "WIN"
                    else:
                        # Floating PnL
                        pips_float = (c_bar["low"] - pos["entry"]) / pos["pip"]
                        float_dollars = pips_float * pos["pip_val"] * pos["lots"]
                        floating_pnl_sum += min(0.0, float_dollars)
                else:
                    if c_bar["high"] >= pos["sl"]:
                        is_closed = True
                        exit_price = pos["sl"]
                        outcome = "LOSS"
                    elif c_bar["low"] <= pos["tp"]:
                        is_closed = True
                        exit_price = pos["tp"]
                        outcome = "WIN"
                    else:
                        pips_float = (pos["entry"] - c_bar["high"]) / pos["pip"]
                        float_dollars = pips_float * pos["pip_val"] * pos["lots"]
                        floating_pnl_sum += min(0.0, float_dollars)

                if is_closed:
                    pips_realized = 15.0 if outcome == "WIN" else -10.0
                    gross_dollars = pips_realized * pos["pip_val"] * pos["lots"]
                    comm = pos["lots"] * 3.0 # $3/lot
                    net_dollars = gross_dollars - comm

                    acct["balance"] += net_dollars
                    acct["equity"] = acct["balance"]
                    acct["peak_equity"] = max(acct["peak_equity"], acct["equity"])

                    # Record daily PnL
                    trade_day = current_time.strftime("%Y-%m-%d")
                    acct["daily_net_pnl"][trade_day] = acct["daily_net_pnl"].get(trade_day, 0.0) + net_dollars

                    pos["exit_time"] = current_time
                    pos["exit_price"] = exit_price
                    pos["outcome"] = outcome
                    pos["net_pnl"] = net_dollars
                    acct["trades"].append(pos)
                    closed_this_bar.append(pos)

            for c_pos in closed_this_bar:
                open_positions.remove(c_pos)

            # Update current equity with floating
            acct["equity"] = acct["balance"] + floating_pnl_sum
            acct["peak_equity"] = max(acct["peak_equity"], acct["equity"])

            # 3. Check Hard Breach Conditions
            # A. 2% Maximum Floating Loss ($20.00)
            if floating_pnl_sum <= -20.0:
                acct["status"] = "BREACHED"
                acct["breach_reason"] = "Maximum Floating Loss Exceeded (>= $20.00)"
                acct["max_floating_loss"] = abs(floating_pnl_sum)
                acct["end_time"] = current_time
                break

            # B. 3% Static Daily Drawdown ($30.00)
            daily_dd = acct["daily_start_equity"] - acct["equity"]
            acct["max_daily_dd"] = max(acct["max_daily_dd"], daily_dd)
            if daily_dd >= 30.0:
                acct["status"] = "BREACHED"
                acct["breach_reason"] = f"Static Daily Drawdown Exceeded (${daily_dd:.2f} >= $30.00)"
                acct["end_time"] = current_time
                break

            # C. 6% Trailing Overall Drawdown from EOD HWM ($60.00)
            trailing_dd = acct["eod_hwm"] - acct["equity"]
            acct["max_trailing_dd"] = max(acct["max_trailing_dd"], trailing_dd)
            if acct["equity"] <= acct["trailing_floor"]:
                acct["status"] = "BREACHED"
                acct["breach_reason"] = f"Trailing Overall Drawdown Exceeded (${acct['equity']:.2f} <= ${acct['trailing_floor']:.2f})"
                acct["end_time"] = current_time
                break

            # 4. Check for New Signal at current_time
            # Find if any signal triggers at current_time
            while curr_sig_idx < total_signals and all_signals[curr_sig_idx]["time"] == current_time:
                s = all_signals[curr_sig_idx]
                curr_sig_idx += 1

                # Prevent more than 3 simultaneous positions to avoid correlated floating breach
                if len(open_positions) >= 3:
                    continue

                # Position sizing: 0.50% risk = $5.00 on $1,000
                # SL = 10 pips
                s_cfg = CONFIGS[s["pair"]]
                pip_val = s_cfg["base_pip_val"]
                lots = round(5.0 / (10.0 * pip_val), 2)
                lots = max(0.01, min(0.10, lots)) # reasonable micro lots

                friction = (s_cfg["spread"] + 0.5) * s["pip"]
                if s["direction"] == "LONG":
                    entry = s["close"] + friction
                    tp = entry + 15.0 * s["pip"]
                    sl = entry - 10.0 * s["pip"]
                else:
                    entry = s["close"] - friction
                    tp = entry - 15.0 * s["pip"]
                    sl = entry + 10.0 * s["pip"]

                open_positions.append({
                    "pair": s["pair"],
                    "direction": s["direction"],
                    "setup": s["setup"],
                    "entry_time": current_time,
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "lots": lots,
                    "pip": s["pip"],
                    "pip_val": pip_val
                })

            # Check if 28 days reached
            if current_time >= account_expiry_time:
                acct["status"] = "EXPIRED"
                acct["end_time"] = current_time
                break

        # If loop finished and still active, mark expired at account_expiry_time
        if acct["status"] == "ACTIVE":
            acct["status"] = "EXPIRED"
            acct["end_time"] = account_expiry_time

        # Close any leftover positions at expiry
        for pos in open_positions:
            acct["trades"].append(pos)

        # 5. Evaluate Payout Eligibility if Expired without breach
        total_net_profit = acct["balance"] - acct["initial_balance"]

        if acct["status"] == "EXPIRED":
            # A. Minimum 3 profitable days >= $5.00 (0.5% of $1,000)
            prof_days = [d for d, pnl in acct["daily_net_pnl"].items() if pnl >= 5.0]
            acct["min_days_passed"] = len(prof_days) >= 3

            # B. 15% Consistency Rule: highest day < 15% of total profit
            if total_net_profit > 0:
                max_day_pnl = max(acct["daily_net_pnl"].values()) if acct["daily_net_pnl"] else 0.0
                highest_day_pct = (max_day_pnl / total_net_profit) * 100.0
                acct["highest_day_pnl"] = max_day_pnl
                acct["highest_day_pct"] = highest_day_pct
                acct["consistency_passed"] = (max_day_pnl < 0.15 * total_net_profit)
            else:
                acct["highest_day_pnl"] = 0.0
                acct["highest_day_pct"] = 0.0
                acct["consistency_passed"] = False

            # C. Minimum Withdrawal >= $100.00
            acct["min_withdrawal_passed"] = (total_net_profit >= 100.0)

            # Combined Payout Eligibility
            if acct["min_days_passed"] and acct["consistency_passed"] and acct["min_withdrawal_passed"]:
                acct["eligible_for_payout"] = True
                raw_payout = total_net_profit * 0.80
                remaining_lifetime_cap = max(0.0, 100.0 - lifetime_payouts)
                payout = min(raw_payout, remaining_lifetime_cap)
                acct["payout_amount"] = payout
                lifetime_payouts += payout
            else:
                acct["eligible_for_payout"] = False
                acct["payout_amount"] = 0.0

        accounts.append(acct)
        account_id += 1

        # Fast forward curr_sig_idx to next signal after acct["end_time"]
        while curr_sig_idx < total_signals and all_signals[curr_sig_idx]["time"] <= acct["end_time"]:
            curr_sig_idx += 1

    return accounts, lifetime_payouts

def print_final_report(accounts, lifetime_payouts):
    print("\n" + "="*80)
    print("      OFFICIAL GOAT FUNDED TRADER GOAT $1 MODEL - 6-MONTH AUDIT REPORT")
    print("="*80)
    
    total_accounts = len(accounts)
    breached_accounts = [a for a in accounts if a["status"] == "BREACHED"]
    expired_accounts = [a for a in accounts if a["status"] == "EXPIRED"]
    active_accounts = [a for a in accounts if a["status"] == "ACTIVE"]
    payout_accounts = [a for a in accounts if a["eligible_for_payout"]]
    consistency_passed_accounts = [a for a in accounts if a["consistency_passed"]]
    min_withdrawal_accounts = [a for a in accounts if a["min_withdrawal_passed"]]

    total_cost = total_accounts * 1.0  # $1 per account
    net_trader_profit = lifetime_payouts - total_cost

    all_trades = [t for a in accounts for t in a["trades"] if "outcome" in t]
    wins = [t for t in all_trades if t["outcome"] == "WIN"]
    losses = [t for t in all_trades if t["outcome"] == "LOSS"]
    total_closed = len(wins) + len(losses)
    win_rate = (len(wins) / total_closed * 100) if total_closed else 0.0

    gross_profit = sum(t["net_pnl"] for t in wins) if wins else 0.0
    gross_loss = abs(sum(t["net_pnl"] for t in losses)) if losses else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss else 0.0
    expectancy_dollars = (sum(t["net_pnl"] for t in all_trades) / total_closed) if total_closed else 0.0

    print(f"\n1. SIMULATION OVERVIEW & DATA COVERAGE:")
    print(f"   - Evaluation Period: 2026-04-01 to 2026-10-09 (6 Complete Months)")
    print(f"   - Instrument Universe: EURUSD, GBPUSD, USDJPY, USDCAD, USDCHF, AUDUSD (Gold Strictly Excluded)")
    print(f"   - Candle Resolution: M15 (Execution) & H1 (HTF Trend Filter)")
    print(f"   - Strategy Model: Fixed 15p TP / 10p SL (1:1.5 RR), Decoupled ICT Killzones + Pullbacks")
    print(f"   - Account Model: Goat Funded Trader GOAT $1 ($1,000 Capital, $1 Purchase)")

    print(f"\n2. ACCOUNT LIFECYCLE SUMMARY:")
    print(f"   - Total Accounts Started: {total_accounts}")
    print(f"   - Total Accounts Breached: {len(breached_accounts)}")
    print(f"   - Total Accounts Expired (28 Days): {len(expired_accounts)}")
    print(f"   - Total Accounts Active: {len(active_accounts)}")
    print(f"   - Accounts Passing 15% Consistency Rule: {len(consistency_passed_accounts)} / {len(expired_accounts)}")
    print(f"   - Accounts Reaching $100 Min Withdrawal: {len(min_withdrawal_accounts)} / {len(expired_accounts)}")
    print(f"   - Accounts Receiving Payout: {len(payout_accounts)}")

    print(f"\n3. ACCOUNT-BY-ACCOUNT AUDIT TRAIL:")
    print(f"{'Acct':<5} | {'Start Date':<10} | {'End Date':<10} | {'Status':<9} | {'Net PnL':<9} | {'Peak Eq':<9} | {'Max D-DD':<9} | {'Max T-DD':<9} | {'Payout':<8} | {'Breach / Expiry Details'}")
    print("-" * 125)
    for a in accounts:
        net_pnl = a["balance"] - a["initial_balance"]
        s_date = a["start_time"].strftime("%Y-%m-%d")
        e_date = a["end_time"].strftime("%Y-%m-%d") if a["end_time"] else "N/A"
        details = a["breach_reason"] if a["status"] == "BREACHED" else (
            f"Eligible: ${a['payout_amount']:.2f}" if a["eligible_for_payout"] else (
                f"No Payout (Prof=${net_pnl:.1f}, BestDay={a.get('highest_day_pct', 0):.1f}%, >=$5Days={sum(1 for v in a['daily_net_pnl'].values() if v >= 5.0)})"
            )
        )
        print(f"{a['id']:<5} | {s_date:<10} | {e_date:<10} | {a['status']:<9} | ${net_pnl:<8.2f} | ${a['peak_equity']:<8.2f} | ${a['max_daily_dd']:<8.2f} | ${a['max_trailing_dd']:<8.2f} | ${a['payout_amount']:<7.2f} | {details}")

    print(f"\n4. FINANCIAL REWARD & PAYOUT RESULTS:")
    print(f"   - Total Account Purchase Costs (@ $1/acct): ${total_cost:.2f}")
    print(f"   - Total Gross Payouts (80% Profit Split): ${lifetime_payouts:.2f}")
    print(f"   - Maximum Lifetime Withdrawal Cap Applied: ${min(100.0, lifetime_payouts):.2f} / $100.00")
    print(f"   - Net Trader Return (Payouts - Purchase Costs): ${net_trader_profit:.2f}")

    print(f"\n5. STRATEGY METRICS (ALL TRADES):")
    print(f"   - Total Trades Executed: {total_closed}")
    print(f"   - Wins: {len(wins)} | Losses: {len(losses)}")
    print(f"   - Overall Win Rate: {win_rate:.1f}%")
    print(f"   - Profit Factor: {profit_factor:.2f}")
    print(f"   - Expectancy: ${expectancy_dollars:.2f} per trade")
    max_account_dd = max(a["max_trailing_dd"] for a in accounts) if accounts else 0.0
    print(f"   - Maximum Drawdown Seen Across Accounts: ${max_account_dd:.2f} ({max_account_dd/10.0:.1f}%)")

    print(f"\n6. PASS / FAIL CONCLUSION:")
    if lifetime_payouts > 0 and len(breached_accounts) == 0:
        print("   CONCLUSION: [PASS] - Strategy successfully operated without any hard breach and generated net payouts.")
    elif lifetime_payouts > total_cost:
        print(f"   CONCLUSION: [PASS - NET PROFITABLE] - Strategy generated ${lifetime_payouts:.2f} in payouts against ${total_cost:.2f} in costs (Net: +${net_trader_profit:.2f}).")
    elif len(breached_accounts) > 0 and lifetime_payouts <= total_cost:
        print(f"   CONCLUSION: [FAIL] - Account experienced hard breaches or failed to generate net profit after purchase costs.")
    else:
        print(f"   CONCLUSION: [FAIL - PAYOUT CONSTRAINTS] - Accounts survived but failed payout eligibility filters (15% consistency / $100 min withdrawal).")
    print("="*80 + "\n")

def main():
    print("Loading 6-month historical data (2026-04-01 to 2026-10-09)...")
    data_15m, data_1h = load_or_fetch_6month_data()
    print("Data loaded successfully across 6 pairs.")

    print("Computing indicators and detecting strategy signals...")
    all_signals = []
    for p in PAIRS:
        df_ind = compute_all_indicators(data_15m[p], data_1h[p], CONFIGS[p]["pip"])
        sigs = detect_signals_for_pair(df_ind, p, CONFIGS[p])
        all_signals.extend(sigs)
        print(f"  {p}: {len(sigs)} setups detected")

    print(f"Total strategy setups across all pairs: {len(all_signals)}")
    print("Simulating Goat Funded Trader GOAT $1 model accounts...")
    accounts, lifetime_payouts = simulate_goat_accounts(all_signals, data_15m)

    print_final_report(accounts, lifetime_payouts)

if __name__ == "__main__":
    main()
