"""
Optimization of Quant High-Conviction Model:
Testing exit R:R, structural stops, and profit banking to turn 57%+ win rate into strong positive expectancy (> +0.20R/trade and PF > 1.40).
"""

import sys
import pickle
import httpx
import json
import pandas as pd
import numpy as np
from deep_quant_winrate_research import load_data, compute_all_indicators, CONFIGS, PAIRS

def test_quant_variants(data_dict):
    variants = [
        ("V1: 15p TP / 10p SL, Bank 50% at 1.0R, SL to BE", {"tp_pips": 15.0, "sl_pips": 10.0, "partial_r": 1.0, "final_rr": 1.5}),
        ("V2: 18p TP / 10p SL, Bank 50% at 1.0R, SL to BE", {"tp_pips": 18.0, "sl_pips": 10.0, "partial_r": 1.0, "final_rr": 1.8}),
        ("V3: 20p TP / 10p SL, Bank 50% at 1.0R, SL to BE", {"tp_pips": 20.0, "sl_pips": 10.0, "partial_r": 1.0, "final_rr": 2.0}),
        ("V4: 15p TP / 10p SL, Bank 60% at 1.0R, SL to BE", {"tp_pips": 15.0, "sl_pips": 10.0, "partial_r": 1.0, "bank_pct": 0.60}),
        ("V5: 18p TP / 10p SL, Bank 60% at 1.0R, SL to BE", {"tp_pips": 18.0, "sl_pips": 10.0, "partial_r": 1.0, "bank_pct": 0.60}),
        ("V6: 20p TP / 10p SL, Bank 60% at 1.2R, SL to BE", {"tp_pips": 20.0, "sl_pips": 10.0, "partial_r": 1.2, "bank_pct": 0.60}),
        ("V7: 15p TP / 10p SL, Full 1.5R (No BE, clean 1.5R target)", {"tp_pips": 15.0, "sl_pips": 10.0, "no_partial": True}),
        ("V8: 12p TP / 10p SL, Full 1.2R target", {"tp_pips": 12.0, "sl_pips": 10.0, "no_partial": True}),
        ("V9: Structural SL (12-18p) + 1.5R TP + Bank 50% at 1.0R", {"use_struct_sl": True, "target_rr": 1.75, "partial_r": 1.0}),
    ]

    for name, v_cfg in variants:
        all_trades = []
        for p in PAIRS:
            df = data_dict[p]
            cfg = CONFIGS[p]
            pip = cfg["pip"]
            spread_pip = cfg["spread"]
            n = len(df)

            state = 0
            entry_idx = 0
            entry_p = 0.0
            sl_p = 0.0
            tp_p = 0.0
            init_sl_dist = 0.0
            partial_taken = False
            partial_r_banked = 0.0
            sl_pips_curr = v_cfg.get("sl_pips", 10.0)
            tp_pips_curr = v_cfg.get("tp_pips", 15.0)
            bank_pct = v_cfg.get("bank_pct", 0.50)
            partial_r = v_cfg.get("partial_r", 1.0)
            no_partial = v_cfg.get("no_partial", False)
            use_struct = v_cfg.get("use_struct_sl", False)

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

                if state != 0:
                    hold = i - entry_idx
                    if not no_partial and not partial_taken:
                        target_move = init_sl_dist * partial_r
                        if state == 1 and (h - entry_p) >= target_move:
                            partial_taken = True
                            partial_r_banked = bank_pct * partial_r
                            sl_p = entry_p + (0.5 * pip)
                        elif state == -1 and (entry_p - l) >= target_move:
                            partial_taken = True
                            partial_r_banked = bank_pct * partial_r
                            sl_p = entry_p - (0.5 * pip)

                    exit_triggered = False
                    exit_price = 0.0

                    if state == 1:
                        if h >= tp_p and l <= sl_p:
                            exit_triggered = True
                            exit_price = sl_p
                        elif h >= tp_p:
                            exit_triggered = True
                            exit_price = tp_p
                        elif l <= sl_p:
                            exit_triggered = True
                            exit_price = sl_p
                        elif hold >= 160:
                            exit_triggered = True
                            exit_price = close
                    elif state == -1:
                        if l <= tp_p and h >= sl_p:
                            exit_triggered = True
                            exit_price = sl_p
                        elif l <= tp_p:
                            exit_triggered = True
                            exit_price = tp_p
                        elif h >= sl_p:
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
                        sl_pts = init_sl_dist / pip

                        if not no_partial and partial_taken:
                            rem_pips = net_pips
                            final_pips = (sl_pts * partial_r * bank_pct) + (rem_pips * (1.0 - bank_pct))
                            final_r = partial_r_banked + ((rem_pips / sl_pts) * (1.0 - bank_pct))
                        else:
                            final_pips = net_pips
                            final_r = net_pips / sl_pts

                        trade_res = "WIN" if final_r > 0.02 else ("LOSS" if final_r < -0.02 else "BREAKEVEN")
                        all_trades.append({
                            "pair": p,
                            "realized_r": final_r,
                            "realized_pips": final_pips,
                            "outcome": trade_res
                        })
                        state = 0
                        continue

                # Signal check
                if t.weekday() >= 5: continue
                bar_hour = t.hour
                in_kz = (7 <= bar_hour <= 10) or (12 <= bar_hour <= 15)
                if not in_kz: continue

                atr = float(c["atr"])
                adx_val = float(c["adx"])
                if adx_val < 20.0: continue

                body_ratio = abs(close - open_p) / rng
                if body_ratio < 0.50: continue

                plus_di = float(c["plus_di"])
                minus_di = float(c["minus_di"])

                h1_bull = bool(c["h1_bull"])
                h1_bear = bool(c["h1_bear"])
                h4_bull = bool(c["h4_bull"])
                h4_bear = bool(c["h4_bear"])

                long_ict = False
                short_ict = False
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

                bullish_trend = (close > c["ema50"]) and (c["ema20"] > c["ema50"]) and (c["ema20_slope"] > 0)
                bearish_trend = (close < c["ema50"]) and (c["ema20"] < c["ema50"]) and (c["ema20_slope"] < 0)
                long_pb = False
                short_pb = False
                lookback = df.iloc[max(0, i-12):i]
                if bullish_trend and (lookback["close"] > lookback["donch_high"]).any() and (l <= c["ema20"] <= close) and (close > open_p):
                    long_pb = True
                if bearish_trend and (lookback["close"] < lookback["donch_low"]).any() and (close <= c["ema20"] <= h) and (close < open_p):
                    short_pb = True

                is_long = ((long_ict and c["rsi"] <= 75.0 and plus_di >= minus_di) or (long_pb and bullish_trend and 40 <= c["rsi"] <= 75 and plus_di >= minus_di)) and h1_bull and h4_bull
                is_short = ((short_ict and c["rsi"] >= 25.0 and minus_di >= plus_di) or (short_pb and bearish_trend and 25 <= c["rsi"] <= 60 and minus_di >= plus_di)) and h1_bear and h4_bear

                if is_long or is_short:
                    state = 1 if is_long else -1
                    entry_idx = i
                    entry_p = close
                    if use_struct:
                        sl_pts = min(max((atr * 1.5) / pip, 10.0), 20.0)
                        init_sl_dist = sl_pts * pip
                        tp_dist = init_sl_dist * v_cfg.get("target_rr", 1.75)
                    else:
                        init_sl_dist = sl_pips_curr * pip
                        tp_dist = tp_pips_curr * pip

                    if state == 1:
                        sl_p = entry_p - init_sl_dist
                        tp_p = entry_p + tp_dist
                    else:
                        sl_p = entry_p + init_sl_dist
                        tp_p = entry_p - tp_dist
                    partial_taken = False
                    partial_r_banked = 0.0

        tdf = pd.DataFrame(all_trades)
        if tdf.empty: continue
        tot = len(tdf)
        w = len(tdf[tdf["outcome"] == "WIN"])
        l = len(tdf[tdf["outcome"] == "LOSS"])
        wr = (w / tot) * 100.0
        net_r = tdf["realized_r"].sum()
        net_pips = tdf["realized_pips"].sum()
        gw = tdf[tdf["realized_r"] > 0]["realized_r"].sum()
        gl = abs(tdf[tdf["realized_r"] < 0]["realized_r"].sum())
        pf = (gw / gl) if gl > 0 else 99.0
        exp_r = net_r / tot

        print(f"\n>>> {name}")
        print(f"    Trades: {tot} | Wins: {w} | Losses: {l} | WR: {wr:.2f}%")
        print(f"    Net R: {net_r:+6.2f}R | Expectancy: {exp_r:+.3f}R | PF: {pf:.2f} | Net Pips: {net_pips:+7.1f}p")

if __name__ == "__main__":
    d15, d1h = load_data()
    data_dict = compute_all_indicators(d15, d1h)
    test_quant_variants(data_dict)
