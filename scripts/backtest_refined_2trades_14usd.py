"""
Backtest Engine: Goat Funded Trader GOAT $1 Model - Refined Rules Audit
Rules Tested:
1. Only 2 trades per day.
2. If any trade on the day achieves 14 USD, immediately close all trades and do not trade until the next day.
3. Official GOAT $1 Rules:
   - $1,000 Starting Balance ($1/account)
   - 3% Static Daily Drawdown ($30 limit)
   - 6% Trailing Overall Drawdown from EOD HWM ($60 limit)
   - 2% Maximum Floating Loss ($20 limit)
   - 15% Consistency Rule (highest profitable day < 15% of total net profit)
   - Minimum 3 Profitable Days (>= 0.5% / $5.00 net per day)
   - 28-day Account Expiry
   - $100 Minimum Withdrawal, 80% Profit Split, $100 Lifetime Cap

Evaluates:
- Mode 1: Native 0.50% Risk ($5 risk per trade, max 2 trades/day, $14 daily target lockout)
- Mode 2: 14 USD Target Sizing (0.93% risk where 15p TP = $14 USD, max 2 trades/day, lock out upon achieving $14 USD)
"""

import sys
import os
import pickle
import httpx
import json
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np

CONFIGS = {
    "EURUSD": {"pip": 0.0001, "digits": 5, "spread": 0.8, "base_pip_val": 10.0},
    "GBPUSD": {"pip": 0.0001, "digits": 5, "spread": 1.0, "base_pip_val": 10.0},
    "USDJPY": {"pip": 0.01,   "digits": 3, "spread": 0.9, "base_pip_val": 6.5},
    "USDCAD": {"pip": 0.0001, "digits": 5, "spread": 1.2, "base_pip_val": 7.3},
    "USDCHF": {"pip": 0.0001, "digits": 5, "spread": 1.1, "base_pip_val": 11.5},
    "AUDUSD": {"pip": 0.0001, "digits": 5, "spread": 0.9, "base_pip_val": 10.0},
}

PAIRS = list(CONFIGS.keys())

def load_data():
    with open("archives/data_cache_orb.pkl", "rb") as f:
        orb_data = pickle.load(f)[1]

    data_15m = {}
    data_1h = {}

    for p in PAIRS:
        df_orb_15 = orb_data[p]["M15"].copy()
        df_orb_15["time"] = pd.to_datetime(df_orb_15["time"], unit="s", utc=True)
        df_orb_1h = orb_data[p]["H1"].copy()
        df_orb_1h["time"] = pd.to_datetime(df_orb_1h["time"], unit="s", utc=True)

        url_15 = f"https://query1.finance.yahoo.com/v8/finance/chart/{p}=X?range=60d&interval=15m"
        r15 = httpx.get(url_15, headers={"User-Agent": "Mozilla/5.0"}).json()["chart"]["result"][0]
        df_yf_15 = pd.DataFrame({
            "time": pd.to_datetime(r15["timestamp"], unit="s", utc=True),
            "open": r15["indicators"]["quote"][0]["open"],
            "high": r15["indicators"]["quote"][0]["high"],
            "low": r15["indicators"]["quote"][0]["low"],
            "close": r15["indicators"]["quote"][0]["close"]
        }).dropna()

        merged_15 = pd.concat([
            df_orb_15[df_orb_15["time"] < df_yf_15["time"].iloc[0]],
            df_yf_15
        ]).sort_values("time").drop_duplicates("time").reset_index(drop=True)

        url_1h = f"https://query1.finance.yahoo.com/v8/finance/chart/{p}=X?range=6mo&interval=1h"
        r1h = httpx.get(url_1h, headers={"User-Agent": "Mozilla/5.0"}).json()["chart"]["result"][0]
        df_yf_1h = pd.DataFrame({
            "time": pd.to_datetime(r1h["timestamp"], unit="s", utc=True),
            "open": r1h["indicators"]["quote"][0]["open"],
            "high": r1h["indicators"]["quote"][0]["high"],
            "low": r1h["indicators"]["quote"][0]["low"],
            "close": r1h["indicators"]["quote"][0]["close"]
        }).dropna()

        merged_1h = pd.concat([
            df_orb_1h[df_orb_1h["time"] < df_yf_1h["time"].iloc[0]],
            df_yf_1h
        ]).sort_values("time").drop_duplicates("time").reset_index(drop=True)

        data_15m[p] = merged_15[merged_15["time"] >= "2026-03-20"].copy().reset_index(drop=True)
        data_1h[p] = merged_1h[merged_1h["time"] >= "2026-01-01"].copy().reset_index(drop=True)

    return data_15m, data_1h

def compute_indicators(data_15m, data_1h):
    computed = {}
    for p in PAIRS:
        pip = CONFIGS[p]["pip"]
        h1 = data_1h[p].copy()
        h1["ema20"] = h1["close"].ewm(span=20, adjust=False).mean()
        h1["ema50"] = h1["close"].ewm(span=50, adjust=False).mean()
        h1["h1_bull"] = (h1["close"] > h1["ema50"]) & (h1["ema20"] >= h1["ema50"])
        h1["h1_bear"] = (h1["close"] < h1["ema50"]) & (h1["ema20"] <= h1["ema50"])
        h1_map = h1.set_index("time")

        m15 = data_15m[p].copy()
        m15["ema20"] = m15["close"].ewm(span=20, adjust=False).mean()
        m15["ema50"] = m15["close"].ewm(span=50, adjust=False).mean()
        m15["ema20_slope"] = m15["ema20"] - m15["ema20"].shift(2)

        m15["donch_high"] = m15["high"].shift(1).rolling(20).max()
        m15["donch_low"] = m15["low"].shift(1).rolling(20).min()

        tr = pd.concat([
            m15["high"] - m15["low"],
            (m15["high"] - m15["close"].shift(1)).abs(),
            (m15["low"] - m15["close"].shift(1)).abs()
        ], axis=1).max(axis=1)
        m15["atr"] = tr.ewm(alpha=1.0/14.0, adjust=False).mean()

        delta = m15["close"].diff()
        gain = delta.clip(lower=0).ewm(alpha=1.0/14.0, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1.0/14.0, adjust=False).mean()
        m15["rsi"] = 100.0 - (100.0 / (1.0 + (gain / (loss + 1e-9))))

        plus_dm = (m15["high"] - m15["high"].shift(1)).clip(lower=0)
        minus_dm = (m15["low"].shift(1) - m15["low"]).clip(lower=0)
        plus_dm_clean = np.where(plus_dm > minus_dm, plus_dm, 0.0)
        minus_dm_clean = np.where(minus_dm > plus_dm, minus_dm, 0.0)
        tr14 = tr.ewm(alpha=1.0/14.0, adjust=False).mean()
        plus_di = 100.0 * pd.Series(plus_dm_clean, index=m15.index).ewm(alpha=1.0/14.0, adjust=False).mean() / (tr14 + 1e-9)
        minus_di = 100.0 * pd.Series(minus_dm_clean, index=m15.index).ewm(alpha=1.0/14.0, adjust=False).mean() / (tr14 + 1e-9)
        dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
        m15["adx"] = dx.ewm(alpha=1.0/14.0, adjust=False).mean()

        m15["sw10_high"] = m15["high"].where(m15["high"] == m15["high"].rolling(15, center=True).max()).shift(8).ffill()
        m15["sw10_low"] = m15["low"].where(m15["low"] == m15["low"].rolling(15, center=True).min()).shift(8).ffill()

        times_dt = m15["time"]
        asian_mask = (times_dt.dt.hour >= 0) & (times_dt.dt.hour < 6)
        asian_bars = m15[asian_mask]
        if not asian_bars.empty:
            m15["asia_high"] = times_dt.dt.date.map(asian_bars.groupby(times_dt[asian_mask].dt.date)["high"].max().to_dict()).ffill()
            m15["asia_low"] = times_dt.dt.date.map(asian_bars.groupby(times_dt[asian_mask].dt.date)["low"].min().to_dict()).ffill()
        else:
            m15["asia_high"] = np.nan
            m15["asia_low"] = np.nan

        m15["h1_time"] = m15["time"].dt.floor("h") - pd.Timedelta(hours=1)
        m15["h1_bull"] = m15["h1_time"].map(h1_map["h1_bull"]).fillna(False)
        m15["h1_bear"] = m15["h1_time"].map(h1_map["h1_bear"]).fillna(False)

        computed[p] = m15
    return computed

def extract_signals(data_dict):
    signals = []
    for p in PAIRS:
        df = data_dict[p]
        cfg = CONFIGS[p]
        pip = cfg["pip"]
        n = len(df)
        for i in range(30, n):
            c = df.iloc[i]
            prev = df.iloc[i-1]
            t = c["time"]
            if t < pd.Timestamp("2026-04-01", tz="UTC") or t.weekday() >= 5:
                continue
            bar_hour = t.hour
            if bar_hour < 6 or bar_hour >= 17 or (12 <= bar_hour < 14):
                continue

            h, l, close, open_p = float(c["high"]), float(c["low"]), float(c["close"]), float(c["open"])
            rng = (h - l) + 1e-9
            atr = float(c["atr"])
            adx_val = float(c["adx"])

            if 20.0 < adx_val < 30.0 and abs(c["ema20_slope"]) < (0.05 * atr):
                continue

            conv_failed = False
            if p in ["USDJPY", "AUDUSD", "GBPUSD"]:
                min_sep = (0.25 * atr) if p == "AUDUSD" else (0.15 * atr)
                min_slope = (0.08 * atr) if p == "AUDUSD" else (0.04 * atr)
                if abs(c["ema20"] - c["ema50"]) < min_sep or abs(c["ema20_slope"]) < min_slope:
                    conv_failed = True

            in_kz = (7 <= bar_hour <= 10) or (12 <= bar_hour <= 15)
            long_ict = False
            short_ict = False
            if in_kz and rng >= 0.50 * atr:
                if close > open_p and ((close - l) / rng >= 0.50):
                    asia_l = c["asia_low"] if pd.notna(c["asia_low"]) else None
                    sw10_l = c["sw10_low"] if pd.notna(c["sw10_low"]) else None
                    swept_l = min(l, float(prev["low"]))
                    if (asia_l and swept_l < asia_l and close > asia_l) or (sw10_l and swept_l < sw10_l and close > sw10_l):
                        long_ict = True
                if close < open_p and ((h - close) / rng >= 0.50):
                    asia_h = c["asia_high"] if pd.notna(c["asia_high"]) else None
                    sw10_h = c["sw10_high"] if pd.notna(c["sw10_high"]) else None
                    swept_h = max(h, float(prev["high"]))
                    if (asia_h and swept_h > asia_h and close < asia_h) or (sw10_h and swept_h > sw10_h and close < sw10_h):
                        short_ict = True

            bullish_trend = (close > c["ema50"]) and (c["ema20"] > c["ema50"]) and (c["ema20_slope"] > 0)
            bearish_trend = (close < c["ema50"]) and (c["ema20"] < c["ema50"]) and (c["ema20_slope"] < 0)
            long_pb = False
            short_pb = False
            lookback = df.iloc[max(0, i-12):i]
            if bullish_trend and (lookback["close"] > lookback["donch_high"]).any() and (l <= c["ema20"] <= close) and (close > open_p):
                long_pb = True
            if bearish_trend and (lookback["close"] < lookback["donch_low"]).any() and (close <= c["ema20"] <= h) and (close < open_p):
                short_pb = True

            is_long = ((long_ict and c["rsi"] <= 78.0) or (long_pb and bullish_trend and 40 <= c["rsi"] <= 80 and not conv_failed)) and bool(c["h1_bull"])
            is_short = ((short_ict and c["rsi"] >= 22.0) or (short_pb and bearish_trend and 20 <= c["rsi"] <= 60 and not conv_failed)) and bool(c["h1_bear"])

            if is_long:
                signals.append({"time": t, "pair": p, "direction": "LONG", "close": close, "pip": pip, "cfg": cfg})
            elif is_short:
                signals.append({"time": t, "pair": p, "direction": "SHORT", "close": close, "pip": pip, "cfg": cfg})
    signals.sort(key=lambda s: s["time"])
    return signals

def run_simulation(signals, data_15m, target_14_dollars=True):
    """
    Simulates accounts under:
    - Max 2 trades per trading day (21:00 UTC rollover).
    - If any trade (or day) reaches $14 USD profit, immediately close all open trades and stop trading for the day.
    """
    accounts = []
    lifetime_payouts = 0.0
    account_id = 1
    curr_sig_idx = 0
    total_signals = len(signals)

    while curr_sig_idx < total_signals:
        sig = signals[curr_sig_idx]
        account_start_time = sig["time"]
        account_expiry_time = account_start_time + pd.Timedelta(days=28)

        acct = {
            "id": account_id,
            "start_time": account_start_time,
            "end_time": None,
            "initial_balance": 1000.0,
            "balance": 1000.0,
            "equity": 1000.0,
            "peak_equity": 1000.0,
            "eod_hwm": 1000.0,
            "trailing_floor": 940.0,
            "daily_start_equity": 1000.0,
            "daily_net_pnl": {},
            "trades": [],
            "status": "ACTIVE",
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

        open_positions = []
        timeline = []
        for p in PAIRS:
            sub = data_15m[p]
            bars_in_range = sub[(sub["time"] >= account_start_time) & (sub["time"] <= account_expiry_time)]
            timeline.extend(bars_in_range["time"].tolist())
        unique_times = sorted(list(set(timeline)))

        current_trading_day = None
        daily_trades_taken = 0
        day_locked_out = False

        for current_time in unique_times:
            # 1. Trading Day Boundary: 21:00 UTC (17:00 NY)
            # Determine trading day string (date of trading session)
            # Before 21:00 UTC belongs to current day, after 21:00 belongs to next calendar trading day
            ny_trading_day = (current_time + pd.Timedelta(hours=3)).strftime("%Y-%m-%d")

            if ny_trading_day != current_trading_day:
                # EOD rollover
                if current_trading_day is not None:
                    eod_equity = acct["equity"]
                    if eod_equity > acct["eod_hwm"]:
                        acct["eod_hwm"] = eod_equity
                        acct["trailing_floor"] = acct["eod_hwm"] - 60.0
                    acct["daily_start_equity"] = eod_equity

                current_trading_day = ny_trading_day
                daily_trades_taken = 0
                day_locked_out = False

            # 2. Check Open Positions on current bar
            floating_pnl_sum = 0.0
            closed_this_bar = []
            hit_14_target_this_bar = False

            for pos in open_positions:
                df_p = data_15m[pos["pair"]]
                match = df_p[df_p["time"] == current_time]
                if match.empty:
                    continue
                c_bar = match.iloc[0]

                # Check SL / TP
                is_closed = False
                exit_price = None
                outcome = None

                if pos["direction"] == "LONG":
                    # Check if floating profit reached $14 USD at high
                    float_high_pips = (c_bar["high"] - pos["entry"]) / pos["pip"]
                    float_high_dollars = float_high_pips * pos["pip_val"] * pos["lots"] - (pos["lots"] * 3.0)
                    if float_high_dollars >= 14.0:
                        is_closed = True
                        outcome = "WIN"
                        exit_price = pos["entry"] + (14.0 / (pos["pip_val"] * pos["lots"])) * pos["pip"]
                        hit_14_target_this_bar = True
                    elif c_bar["low"] <= pos["sl"]:
                        is_closed = True
                        outcome = "LOSS"
                        exit_price = pos["sl"]
                    elif c_bar["high"] >= pos["tp"]:
                        is_closed = True
                        outcome = "WIN"
                        exit_price = pos["tp"]
                    else:
                        pips_float = (c_bar["low"] - pos["entry"]) / pos["pip"]
                        floating_pnl_sum += min(0.0, pips_float * pos["pip_val"] * pos["lots"])
                else:
                    float_low_pips = (pos["entry"] - c_bar["low"]) / pos["pip"]
                    float_low_dollars = float_low_pips * pos["pip_val"] * pos["lots"] - (pos["lots"] * 3.0)
                    if float_low_dollars >= 14.0:
                        is_closed = True
                        outcome = "WIN"
                        exit_price = pos["entry"] - (14.0 / (pos["pip_val"] * pos["lots"])) * pos["pip"]
                        hit_14_target_this_bar = True
                    elif c_bar["high"] >= pos["sl"]:
                        is_closed = True
                        outcome = "LOSS"
                        exit_price = pos["sl"]
                    elif c_bar["low"] <= pos["tp"]:
                        is_closed = True
                        outcome = "WIN"
                        exit_price = pos["tp"]
                    else:
                        pips_float = (pos["entry"] - c_bar["high"]) / pos["pip"]
                        floating_pnl_sum += min(0.0, pips_float * pos["pip_val"] * pos["lots"])

                if is_closed:
                    if outcome == "WIN" and hit_14_target_this_bar:
                        net_dollars = 14.0
                    elif outcome == "WIN":
                        net_dollars = 15.0 * pos["pip_val"] * pos["lots"] - (pos["lots"] * 3.0)
                    else:
                        net_dollars = -10.0 * pos["pip_val"] * pos["lots"] - (pos["lots"] * 3.0)

                    acct["balance"] += net_dollars
                    acct["equity"] = acct["balance"]
                    acct["peak_equity"] = max(acct["peak_equity"], acct["equity"])

                    acct["daily_net_pnl"][current_trading_day] = acct["daily_net_pnl"].get(current_trading_day, 0.0) + net_dollars
                    pos["exit_time"] = current_time
                    pos["exit_price"] = exit_price
                    pos["outcome"] = outcome
                    pos["net_pnl"] = net_dollars
                    acct["trades"].append(pos)
                    closed_this_bar.append(pos)

            for c_pos in closed_this_bar:
                open_positions.remove(c_pos)

            # RULE: If any trade on the day achieves 14 USD, immediately close all open trades and lockout
            today_profit = acct["daily_net_pnl"].get(current_trading_day, 0.0)
            if hit_14_target_this_bar or today_profit >= 14.0:
                day_locked_out = True
                # Close any remaining open positions immediately at bar close
                for rem_pos in list(open_positions):
                    df_p = data_15m[rem_pos["pair"]]
                    c_bar = df_p[df_p["time"] == current_time].iloc[0]
                    pips = (c_bar["close"] - rem_pos["entry"]) / rem_pos["pip"] if rem_pos["direction"] == "LONG" else (rem_pos["entry"] - c_bar["close"]) / rem_pos["pip"]
                    net_d = pips * rem_pos["pip_val"] * rem_pos["lots"] - (rem_pos["lots"] * 3.0)
                    acct["balance"] += net_d
                    acct["equity"] = acct["balance"]
                    acct["daily_net_pnl"][current_trading_day] = acct["daily_net_pnl"].get(current_trading_day, 0.0) + net_d
                    rem_pos["exit_time"] = current_time
                    rem_pos["exit_price"] = c_bar["close"]
                    rem_pos["outcome"] = "WIN" if net_d > 0 else "LOSS"
                    rem_pos["net_pnl"] = net_d
                    acct["trades"].append(rem_pos)
                    open_positions.remove(rem_pos)

            # Update equity
            acct["equity"] = acct["balance"] + floating_pnl_sum
            acct["peak_equity"] = max(acct["peak_equity"], acct["equity"])

            # 3. Check Hard Breaches
            # A. 2% Floating Loss ($20)
            if floating_pnl_sum <= -20.0:
                acct["status"] = "BREACHED"
                acct["breach_reason"] = "Maximum Floating Loss Exceeded (>= $20.00)"
                acct["end_time"] = current_time
                break

            # B. 3% Static Daily Drawdown ($30)
            daily_dd = acct["daily_start_equity"] - acct["equity"]
            acct["max_daily_dd"] = max(acct["max_daily_dd"], daily_dd)
            if daily_dd >= 30.0:
                acct["status"] = "BREACHED"
                acct["breach_reason"] = f"Static Daily Drawdown Exceeded (${daily_dd:.2f} >= $30.00)"
                acct["end_time"] = current_time
                break

            # C. 6% Trailing Overall Drawdown ($60)
            trailing_dd = acct["eod_hwm"] - acct["equity"]
            acct["max_trailing_dd"] = max(acct["max_trailing_dd"], trailing_dd)
            if acct["equity"] <= acct["trailing_floor"]:
                acct["status"] = "BREACHED"
                acct["breach_reason"] = f"Trailing Overall Drawdown Exceeded (${acct['equity']:.2f} <= ${acct['trailing_floor']:.2f})"
                acct["end_time"] = current_time
                break

            # 4. Check New Signals at current_time (Strict: Max 2 trades per day & not locked out)
            while curr_sig_idx < total_signals and signals[curr_sig_idx]["time"] == current_time:
                s = signals[curr_sig_idx]
                curr_sig_idx += 1

                # If day locked out or already 2 trades taken today, SKIP!
                if day_locked_out or daily_trades_taken >= 2:
                    continue

                if len(open_positions) >= 2:
                    continue

                # Position sizing
                s_cfg = CONFIGS[s["pair"]]
                pip_val = s_cfg["base_pip_val"]

                if target_14_dollars:
                    # 14 USD Target Sizing: 15 pips TP yields ~$14.00 net
                    # 15 * pip_val * lots = 14.30 (approx 0.095 lots for $10 pip_val)
                    lots = round(14.30 / (15.0 * pip_val), 2)
                    lots = max(0.02, min(0.12, lots))
                else:
                    # Native 0.50% risk ($5 risk on 10 pips = 0.05 lots)
                    lots = round(5.0 / (10.0 * pip_val), 2)
                    lots = max(0.01, min(0.10, lots))

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
                    "entry_time": current_time,
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "lots": lots,
                    "pip": s["pip"],
                    "pip_val": pip_val
                })
                daily_trades_taken += 1

            if current_time >= account_expiry_time:
                acct["status"] = "EXPIRED"
                acct["end_time"] = current_time
                break

        if acct["status"] == "ACTIVE":
            acct["status"] = "EXPIRED"
            acct["end_time"] = account_expiry_time

        # Payout Evaluation
        total_net_profit = acct["balance"] - acct["initial_balance"]
        if acct["status"] == "EXPIRED":
            prof_days = [d for d, pnl in acct["daily_net_pnl"].items() if pnl >= 5.0]
            acct["min_days_passed"] = len(prof_days) >= 3

            if total_net_profit > 0:
                max_day_pnl = max(acct["daily_net_pnl"].values()) if acct["daily_net_pnl"] else 0.0
                acct["highest_day_pnl"] = max_day_pnl
                acct["highest_day_pct"] = (max_day_pnl / total_net_profit) * 100.0
                acct["consistency_passed"] = (max_day_pnl < 0.15 * total_net_profit)
            else:
                acct["highest_day_pnl"] = 0.0
                acct["highest_day_pct"] = 0.0
                acct["consistency_passed"] = False

            acct["min_withdrawal_passed"] = (total_net_profit >= 100.0)

            if acct["min_days_passed"] and acct["consistency_passed"] and acct["min_withdrawal_passed"]:
                acct["eligible_for_payout"] = True
                payout = min(total_net_profit * 0.80, max(0.0, 100.0 - lifetime_payouts))
                acct["payout_amount"] = payout
                lifetime_payouts += payout

        accounts.append(acct)
        account_id += 1

        while curr_sig_idx < total_signals and signals[curr_sig_idx]["time"] <= acct["end_time"]:
            curr_sig_idx += 1

    return accounts, lifetime_payouts

def print_audit(accounts, lifetime_payouts, title):
    print("\n" + "="*85)
    print(f"   {title}")
    print("="*85)

    tot = len(accounts)
    breached = [a for a in accounts if a["status"] == "BREACHED"]
    expired = [a for a in accounts if a["status"] == "EXPIRED"]
    payout_accts = [a for a in accounts if a["eligible_for_payout"]]
    consist_pass = [a for a in accounts if a["consistency_passed"]]
    min_w_pass = [a for a in accounts if a["min_withdrawal_passed"]]

    cost = tot * 1.0
    net_profit = lifetime_payouts - cost

    all_t = [t for a in accounts for t in a["trades"] if "outcome" in t]
    wins = [t for t in all_t if t["outcome"] == "WIN"]
    losses = [t for t in all_t if t["outcome"] == "LOSS"]
    wr = (len(wins) / len(all_t) * 100) if all_t else 0.0
    gp = sum(t["net_pnl"] for t in wins) if wins else 0.0
    gl = abs(sum(t["net_pnl"] for t in losses)) if losses else 0.0
    pf = (gp / gl) if gl else 0.0
    exp = (sum(t["net_pnl"] for t in all_t) / len(all_t)) if all_t else 0.0

    print(f"\n1. SUMMARY & LIFECYCLE:")
    print(f"   - Accounts Started: {tot} | Breached: {len(breached)} | Expired (28 Days): {len(expired)}")
    print(f"   - Accounts Meeting 15% Consistency Rule: {len(consist_pass)} / {len(expired)}")
    print(f"   - Accounts Reaching $100 Min Withdrawal: {len(min_w_pass)} / {len(expired)}")
    print(f"   - Accounts Receiving Payout: {len(payout_accts)}")
    print(f"   - Total Account Fees: ${cost:.2f} | Total Payouts: ${lifetime_payouts:.2f} | Net Trader Result: ${net_profit:+.2f}")

    print(f"\n2. ACCOUNT-BY-ACCOUNT AUDIT TRAIL:")
    print(f"{'Acct':<5} | {'Start Date':<10} | {'End Date':<10} | {'Status':<9} | {'Net PnL':<9} | {'Peak Eq':<9} | {'Max D-DD':<9} | {'Max T-DD':<9} | {'Payout':<8} | Details")
    print("-" * 125)
    for a in accounts:
        net = a["balance"] - a["initial_balance"]
        s_d = a["start_time"].strftime("%Y-%m-%d")
        e_d = a["end_time"].strftime("%Y-%m-%d") if a["end_time"] else "N/A"
        if a["status"] == "BREACHED":
            det = a["breach_reason"]
        elif a["eligible_for_payout"]:
            det = f"PAID ${a['payout_amount']:.2f} (80% split)"
        else:
            best_pct = a.get("highest_day_pct", 0.0)
            pdays = sum(1 for v in a["daily_net_pnl"].values() if v >= 5.0)
            det = f"No Payout (Prof=${net:.1f}, BestDay={best_pct:.1f}%, >=$5Days={pdays})"
        print(f"{a['id']:<5} | {s_d:<10} | {e_d:<10} | {a['status']:<9} | ${net:<8.2f} | ${a['peak_equity']:<8.2f} | ${a['max_daily_dd']:<8.2f} | ${a['max_trailing_dd']:<8.2f} | ${a['payout_amount']:<7.2f} | {det}")

    print(f"\n3. STRATEGY EXECUTION PERFORMANCE:")
    print(f"   - Total Trades: {len(all_t)} (Wins: {len(wins)}, Losses: {len(losses)})")
    print(f"   - Win Rate: {wr:.1f}% | Profit Factor: {pf:.2f} | Expectancy: ${exp:.2f}/trade")

    if lifetime_payouts > cost:
        print(f"\nCONCLUSION: [PASS - NET PROFITABLE] Total payouts of ${lifetime_payouts:.2f} exceeded purchase costs of ${cost:.2f} (Net: +${net_profit:.2f})")
    else:
        print(f"\nCONCLUSION: [FAIL] Payouts (${lifetime_payouts:.2f}) did not exceed purchase costs (${cost:.2f}).")
    print("="*85 + "\n")

def main():
    print("Loading data...")
    data_15m, data_1h = load_data()
    print("Computing indicators...")
    computed = compute_indicators(data_15m, data_1h)
    print("Extracting signals...")
    signals = extract_signals(computed)
    print(f"Total strategy signals detected: {len(signals)}")

    # RUN MODEL A: Native 0.50% Risk ($5 risk) + 2 Trades/Day + $14 Target Lockout
    print("\nRunning Model A: Native 0.50% Risk + Max 2 Trades/Day + $14 Daily Lockout...")
    accts_a, payouts_a = run_simulation(signals, data_15m, target_14_dollars=False)
    print_audit(accts_a, payouts_a, "MODEL A: NATIVE 0.50% RISK | MAX 2 TRADES/DAY | $14 DAILY TARGET LOCKOUT")

    # RUN MODEL B: 14 USD Target Sizing (0.93% risk) + Max 2 Trades/Day + $14 Trade Lockout
    print("\nRunning Model B: 14 USD Target Sizing + Max 2 Trades/Day + $14 Immediate Lockout...")
    accts_b, payouts_b = run_simulation(signals, data_15m, target_14_dollars=True)
    print_audit(accts_b, payouts_b, "MODEL B: 14 USD TARGET SIZING (0.93% RISK) | MAX 2 TRADES/DAY | $14 IMMEDIATE LOCKOUT")

if __name__ == "__main__":
    main()
