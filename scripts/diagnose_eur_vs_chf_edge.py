"""
Comparative Forensic Engine: EURUSD (Alpha Leader) vs USDCHF/USDCAD/GBPUSD
Dissects why EURUSD delivers +10.15R, 63.8% WR, and 1.54 PF, and applies those exact structural conditions to turn the other pairs strongly profitable.
"""

import sys
import pickle
import pandas as pd
import numpy as np

sys.path.append('scripts')
from deep_quant_winrate_research import load_data, compute_all_indicators, CONFIGS, PAIRS

def compare_trades():
    d15, d1h = load_data()
    data = compute_all_indicators(d15, d1h)

    for p in ["EURUSD", "USDCHF", "USDCAD", "GBPUSD"]:
        df = data[p]
        cfg = CONFIGS[p]
        pip = cfg["pip"]
        spread = cfg["spread"]
        costs = spread + 0.5 + 0.35
        sl_pts = 16.0
        init_sl = sl_pts * pip

        trades = []
        n = len(df)
        state = 0
        entry_idx = 0
        entry_p, sl_p, tp_p = 0.0, 0.0, 0.0
        partial_taken = False

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
                if not partial_taken:
                    if state == 1 and (h - entry_p) >= init_sl:
                        partial_taken = True
                        sl_p = entry_p + (0.5 * pip)
                    elif state == -1 and (entry_p - l) >= init_sl:
                        partial_taken = True
                        sl_p = entry_p - (0.5 * pip)

                exit_triggered = False
                exit_price = 0.0

                if state == 1:
                    if h >= tp_p and l <= sl_p: exit_triggered = True; exit_price = sl_p
                    elif h >= tp_p: exit_triggered = True; exit_price = tp_p
                    elif l <= sl_p: exit_triggered = True; exit_price = sl_p
                    elif hold >= 160: exit_triggered = True; exit_price = close
                elif state == -1:
                    if l <= tp_p and h >= sl_p: exit_triggered = True; exit_price = sl_p
                    elif l <= tp_p: exit_triggered = True; exit_price = tp_p
                    elif h >= sl_p: exit_triggered = True; exit_price = sl_p
                    elif hold >= 160: exit_triggered = True; exit_price = close

                if exit_triggered:
                    dir_mult = 1 if state == 1 else -1
                    gross_pips = (exit_price - entry_p) * dir_mult / pip
                    net_pips = gross_pips - costs
                    if partial_taken:
                        final_r = 0.60 + ((net_pips / sl_pts) * 0.40)
                        final_pips = (sl_pts * 0.60) + (net_pips * 0.40)
                    else:
                        final_r = net_pips / sl_pts
                        final_pips = net_pips

                    trades.append({
                        "entry_time": df.iloc[entry_idx]["time"],
                        "hour": df.iloc[entry_idx]["time"].hour,
                        "weekday": df.iloc[entry_idx]["time"].day_name(),
                        "direction": "LONG" if state == 1 else "SHORT",
                        "outcome": "WIN" if final_r > 0.02 else ("LOSS" if final_r < -0.02 else "BE"),
                        "realized_r": final_r,
                        "net_pips": final_pips,
                        "adx": df.iloc[entry_idx]["adx"],
                        "rsi": df.iloc[entry_idx]["rsi"],
                    })
                    state = 0
                    continue

            # Signal
            if t.weekday() >= 5: continue
            hr = t.hour
            if not (6 <= hr <= 16): continue
            atr = float(c["atr"])
            if float(c["adx"]) < 18.0: continue
            if abs(close - open_p) / rng < 0.45: continue

            plus_di, minus_di = float(c["plus_di"]), float(c["minus_di"])
            h1_bull, h1_bear = bool(c["h1_bull"]), bool(c["h1_bear"])
            h4_bull, h4_bear = bool(c["h4_bull"]), bool(c["h4_bear"])

            # Sweep
            long_ict, short_ict = False, False
            if rng >= 0.45 * atr:
                asia_l = c["asia_low"] if pd.notna(c["asia_low"]) else None
                sw10_l = c["sw10_low"] if pd.notna(c["sw10_low"]) else None
                swept_l = min(l, float(prev["low"]))
                if close > open_p and ((close - l) / rng >= 0.45) and ((asia_l and swept_l < asia_l and close > asia_l) or (sw10_l and swept_l < sw10_l and close > sw10_l)):
                    long_ict = True

                asia_h = c["asia_high"] if pd.notna(c["asia_high"]) else None
                sw10_h = c["sw10_high"] if pd.notna(c["sw10_high"]) else None
                swept_h = max(h, float(prev["high"]))
                if close < open_p and ((h - close) / rng >= 0.45) and ((asia_h and swept_h > asia_h and close < asia_h) or (sw10_h and swept_h > sw10_h and close < sw10_h)):
                    short_ict = True

            # Pullback
            bullish_trend = (close > c["ema50"]) and (c["ema20"] > c["ema50"]) and (c["ema20_slope"] > 0)
            bearish_trend = (close < c["ema50"]) and (c["ema20"] < c["ema50"]) and (c["ema20_slope"] < 0)
            lookback = df.iloc[max(0, i-12):i]
            long_pb = bullish_trend and (lookback["close"] > lookback["donch_high"]).any() and (l <= c["ema20"] <= close) and (close > open_p)
            short_pb = bearish_trend and (lookback["close"] < lookback["donch_low"]).any() and (close <= c["ema20"] <= h) and (close < open_p)

            is_long = ((long_ict and c["rsi"] <= 78.0 and plus_di >= minus_di) or (long_pb and bullish_trend and 38 <= c["rsi"] <= 78 and plus_di >= minus_di)) and h1_bull and h4_bull
            is_short = ((short_ict and c["rsi"] >= 22.0 and minus_di >= plus_di) or (short_pb and bearish_trend and 22 <= c["rsi"] <= 62 and minus_di >= plus_di)) and h1_bear and h4_bear

            if is_long:
                state = 1; entry_idx = i; entry_p = close; sl_p = entry_p - init_sl; tp_p = entry_p + (init_sl * 1.5); partial_taken = False
            elif is_short:
                state = -1; entry_idx = i; entry_p = close; sl_p = entry_p + init_sl; tp_p = entry_p - (init_sl * 1.5); partial_taken = False

        tdf = pd.DataFrame(trades)
        w = (tdf["outcome"] == "WIN").sum()
        tot = len(tdf)
        wr = (w / tot) * 100
        net_r = tdf["realized_r"].sum()
        net_p = tdf["net_pips"].sum()
        print(f"\n[{p}] Total: {tot} | Wins: {w} | WR: {wr:.1f}% | Net R: {net_r:+5.2f}R | Net Pips: {net_p:+6.1f}p")

        # Win rate by hour
        print("  By Hour:")
        for hr_val in sorted(tdf["hour"].unique()):
            sub_h = tdf[tdf["hour"] == hr_val]
            sub_w = (sub_h["outcome"] == "WIN").sum()
            sub_wr = (sub_w / len(sub_h)) * 100
            sub_r = sub_h["realized_r"].sum()
            print(f"    Hour {hr_val:02d}: {len(sub_h):2d} tr | WR: {sub_wr:5.1f}% | Net R: {sub_r:+5.2f}R")

if __name__ == "__main__":
    compare_trades()
