"""
Deep Quantitative Win-Rate & Strategy Overhaul Engine
Systematically tests algorithmic trading, quantitative finance, and ICT market microstructure models
to achieve >50% win rate, positive expectancy, and prop firm challenge passing.
Data: 2026-04-01 to 2026-10-09 (6 months across 6 Forex pairs with realistic friction).
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

def compute_all_indicators(data_15m, data_1h):
    computed = {}
    for p in PAIRS:
        pip = CONFIGS[p]["pip"]
        h1 = data_1h[p].copy()
        h1["ema20"] = h1["close"].ewm(span=20, adjust=False).mean()
        h1["ema50"] = h1["close"].ewm(span=50, adjust=False).mean()
        h1["ema200"] = h1["close"].ewm(span=200, adjust=False).mean()
        h1["h1_bull"] = (h1["close"] > h1["ema50"]) & (h1["ema20"] >= h1["ema50"])
        h1["h1_bear"] = (h1["close"] < h1["ema50"]) & (h1["ema20"] <= h1["ema50"])
        
        # 4H resampled from 1H
        h1_dt = h1.set_index("time")
        h4 = h1_dt.resample("4h").agg({
            "open": "first", "high": "max", "low": "min", "close": "last"
        }).dropna().reset_index()
        h4["ema20"] = h4["close"].ewm(span=20, adjust=False).mean()
        h4["ema50"] = h4["close"].ewm(span=50, adjust=False).mean()
        h4["h4_bull"] = h4["ema20"] > h4["ema50"]
        h4["h4_bear"] = h4["ema20"] < h4["ema50"]
        h4_map = h4.set_index("time")

        h1_map = h1.set_index("time")

        m15 = data_15m[p].copy()
        m15["ema20"] = m15["close"].ewm(span=20, adjust=False).mean()
        m15["ema50"] = m15["close"].ewm(span=50, adjust=False).mean()
        m15["ema200"] = m15["close"].ewm(span=200, adjust=False).mean()
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
        m15["plus_di"] = plus_di
        m15["minus_di"] = minus_di

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

        # Map 1H and 4H with conservative lag
        m15["h1_time"] = m15["time"].dt.floor("h") - pd.Timedelta(hours=1)
        m15["h1_bull"] = m15["h1_time"].map(h1_map["h1_bull"]).fillna(False)
        m15["h1_bear"] = m15["h1_time"].map(h1_map["h1_bear"]).fillna(False)

        m15["h4_time"] = m15["time"].dt.floor("4h") - pd.Timedelta(hours=4)
        m15["h4_bull"] = m15["h4_time"].map(h4_map["h4_bull"]).fillna(False)
        m15["h4_bear"] = m15["h4_time"].map(h4_map["h4_bear"]).fillna(False)

        computed[p] = m15
    return computed

def run_experiment(data_dict, config):
    """
    Evaluates a specific quantitative variant over the 6-month period (2026-04-01 to 2026-10-09).
    config keys:
      - 'tp_pips': float
      - 'sl_pips': float
      - 'use_partial_be': bool (bank 50% at partial_r, SL to BE + 0.5 pip)
      - 'partial_r': float (e.g. 1.0)
      - 'trail_remainder': bool
      - 'require_h4': bool
      - 'min_adx': float
      - 'killzone_only': bool
      - 'min_body_ratio': float
      - 'allowed_pairs': list
    """
    tp_pips = config.get('tp_pips', 15.0)
    sl_pips = config.get('sl_pips', 10.0)
    use_partial_be = config.get('use_partial_be', False)
    partial_r = config.get('partial_r', 1.0)
    require_h4 = config.get('require_h4', False)
    min_adx = config.get('min_adx', 0.0)
    killzone_only = config.get('killzone_only', False)
    min_body_ratio = config.get('min_body_ratio', 0.45)
    allowed_pairs = config.get('allowed_pairs', PAIRS)

    all_trades = []

    for p in allowed_pairs:
        df = data_dict[p]
        cfg = CONFIGS[p]
        pip = cfg["pip"]
        spread_pip = cfg["spread"]
        n = len(df)

        state = 0 # 1: Long, -1: Short
        entry_idx = 0
        entry_p = 0.0
        sl_p = 0.0
        tp_p = 0.0
        init_sl_dist = 0.0
        partial_taken = False
        partial_r_banked = 0.0

        for i in range(30, n):
            c = df.iloc[i]
            prev = df.iloc[i-1]
            t = c["time"]

            if t < pd.Timestamp("2026-04-01", tz="UTC"):
                continue
            if t > pd.Timestamp("2026-10-09 23:45:00", tz="UTC"):
                break

            h, l, close, open_p = float(c["high"]), float(c["low"]), float(c["close"]), float(c["open"])
            rng = (h - l) + 1e-9

            # 1. Manage active position
            if state != 0:
                hold = i - entry_idx
                # Check partial take profit
                if use_partial_be and not partial_taken:
                    target_move = init_sl_dist * partial_r
                    if state == 1 and (h - entry_p) >= target_move:
                        partial_taken = True
                        partial_r_banked = 0.50 * partial_r
                        sl_p = entry_p + (0.5 * pip) # Breakeven + small buffer
                    elif state == -1 and (entry_p - l) >= target_move:
                        partial_taken = True
                        partial_r_banked = 0.50 * partial_r
                        sl_p = entry_p - (0.5 * pip)

                exit_triggered = False
                exit_price = 0.0
                outcome = ""

                if state == 1:
                    hit_tp = h >= tp_p
                    hit_sl = l <= sl_p
                    if hit_tp and hit_sl:
                        # Conservative assumption: hit SL first
                        exit_triggered = True
                        exit_price = sl_p
                        outcome = "LOSS" if not partial_taken else "WIN"
                    elif hit_tp:
                        exit_triggered = True
                        exit_price = tp_p
                        outcome = "WIN"
                    elif hit_sl:
                        exit_triggered = True
                        exit_price = sl_p
                        outcome = "LOSS" if not partial_taken else "WIN" # partial win if banked
                    elif hold >= 160:
                        exit_triggered = True
                        exit_price = close
                        outcome = "WIN" if exit_price > entry_p else "LOSS"

                elif state == -1:
                    hit_tp = l <= tp_p
                    hit_sl = h >= sl_p
                    if hit_tp and hit_sl:
                        exit_triggered = True
                        exit_price = sl_p
                        outcome = "LOSS" if not partial_taken else "WIN"
                    elif hit_tp:
                        exit_triggered = True
                        exit_price = tp_p
                        outcome = "WIN"
                    elif hit_sl:
                        exit_triggered = True
                        exit_price = sl_p
                        outcome = "LOSS" if not partial_taken else "WIN"
                    elif hold >= 160:
                        exit_triggered = True
                        exit_price = close
                        outcome = "WIN" if exit_price < entry_p else "LOSS"

                if exit_triggered:
                    dir_mult = 1 if state == 1 else -1
                    gross_pips = (exit_price - entry_p) * dir_mult / pip
                    costs_pips = spread_pip + 0.5 + 0.35
                    net_pips = gross_pips - costs_pips

                    if use_partial_be and partial_taken:
                        rem_pips = net_pips
                        final_pips = (sl_pips * partial_r * 0.5) + (rem_pips * 0.5)
                        final_r = partial_r_banked + ((rem_pips / sl_pips) * 0.5)
                    else:
                        final_pips = net_pips
                        final_r = net_pips / sl_pips

                    trade_res = "WIN" if final_r > 0.02 else ("LOSS" if final_r < -0.02 else "BREAKEVEN")

                    all_trades.append({
                        "pair": p,
                        "entry_time": df.iloc[entry_idx]["time"],
                        "exit_time": t,
                        "direction": "LONG" if state == 1 else "SHORT",
                        "realized_r": final_r,
                        "realized_pips": final_pips,
                        "outcome": trade_res,
                        "hold_bars": hold
                    })
                    state = 0
                    continue

            # 2. Look for Entry Signals
            if t.weekday() >= 5:
                continue
            bar_hour = t.hour
            if bar_hour < 6 or bar_hour >= 17 or (12 <= bar_hour < 14):
                continue

            in_kz = (7 <= bar_hour <= 10) or (12 <= bar_hour <= 15)
            if killzone_only and not in_kz:
                continue

            atr = float(c["atr"])
            adx_val = float(c["adx"])
            if adx_val < min_adx:
                continue

            # Directional DMI check
            plus_di = float(c["plus_di"])
            minus_di = float(c["minus_di"])

            body_ratio = abs(close - open_p) / rng
            if body_ratio < min_body_ratio:
                continue

            # HTF alignment
            h1_bull = bool(c["h1_bull"])
            h1_bear = bool(c["h1_bear"])
            h4_bull = bool(c["h4_bull"]) if require_h4 else True
            h4_bear = bool(c["h4_bear"]) if require_h4 else True

            # ICT Liquidity Sweep
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

            # Pullback trend setup
            bullish_trend = (close > c["ema50"]) and (c["ema20"] > c["ema50"]) and (c["ema20_slope"] > 0)
            bearish_trend = (close < c["ema50"]) and (c["ema20"] < c["ema50"]) and (c["ema20_slope"] < 0)
            long_pb = False
            short_pb = False
            lookback = df.iloc[max(0, i-12):i]
            if bullish_trend and (lookback["close"] > lookback["donch_high"]).any() and (l <= c["ema20"] <= close) and (close > open_p):
                long_pb = True
            if bearish_trend and (lookback["close"] < lookback["donch_low"]).any() and (close <= c["ema20"] <= h) and (close < open_p):
                short_pb = True

            conv_failed = False
            if p in ["USDJPY", "AUDUSD", "GBPUSD"]:
                min_sep = (0.25 * atr) if p == "AUDUSD" else (0.15 * atr)
                min_slope = (0.08 * atr) if p == "AUDUSD" else (0.04 * atr)
                if abs(c["ema20"] - c["ema50"]) < min_sep or abs(c["ema20_slope"]) < min_slope:
                    conv_failed = True

            is_long = ((long_ict and c["rsi"] <= 75.0 and plus_di >= minus_di) or (long_pb and bullish_trend and 40 <= c["rsi"] <= 75 and not conv_failed and plus_di >= minus_di)) and h1_bull and h4_bull
            is_short = ((short_ict and c["rsi"] >= 25.0 and minus_di >= plus_di) or (short_pb and bearish_trend and 25 <= c["rsi"] <= 60 and not conv_failed and minus_di >= plus_di)) and h1_bear and h4_bear

            if is_long:
                state = 1
                entry_idx = i
                entry_p = close
                init_sl_dist = sl_pips * pip
                sl_p = entry_p - init_sl_dist
                tp_p = entry_p + (tp_pips * pip)
                partial_taken = False
                partial_r_banked = 0.0
            elif is_short:
                state = -1
                entry_idx = i
                entry_p = close
                init_sl_dist = sl_pips * pip
                sl_p = entry_p + init_sl_dist
                tp_p = entry_p - (tp_pips * pip)
                partial_taken = False
                partial_r_banked = 0.0

    df_t = pd.DataFrame(all_trades)
    return df_t

def analyze_results(df_t, name):
    if df_t.empty:
        print(f"[{name}] No trades generated.")
        return
    tot = len(df_t)
    wins = len(df_t[df_t['outcome'] == 'WIN'])
    losses = len(df_t[df_t['outcome'] == 'LOSS'])
    be = len(df_t[df_t['outcome'] == 'BREAKEVEN'])
    wr = (wins / tot) * 100.0
    net_r = df_t['realized_r'].sum()
    net_pips = df_t['realized_pips'].sum()
    gw = df_t[df_t['realized_r'] > 0]['realized_r'].sum()
    gl = abs(df_t[df_t['realized_r'] < 0]['realized_r'].sum())
    pf = (gw / gl) if gl > 0 else 99.0
    exp_r = net_r / tot

    print(f"\n{'='*75}")
    print(f"MODEL: {name}")
    print(f"{'='*75}")
    print(f"Total Trades: {tot} (avg {tot/135:.1f}/day)")
    print(f"Wins: {wins} | Losses: {losses} | Breakevens: {be}")
    print(f"WIN RATE: {wr:.2f}%")
    print(f"Profit Factor: {pf:.2f} | Net R: {net_r:+6.2f}R | Expectancy: {exp_r:+.3f}R")
    print(f"Net Realized Pips: {net_pips:+8.1f} pips")

    # Per pair breakdown
    for p in PAIRS:
        sub = df_t[df_t['pair'] == p]
        if sub.empty: continue
        p_tot = len(sub)
        p_w = len(sub[sub['outcome'] == 'WIN'])
        p_wr = (p_w / p_tot) * 100.0
        p_r = sub['realized_r'].sum()
        p_pf = (sub[sub['realized_r'] > 0]['realized_r'].sum() / abs(sub[sub['realized_r'] < 0]['realized_r'].sum())) if abs(sub[sub['realized_r'] < 0]['realized_r'].sum()) > 0 else 99.0
        print(f"  {p:8s}: {p_tot:3d} tr | WR: {p_wr:5.1f}% | Net R: {p_r:+6.2f}R | PF: {p_pf:.2f}")

def main():
    print("Loading data...")
    d15, d1h = load_data()
    print("Computing indicators...")
    data_dict = compute_all_indicators(d15, d1h)
    print("Running experiments across 6 months (Apr-Oct 2026)...\n")

    experiments = [
        ("1. Baseline (Fixed 15p TP / 10p SL)", {
            "tp_pips": 15.0, "sl_pips": 10.0, "use_partial_be": False, "require_h4": False
        }),
        ("2. 1:1 Risk-Reward (Fixed 10p TP / 10p SL)", {
            "tp_pips": 10.0, "sl_pips": 10.0, "use_partial_be": False, "require_h4": False
        }),
        ("3. Model J (Bank 50% at +10p / +1.0R, SL to BE, 15p Final TP)", {
            "tp_pips": 15.0, "sl_pips": 10.0, "use_partial_be": True, "partial_r": 1.0, "require_h4": False
        }),
        ("4. Model J + 4H Trend Alignment", {
            "tp_pips": 15.0, "sl_pips": 10.0, "use_partial_be": True, "partial_r": 1.0, "require_h4": True
        }),
        ("5. Model J + 4H Trend + ADX >= 22 Filter", {
            "tp_pips": 15.0, "sl_pips": 10.0, "use_partial_be": True, "partial_r": 1.0, "require_h4": True, "min_adx": 22.0
        }),
        ("6. Model J + 4H Trend + Killzone Only (07-10, 12-15 UTC)", {
            "tp_pips": 15.0, "sl_pips": 10.0, "use_partial_be": True, "partial_r": 1.0, "require_h4": True, "killzone_only": True
        }),
        ("7. Quant High-Conviction (Model J, 4H Trend, ADX >= 20, Killzone Only, Body >= 50%)", {
            "tp_pips": 15.0, "sl_pips": 10.0, "use_partial_be": True, "partial_r": 1.0, "require_h4": True, "min_adx": 20.0, "killzone_only": True, "min_body_ratio": 0.50
        }),
    ]

    for name, cfg in experiments:
        df_res = run_experiment(data_dict, cfg)
        analyze_results(df_res, name)

if __name__ == "__main__":
    main()
