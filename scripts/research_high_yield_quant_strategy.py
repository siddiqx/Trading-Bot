"""
High-Yield Quantitative Strategy Research:
Objective: Substantially increase Net R and Net Pips over the 6-month window
while strictly maintaining Win Rate > 50%, positive expectancy, and prop-firm safety.
Tests:
1. Target Expansion (1.75R, 2.0R, 2.5R runners after banking 1.0R partial).
2. Runner trailing mechanics (Trailing 20-EMA, trailing ATR, or multi-target scaling).
3. Selective session/indicator expansion to capture 150-250 high-conviction trades over 6 months instead of only 70.
4. Per-pair alpha maximization across EURUSD, GBPUSD, USDJPY, USDCAD, USDCHF, AUDUSD.
"""

import sys
import pickle
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# Add scripts directory to path
sys.path.append('scripts')
from deep_quant_winrate_research import load_data, compute_all_indicators, CONFIGS, PAIRS

def run_high_yield_research():
    print("Loading data...")
    d15, d1h = load_data()
    print("Computing indicators...")
    data_dict = compute_all_indicators(d15, d1h)

    print("\n" + "="*90)
    print("EXPERIMENT 1: RUNNER TARGET EXPANSION ON MODEL J")
    print("Bank 40-50% at +1.0R (Locks >50% WR & risk-free BE), let remainder run to higher targets")
    print("="*90)

    # Grid of runner targets and banking ratios
    # Base SL: 14.0 pips
    runner_configs = [
        ("Base (Bank 50% at 1.0R, TP at 1.5R)", 0.50, 1.0, 1.5, False),
        ("Runner 1.75R (Bank 50% at 1.0R, TP at 1.75R)", 0.50, 1.0, 1.75, False),
        ("Runner 2.0R (Bank 50% at 1.0R, TP at 2.0R)", 0.50, 1.0, 2.0, False),
        ("Runner 2.25R (Bank 50% at 1.0R, TP at 2.25R)", 0.50, 1.0, 2.25, False),
        ("Runner 2.5R (Bank 50% at 1.0R, TP at 2.5R)", 0.50, 1.0, 2.5, False),
        ("Tranche Scale (Bank 40% at 1.0R, 30% at 1.75R, 30% at 2.5R)", "TRANCHE", 1.0, 2.5, False),
        ("Trailing EMA (Bank 50% at 1.0R, Trail remainder on 20-EMA)", 0.50, 1.0, 3.0, True),
    ]

    for p_label, p_basket in [
        ("Core Triad (EURUSD, USDCHF, AUDUSD)", ["EURUSD", "USDCHF", "AUDUSD"]),
        ("All 6 Forex Pairs", PAIRS)
    ]:
        print(f"\n--- Basket: {p_label} (SL = 14.0 pips) ---")
        for name, bank_pct, part_r, final_rr, trail_ema in runner_configs:
            cfg = {
                "sl_pips": 14.0,
                "partial_r": part_r,
                "bank_pct": bank_pct,
                "final_rr": final_rr,
                "trail_ema": trail_ema,
                "allowed_pairs": p_basket,
                "session_hours": (7, 16), # 07:00 to 16:00 UTC core London/NY
                "min_adx": 18.0,
                "min_body_ratio": 0.45
            }
            res = simulate_yield(data_dict, cfg)
            print_metrics(res, name)

    print("\n" + "="*90)
    print("EXPERIMENT 2: OPTIMIZING FREQUENCY & FILTER CALIBRATION")
    print("Testing broader session windows (06-16 UTC vs 07-15 UTC), ADX thresholds (15, 18, 20)")
    print("="*90)

    for adx_th in [15.0, 18.0, 20.0]:
        for s_start, s_end in [(6, 16), (7, 16), (7, 15)]:
            cfg = {
                "sl_pips": 14.0,
                "partial_r": 1.0,
                "bank_pct": 0.50,
                "final_rr": 2.0, # 2.0R runner
                "trail_ema": False,
                "allowed_pairs": ["EURUSD", "USDCHF", "AUDUSD"],
                "session_hours": (s_start, s_end),
                "min_adx": adx_th,
                "min_body_ratio": 0.40
            }
            lbl = f"Hours {s_start:02d}-{s_end:02d} | ADX >={adx_th:.0f}"
            res = simulate_yield(data_dict, cfg)
            print_metrics(res, lbl)

def simulate_yield(data_dict, config):
    sl_pips = config["sl_pips"]
    partial_r = config["partial_r"]
    bank_pct = config["bank_pct"]
    final_rr = config["final_rr"]
    trail_ema = config.get("trail_ema", False)
    allowed_pairs = config["allowed_pairs"]
    s_start, s_end = config["session_hours"]
    min_adx = config["min_adx"]
    min_body_ratio = config["min_body_ratio"]

    all_trades = []

    for p in allowed_pairs:
        df = data_dict[p]
        cfg = CONFIGS[p]
        pip = cfg["pip"]
        spread_pip = cfg["spread"]
        costs_pips = spread_pip + 0.5 + 0.35
        n = len(df)

        state = 0
        entry_idx = 0
        entry_p, sl_p, tp_p = 0.0, 0.0, 0.0
        init_sl_dist = 0.0
        partial_taken = False
        tranche2_taken = False
        partial_r_banked = 0.0

        for i in range(30, n):
            c = df.iloc[i]
            prev = df.iloc[i-1]
            t = c["time"]

            if t < pd.Timestamp("2026-04-01", tz="UTC"): continue
            if t > pd.Timestamp("2026-10-09 23:45:00", tz="UTC"): break

            h, l, close, open_p = float(c["high"]), float(c["low"]), float(c["close"]), float(c["open"])
            rng = (h - l) + 1e-9

            if state != 0:
                hold = i - entry_idx

                # Dynamic Trade Management
                if not partial_taken:
                    target_1r = init_sl_dist * partial_r
                    if state == 1 and (h - entry_p) >= target_1r:
                        partial_taken = True
                        pct1 = 0.40 if bank_pct == "TRANCHE" else bank_pct
                        partial_r_banked = pct1 * partial_r
                        sl_p = entry_p + (0.5 * pip) # Breakeven + buffer
                    elif state == -1 and (entry_p - l) >= target_1r:
                        partial_taken = True
                        pct1 = 0.40 if bank_pct == "TRANCHE" else bank_pct
                        partial_r_banked = pct1 * partial_r
                        sl_p = entry_p - (0.5 * pip)

                elif bank_pct == "TRANCHE" and not tranche2_taken:
                    target_175r = init_sl_dist * 1.75
                    if state == 1 and (h - entry_p) >= target_175r:
                        tranche2_taken = True
                        partial_r_banked += 0.30 * 1.75
                        sl_p = entry_p + (1.0 * init_sl_dist) # Lock in +1.0R on runner
                    elif state == -1 and (entry_p - l) >= target_175r:
                        tranche2_taken = True
                        partial_r_banked += 0.30 * 1.75
                        sl_p = entry_p - (1.0 * init_sl_dist)

                # Trailing 20-EMA check for runner
                if trail_ema and partial_taken:
                    ema20 = float(c["ema20"])
                    if state == 1 and ema20 > sl_p:
                        sl_p = ema20
                    elif state == -1 and ema20 < sl_p:
                        sl_p = ema20

                exit_triggered = False
                exit_price = 0.0

                if state == 1:
                    hit_tp = h >= tp_p
                    hit_sl = l <= sl_p
                    if hit_tp and hit_sl:
                        exit_triggered = True
                        exit_price = sl_p
                    elif hit_tp:
                        exit_triggered = True
                        exit_price = tp_p
                    elif hit_sl:
                        exit_triggered = True
                        exit_price = sl_p
                    elif hold >= 160:
                        exit_triggered = True
                        exit_price = close
                elif state == -1:
                    hit_tp = l <= tp_p
                    hit_sl = h >= sl_p
                    if hit_tp and hit_sl:
                        exit_triggered = True
                        exit_price = sl_p
                    elif hit_tp:
                        exit_triggered = True
                        exit_price = tp_p
                    elif hit_sl:
                        exit_triggered = True
                        exit_price = sl_p
                    elif hold >= 160:
                        exit_triggered = True
                        exit_price = close

                if exit_triggered:
                    dir_mult = 1 if state == 1 else -1
                    gross_pips = (exit_price - entry_p) * dir_mult / pip
                    net_pips = gross_pips - costs_pips
                    sl_pts = init_sl_dist / pip

                    if bank_pct == "TRANCHE":
                        if tranche2_taken:
                            rem_weight = 0.30
                        elif partial_taken:
                            rem_weight = 0.60
                        else:
                            rem_weight = 1.0

                        if partial_taken:
                            final_r = partial_r_banked + ((net_pips / sl_pts) * rem_weight)
                            final_pips = (sl_pts * partial_r_banked) + (net_pips * rem_weight)
                        else:
                            final_r = net_pips / sl_pts
                            final_pips = net_pips
                    elif partial_taken:
                        rem_weight = 1.0 - bank_pct
                        final_r = partial_r_banked + ((net_pips / sl_pts) * rem_weight)
                        final_pips = (sl_pts * partial_r * bank_pct) + (net_pips * rem_weight)
                    else:
                        final_r = net_pips / sl_pts
                        final_pips = net_pips

                    res = "WIN" if final_r > 0.02 else ("LOSS" if final_r < -0.02 else "BREAKEVEN")
                    all_trades.append({
                        "pair": p,
                        "entry_time": df.iloc[entry_idx]["time"],
                        "exit_time": t,
                        "direction": "LONG" if state == 1 else "SHORT",
                        "realized_r": final_r,
                        "realized_pips": final_pips,
                        "outcome": res,
                        "hold_bars": hold
                    })
                    state = 0
                    continue

            # Signal scanning
            if t.weekday() >= 5: continue
            hr = t.hour
            in_session = (s_start <= hr <= s_end)
            if not in_session: continue

            atr = float(c["atr"])
            adx_val = float(c["adx"])
            if adx_val < min_adx: continue

            body_ratio = abs(close - open_p) / rng
            if body_ratio < min_body_ratio: continue

            plus_di, minus_di = float(c["plus_di"]), float(c["minus_di"])
            h1_bull, h1_bear = bool(c["h1_bull"]), bool(c["h1_bear"])
            h4_bull, h4_bear = bool(c["h4_bull"]), bool(c["h4_bear"])

            # 1. ICT Sweep
            long_ict, short_ict = False, False
            if rng >= 0.45 * atr:
                if close > open_p and ((close - l) / rng >= 0.45):
                    asia_l = c["asia_low"] if pd.notna(c["asia_low"]) else None
                    sw10_l = c["sw10_low"] if pd.notna(c["sw10_low"]) else None
                    swept_l = min(l, float(prev["low"]))
                    if (asia_l and swept_l < asia_l and close > asia_l) or (sw10_l and swept_l < sw10_l and close > sw10_l):
                        long_ict = True
                if close < open_p and ((h - close) / rng >= 0.45):
                    asia_h = c["asia_high"] if pd.notna(c["asia_high"]) else None
                    sw10_h = c["sw10_high"] if pd.notna(c["sw10_high"]) else None
                    swept_h = max(h, float(prev["high"]))
                    if (asia_h and swept_h > asia_h and close < asia_h) or (sw10_h and swept_h > sw10_h and close < sw10_h):
                        short_ict = True

            # 2. Trend Pullback
            bullish_trend = (close > c["ema50"]) and (c["ema20"] > c["ema50"]) and (c["ema20_slope"] > 0)
            bearish_trend = (close < c["ema50"]) and (c["ema20"] < c["ema50"]) and (c["ema20_slope"] < 0)
            lookback = df.iloc[max(0, i-12):i]
            long_pb = bullish_trend and (lookback["close"] > lookback["donch_high"]).any() and (l <= c["ema20"] <= close) and (close > open_p)
            short_pb = bearish_trend and (lookback["close"] < lookback["donch_low"]).any() and (close <= c["ema20"] <= h) and (close < open_p)

            conv_failed = False
            if p in ["USDJPY", "AUDUSD", "GBPUSD"]:
                min_sep = (0.20 * atr) if p == "AUDUSD" else (0.12 * atr)
                min_slope = (0.06 * atr) if p == "AUDUSD" else (0.03 * atr)
                if abs(c["ema20"] - c["ema50"]) < min_sep or abs(c["ema20_slope"]) < min_slope:
                    conv_failed = True

            is_long = ((long_ict and c["rsi"] <= 78.0 and plus_di >= minus_di) or (long_pb and bullish_trend and 38 <= c["rsi"] <= 78 and not conv_failed and plus_di >= minus_di)) and h1_bull and h4_bull
            is_short = ((short_ict and c["rsi"] >= 22.0 and minus_di >= plus_di) or (short_pb and bearish_trend and 22 <= c["rsi"] <= 62 and not conv_failed and minus_di >= plus_di)) and h1_bear and h4_bear

            if is_long:
                state = 1
                entry_idx = i
                entry_p = close
                init_sl_dist = sl_pips * pip
                sl_p = entry_p - init_sl_dist
                tp_p = entry_p + (init_sl_dist * final_rr)
                partial_taken = False
                tranche2_taken = False
                partial_r_banked = 0.0
            elif is_short:
                state = -1
                entry_idx = i
                entry_p = close
                init_sl_dist = sl_pips * pip
                sl_p = entry_p + init_sl_dist
                tp_p = entry_p - (init_sl_dist * final_rr)
                partial_taken = False
                tranche2_taken = False
                partial_r_banked = 0.0

    return pd.DataFrame(all_trades)

def print_metrics(df, label):
    if df.empty:
        print(f"  {label:35s}: No trades.")
        return
    tot = len(df)
    w = (df['outcome'] == 'WIN').sum()
    l = (df['outcome'] == 'LOSS').sum()
    be = (df['outcome'] == 'BREAKEVEN').sum()
    wr = (w / tot) * 100.0
    net_r = df['realized_r'].sum()
    net_pips = df['realized_pips'].sum()
    gw = df[df['realized_r'] > 0]['realized_r'].sum()
    gl = abs(df[df['realized_r'] < 0]['realized_r'].sum())
    pf = (gw / gl) if gl > 0 else 99.0
    exp_r = net_r / tot

    print(f"  {label:38s} | Tr: {tot:3d} | WR: {wr:5.1f}% | Net R: {net_r:+6.2f}R | PF: {pf:.2f} | Exp: {exp_r:+.3f}R | Pips: {net_pips:+7.1f}p")

if __name__ == "__main__":
    run_high_yield_research()
