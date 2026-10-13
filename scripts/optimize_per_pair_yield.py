"""
Per-Pair Yield Maximization Engine:
Systematically evaluates each pair (EURUSD, USDCHF, AUDUSD, USDCAD, USDJPY, GBPUSD) individually
to determine its optimal target multiple, trailing mechanism, and signal parameters
to maximize Net R and Pip yield while strictly keeping Win Rate > 50%.
"""

import sys
import pickle
import pandas as pd
import numpy as np

sys.path.append('scripts')
from deep_quant_winrate_research import load_data, compute_all_indicators, CONFIGS, PAIRS

def optimize_per_pair():
    d15, d1h = load_data()
    data = compute_all_indicators(d15, d1h)

    print("="*90)
    print("PER-PAIR PARAMETER SWEEP ACROSS 6-MONTH DATASET (APRIL - OCTOBER 2026)")
    print("="*90)

    for p in PAIRS:
        df = data[p]
        cfg = CONFIGS[p]
        pip = cfg["pip"]
        spread = cfg["spread"]
        costs = spread + 0.5 + 0.35

        print(f"\n{'#'*40} {p} {'#'*40}")
        best_cfg = None
        best_r = -999.0

        for sl_pips in [12.0, 14.0, 16.0, 18.0]:
            for final_rr in [1.5, 1.75, 2.0, 2.25, 2.5]:
                for bank_pct in [0.40, 0.50, 0.60]:
                    trades = []
                    n = len(df)
                    state = 0
                    entry_idx = 0
                    entry_p, sl_p, tp_p = 0.0, 0.0, 0.0
                    init_sl_dist = sl_pips * pip
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
                                trades.append({"outcome": res, "realized_r": final_r, "net_pips": final_pips})
                                state = 0
                                continue

                        # Signal criteria: 06-16 UTC, ADX >= 18, body >= 0.45
                        if t.weekday() >= 5: continue
                        hr = t.hour
                        if not (6 <= hr <= 16): continue

                        atr = float(c["atr"])
                        adx_val = float(c["adx"])
                        if adx_val < 18.0: continue

                        body_ratio = abs(close - open_p) / rng
                        if body_ratio < 0.45: continue

                        plus_di, minus_di = float(c["plus_di"]), float(c["minus_di"])
                        h1_bull, h1_bear = bool(c["h1_bull"]), bool(c["h1_bear"])
                        h4_bull, h4_bear = bool(c["h4_bull"]), bool(c["h4_bear"])

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

                        is_long = ((long_ict and c["rsi"] <= 78.0 and plus_di >= minus_di) or (long_pb and bullish_trend and 38 <= c["rsi"] <= 78 and plus_di >= minus_di)) and h1_bull and h4_bull
                        is_short = ((short_ict and c["rsi"] >= 22.0 and minus_di >= plus_di) or (short_pb and bearish_trend and 22 <= c["rsi"] <= 62 and minus_di >= plus_di)) and h1_bear and h4_bear

                        if is_long:
                            state = 1
                            entry_idx = i
                            entry_p = close
                            sl_p = entry_p - init_sl_dist
                            tp_p = entry_p + (init_sl_dist * final_rr)
                            partial_taken = False
                            partial_r_banked = 0.0
                        elif is_short:
                            state = -1
                            entry_idx = i
                            entry_p = close
                            sl_p = entry_p + init_sl_dist
                            tp_p = entry_p - (init_sl_dist * final_rr)
                            partial_taken = False
                            partial_r_banked = 0.0

                    tdf = pd.DataFrame(trades)
                    if tdf.empty: continue
                    tot = len(tdf)
                    w = (tdf["outcome"] == "WIN").sum()
                    wr = (w / tot) * 100.0
                    net_r = tdf["realized_r"].sum()
                    net_pips = tdf["net_pips"].sum()
                    gw = tdf[tdf["realized_r"] > 0]["realized_r"].sum()
                    gl = abs(tdf[tdf["realized_r"] < 0]["realized_r"].sum())
                    pf = (gw / gl) if gl > 0 else 99.0

                    if wr >= 50.0 and net_r > best_r:
                        best_r = net_r
                        best_cfg = (sl_pips, final_rr, bank_pct, tot, wr, net_r, net_pips, pf)

        if best_cfg:
            sl_pips, final_rr, bank_pct, tot, wr, net_r, net_pips, pf = best_cfg
            print(f"  OPTIMAL {p}: SL={sl_pips:.0f}p | Target={final_rr:.2f}R | Bank={int(bank_pct*100)}% @ 1R")
            print(f"  Trades: {tot} | Win Rate: {wr:.1f}% | Net R: {net_r:+6.2f}R | Net Pips: {net_pips:+7.1f}p | PF: {pf:.2f}")
        else:
            print(f"  No config with WR >= 50% found for {p}")

if __name__ == "__main__":
    optimize_per_pair()
