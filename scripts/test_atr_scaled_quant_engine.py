"""
ATR-Adaptive Quantitative Engine:
Scales Stop Loss dynamically to pair volatility (1.2 * ATR_14, clamped to asset-specific ranges):
- EURUSD: 14-18 pips
- USDCHF: 14-18 pips
- AUDUSD: 12-16 pips
- USDCAD: 16-22 pips
- GBPUSD: 20-26 pips
- USDJPY: 22-30 pips
TP: 1.5R to 1.75R
Trade Management: Bank 60% at 1.0R, advance SL to BE + 0.5p buffer.
Evaluates 6-month window (April 1 to October 9, 2026) with full real-world friction.
"""

import sys
import pickle
import pandas as pd
import numpy as np

sys.path.append('scripts')
from deep_quant_winrate_research import load_data, compute_all_indicators, CONFIGS, PAIRS

PAIR_SL_RANGES = {
    "EURUSD": (14.0, 18.0),
    "USDCHF": (14.0, 18.0),
    "AUDUSD": (12.0, 16.0),
    "USDCAD": (16.0, 22.0),
    "GBPUSD": (20.0, 28.0),
    "USDJPY": (22.0, 32.0),
}

def test_atr_scaled_engine():
    d15, d1h = load_data()
    data = compute_all_indicators(d15, d1h)

    print("="*90)
    print("ATR-ADAPTIVE QUANTITATIVE ENGINE (APRIL - OCTOBER 2026)")
    print("="*90)

    for target_rr in [1.5, 1.6, 1.75]:
        for bank_pct in [0.50, 0.60]:
            all_trades = []

            for p in PAIRS:
                df = data[p]
                cfg = CONFIGS[p]
                pip = cfg["pip"]
                spread = cfg["spread"]
                costs = spread + 0.5 + 0.35
                min_sl_p, max_sl_p = PAIR_SL_RANGES[p]

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

                    if t < pd.Timestamp("2026-04-01", tz="UTC"): continue
                    if t > pd.Timestamp("2026-10-09 23:45:00", tz="UTC"): break

                    h, l, close, open_p = float(c["high"]), float(c["low"]), float(c["close"]), float(c["open"])
                    rng = (h - l) + 1e-9
                    atr = float(c["atr"])

                    # 1. Manage Active Position
                    if state != 0:
                        hold = i - entry_idx
                        if not partial_taken:
                            target_1r = init_sl_dist * 1.0
                            if state == 1 and (h - entry_p) >= target_1r:
                                partial_taken = True
                                partial_r_banked = bank_pct * 1.0
                                sl_p = entry_p + (0.5 * pip)
                            elif state == -1 and (entry_p - l) >= target_1r:
                                partial_taken = True
                                partial_r_banked = bank_pct * 1.0
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
                            net_pips = gross_pips - costs
                            sl_pts = init_sl_dist / pip

                            if partial_taken:
                                rem_weight = 1.0 - bank_pct
                                final_r = partial_r_banked + ((net_pips / sl_pts) * rem_weight)
                                final_pips = (sl_pts * 1.0 * bank_pct) + (net_pips * rem_weight)
                            else:
                                final_r = net_pips / sl_pts
                                final_pips = net_pips

                            res = "WIN" if final_r > 0.02 else ("LOSS" if final_r < -0.02 else "BREAKEVEN")
                            all_trades.append({
                                "pair": p,
                                "entry_time": df.iloc[entry_idx]["time"],
                                "outcome": res,
                                "realized_r": final_r,
                                "net_pips": final_pips
                            })
                            state = 0
                            continue

                    # Signal filtering: Core sessions (06-16 UTC), ADX >= 18, Body >= 0.45
                    if t.weekday() >= 5: continue
                    hr = t.hour
                    if not (6 <= hr <= 16): continue

                    adx_val = float(c["adx"])
                    if adx_val < 18.0: continue

                    body_ratio = abs(close - open_p) / rng
                    if body_ratio < 0.45: continue

                    plus_di, minus_di = float(c["plus_di"]), float(c["minus_di"])
                    h1_bull, h1_bear = bool(c["h1_bull"]), bool(c["h1_bear"])
                    h4_bull, h4_bear = bool(c["h4_bull"]), bool(c["h4_bear"])

                    # Setups
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

                    if is_long or is_short:
                        state = 1 if is_long else -1
                        entry_idx = i
                        entry_p = close

                        # Volatility-adjusted stop loss: 1.2 * ATR_14 clamped to pair-specific range
                        calc_sl_pts = (atr * 1.2) / pip
                        sl_pts = min(max(calc_sl_pts, min_sl_p), max_sl_p)
                        init_sl_dist = sl_pts * pip

                        if state == 1:
                            sl_p = entry_p - init_sl_dist
                            tp_p = entry_p + (init_sl_dist * target_rr)
                        else:
                            sl_p = entry_p + init_sl_dist
                            tp_p = entry_p - (init_sl_dist * target_rr)

                        partial_taken = False
                        partial_r_banked = 0.0

            tdf = pd.DataFrame(all_trades)
            if tdf.empty: continue
            tot = len(tdf)
            w = (tdf["outcome"] == "WIN").sum()
            wr = (w / tot) * 100.0
            net_r = tdf["realized_r"].sum()
            net_pips = tdf["net_pips"].sum()
            gw = tdf[tdf["realized_r"] > 0]["realized_r"].sum()
            gl = abs(tdf[tdf["realized_r"] < 0]["realized_r"].sum())
            pf = (gw / gl) if gl > 0 else 99.0
            exp_r = net_r / tot

            lbl = f"RR={target_rr:.2f} | Bank={int(bank_pct*100)}% @ 1R"
            print(f"\n>>> {lbl} (ALL 6 PAIRS) <<<")
            print(f"    Total Trades: {tot} | Wins: {w} | WIN RATE: {wr:.1f}%")
            print(f"    NET R: {net_r:+6.2f}R | PROFIT FACTOR: {pf:.2f} | EXPECTANCY: {exp_r:+.3f}R | NET PIPS: {net_pips:+7.1f}p")

            # Per pair breakdown
            for p in PAIRS:
                sub = tdf[tdf["pair"] == p]
                if sub.empty: continue
                p_tot = len(sub)
                p_w = (sub["outcome"] == "WIN").sum()
                p_wr = (p_w / p_tot) * 100.0
                p_r = sub["realized_r"].sum()
                p_pips = sub["net_pips"].sum()
                p_pf = (sub[sub["realized_r"] > 0]["realized_r"].sum() / abs(sub[sub["realized_r"] < 0]["realized_r"].sum())) if abs(sub[sub["realized_r"] < 0]["realized_r"].sum()) > 0 else 99.0
                print(f"      {p:8s}: {p_tot:3d} tr | WR: {p_wr:5.1f}% | Net R: {p_r:+6.2f}R | Net Pips: {p_pips:+7.1f}p | PF: {p_pf:.2f}")

if __name__ == "__main__":
    test_atr_scaled_engine()
