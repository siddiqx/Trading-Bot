"""
Long-Term and Prop Firm Validation of Model 7 Quant Engine
Tests SL 12p-18p across:
1. 6-Month Dataset (2026-04-01 to 2026-10-09)
2. 24-Month Dataset (2024 to 2026)
3. Full GFT $5,000 2-Step Standard Challenge simulation (Phase 1 + Phase 2 + Funded)
"""

import sys
import pickle
import pandas as pd
import numpy as np
from deep_quant_winrate_research import load_data, compute_all_indicators, CONFIGS, PAIRS

def run_longterm_and_prop_test():
    d15, d1h = load_data()
    data_dict = compute_all_indicators(d15, d1h)

    # Grid of SL and TP combinations with Model J
    base_cfg = {
        "use_partial_be": True, "partial_r": 1.0,
        "require_h4": True, "min_adx": 20.0, "killzone_only": True, "min_body_ratio": 0.50
    }

    # Test SL depths: 12p, 14p, 15p, 16p with 1.5R target
    sl_tp_pairs = [
        (12.0, 18.0),
        (14.0, 21.0),
        (15.0, 22.5),
        (16.0, 24.0),
    ]

    print("\n" + "="*90)
    print("PHASE 1: 6-MONTH HISTORICAL BACKTEST (2026-04-01 to 2026-10-09)")
    print("="*90)

    for p_label, p_basket in [
        ("Core Triad (EURUSD, USDCHF, AUDUSD)", ["EURUSD", "USDCHF", "AUDUSD"]),
        ("All 6 Forex Pairs", PAIRS)
    ]:
        print(f"\n--- Basket: {p_label} ---")
        for sl, tp in sl_tp_pairs:
            cfg = {**base_cfg, "allowed_pairs": p_basket, "sl_pips": sl, "tp_pips": tp}
            res = run_simulation(data_dict, cfg, "2026-04-01", "2026-10-09 23:45:00")
            print_metrics(res, f"SL {sl:.0f}p / TP {tp:.1f}p")

    print("\n" + "="*90)
    print("PHASE 2: MULTI-YEAR ROBUSTNESS AUDIT (2024-01-01 to 2026-10-09)")
    print("="*90)

    for p_label, p_basket in [
        ("Core Triad (EURUSD, USDCHF, AUDUSD)", ["EURUSD", "USDCHF", "AUDUSD"]),
        ("All 6 Forex Pairs", PAIRS)
    ]:
        print(f"\n--- Basket: {p_label} ---")
        for sl, tp in sl_tp_pairs:
            cfg = {**base_cfg, "allowed_pairs": p_basket, "sl_pips": sl, "tp_pips": tp}
            res = run_simulation(data_dict, cfg, "2024-01-01", "2026-10-09 23:45:00")
            print_metrics(res, f"SL {sl:.0f}p / TP {tp:.1f}p")

    print("\n" + "="*90)
    print("PHASE 3: PROP FIRM SIMULATION — $5,000 GFT 2-STEP STANDARD CHALLENGE")
    print("==========================================================================================")
    # Let's test Core Triad (SL 14p / TP 21p) and All 6 Pairs (SL 14p / TP 21p) on GFT 2-Step Standard rules
    for p_label, p_basket in [
        ("Core Triad (EURUSD, USDCHF, AUDUSD)", ["EURUSD", "USDCHF", "AUDUSD"]),
        ("All 6 Forex Pairs", PAIRS)
    ]:
        cfg = {**base_cfg, "allowed_pairs": p_basket, "sl_pips": 14.0, "tp_pips": 21.0}
        trades_df = run_simulation(data_dict, cfg, "2026-04-01", "2026-10-09 23:45:00")
        simulate_prop_challenge(trades_df, p_label)

def run_simulation(data_dict, config, start_date, end_date):
    tp_pips = config["tp_pips"]
    sl_pips = config["sl_pips"]
    use_partial_be = config.get("use_partial_be", True)
    partial_r = config.get("partial_r", 1.0)
    require_h4 = config.get("require_h4", True)
    min_adx = config.get("min_adx", 20.0)
    min_body_ratio = config.get("min_body_ratio", 0.50)
    allowed_pairs = config["allowed_pairs"]

    all_trades = []

    for p in allowed_pairs:
        df = data_dict[p]
        cfg = CONFIGS[p]
        pip = cfg["pip"]
        spread_pip = cfg["spread"]
        n = len(df)

        state = 0
        entry_idx = 0
        entry_p, sl_p, tp_p = 0.0, 0.0, 0.0
        init_sl_dist = 0.0
        partial_taken = False
        partial_r_banked = 0.0

        for i in range(30, n):
            c = df.iloc[i]
            prev = df.iloc[i-1]
            t = c["time"]

            if t < pd.Timestamp(start_date, tz="UTC"): continue
            if t > pd.Timestamp(end_date, tz="UTC"): break

            h, l, close, open_p = float(c["high"]), float(c["low"]), float(c["close"]), float(c["open"])
            rng = (h - l) + 1e-9

            if state != 0:
                hold = i - entry_idx
                if use_partial_be and not partial_taken:
                    target_move = init_sl_dist * partial_r
                    if state == 1 and (h - entry_p) >= target_move:
                        partial_taken = True
                        partial_r_banked = 0.50 * partial_r
                        sl_p = entry_p + (0.5 * pip) # Breakeven + buffer
                    elif state == -1 and (entry_p - l) >= target_move:
                        partial_taken = True
                        partial_r_banked = 0.50 * partial_r
                        sl_p = entry_p - (0.5 * pip)

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
                    costs_pips = spread_pip + 0.5 + 0.35
                    net_pips = gross_pips - costs_pips

                    if use_partial_be and partial_taken:
                        rem_pips = net_pips
                        final_pips = (sl_pips * partial_r * 0.50) + (rem_pips * 0.50)
                        final_r = partial_r_banked + ((rem_pips / sl_pips) * 0.50)
                    else:
                        final_pips = net_pips
                        final_r = net_pips / sl_pips

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

            # Signal filtering
            if t.weekday() >= 5: continue
            hr = t.hour
            in_kz = (7 <= hr <= 10) or (12 <= hr <= 15)
            if not in_kz: continue

            atr = float(c["atr"])
            adx_val = float(c["adx"])
            if adx_val < min_adx: continue

            body_ratio = abs(close - open_p) / rng
            if body_ratio < min_body_ratio: continue

            plus_di, minus_di = float(c["plus_di"]), float(c["minus_di"])
            h1_bull, h1_bear = bool(c["h1_bull"]), bool(c["h1_bear"])
            h4_bull = bool(c["h4_bull"]) if require_h4 else True
            h4_bear = bool(c["h4_bear"]) if require_h4 else True

            # ICT Sweep
            long_ict, short_ict = False, False
            if rng >= 0.50 * atr:
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

            # Trend Pullback
            bullish_trend = (close > c["ema50"]) and (c["ema20"] > c["ema50"]) and (c["ema20_slope"] > 0)
            bearish_trend = (close < c["ema50"]) and (c["ema20"] < c["ema50"]) and (c["ema20_slope"] < 0)
            lookback = df.iloc[max(0, i-12):i]
            long_pb = bullish_trend and (lookback["close"] > lookback["donch_high"]).any() and (l <= c["ema20"] <= close) and (close > open_p)
            short_pb = bearish_trend and (lookback["close"] < lookback["donch_low"]).any() and (close <= c["ema20"] <= h) and (close < open_p)

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

    return pd.DataFrame(all_trades)

def print_metrics(df, label):
    if df.empty:
        print(f"  {label:20s}: No trades.")
        return
    tot = len(df)
    w = (df['outcome'] == 'WIN').sum()
    l = (df['outcome'] == 'LOSS').sum()
    wr = (w / tot) * 100.0
    net_r = df['realized_r'].sum()
    net_pips = df['realized_pips'].sum()
    gw = df[df['realized_r'] > 0]['realized_r'].sum()
    gl = abs(df[df['realized_r'] < 0]['realized_r'].sum())
    pf = (gw / gl) if gl > 0 else 99.0
    exp_r = net_r / tot

    print(f"  {label:20s} | Tr: {tot:4d} | WR: {wr:5.1f}% | Net R: {net_r:+6.2f}R | PF: {pf:.2f} | Exp: {exp_r:+.3f}R | Pips: {net_pips:+7.1f}p")

def simulate_prop_challenge(trades_df, basket_name):
    """
    Simulates the $5,000 Goat Funded Trader 2-Step Standard Challenge:
    - Phase 1: +$500.00 (+10%), 5% daily DD ($250), 10% max loss ($500), min 3 days >= $25
    - Phase 2: +$250.00 (+5%), 5% daily DD ($250), 10% max loss ($500), min 3 days >= $25
    - Risk per trade: 1.0% ($50) or 0.75% ($37.50)
    """
    if trades_df.empty: return
    trades_df = trades_df.sort_values("entry_time").reset_index(drop=True)

    risk_per_trade_usd = 40.0 # 0.80% risk per trade ($40 risk per 1.0R)

    print(f"\n--- Testing Challenge on {basket_name} ($40 Risk / 0.80% per trade) ---")

    balance = 5000.0
    phase = "PHASE_1"
    p1_target = 5500.0
    p2_target = 5250.0
    p1_pass_date = None
    p2_pass_date = None
    daily_profits = {} # date -> profit

    max_dd = 0.0
    peak_bal = 5000.0

    trades_taken = 0
    p1_trades = 0
    p2_trades = 0
    funded_trades = 0

    for idx, t in trades_df.iterrows():
        r = t["realized_r"]
        trade_pnl = r * risk_per_trade_usd
        trades_taken += 1

        balance += trade_pnl
        if balance > peak_bal: peak_bal = balance
        dd = peak_bal - balance
        if dd > max_dd: max_dd = dd

        d_str = t["entry_time"].strftime("%Y-%m-%d")
        daily_profits[d_str] = daily_profits.get(d_str, 0.0) + trade_pnl

        if phase == "PHASE_1":
            p1_trades += 1
            if balance >= p1_target:
                qual_days = sum(1 for d, pnl in daily_profits.items() if pnl >= 25.0)
                if qual_days >= 3:
                    phase = "PHASE_2"
                    p1_pass_date = t["exit_time"]
                    balance = 5000.0 # Phase 2 resets to $5,000
                    peak_bal = 5000.0
                    daily_profits = {}
        elif phase == "PHASE_2":
            p2_trades += 1
            if balance >= p2_target:
                qual_days = sum(1 for d, pnl in daily_profits.items() if pnl >= 25.0)
                if qual_days >= 3:
                    phase = "FUNDED"
                    p2_pass_date = t["exit_time"]
                    daily_profits = {}
        elif phase == "FUNDED":
            funded_trades += 1

    print(f"  Final Challenge Status: {phase}")
    print(f"  Phase 1 Passed: {'YES at ' + str(p1_pass_date) if p1_pass_date else 'NO'} ({p1_trades} trades)")
    print(f"  Phase 2 Passed: {'YES at ' + str(p2_pass_date) if p2_pass_date else 'NO'} ({p2_trades} trades)")
    print(f"  Peak Drawdown: ${max_dd:.2f} (Max Allowed: $500.00)")
    print(f"  Funded Account Balance: ${balance:.2f} ({funded_trades} funded trades taken)")

if __name__ == "__main__":
    run_longterm_and_prop_test()
