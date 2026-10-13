"""
High-Yield 1H and Multi-Timeframe (15M + 1H) Quantitative Engine:
Tests 1H Swing setups vs 15M Intraday setups across all 6 Forex pairs
to discover if 1H unlocks the massive pip yield (+300 to +800 pips, +20R to +50R)
while maintaining Win Rate > 50% under full real-world friction.
"""

import sys
import pickle
import pandas as pd
import numpy as np

sys.path.append('scripts')
from deep_quant_winrate_research import load_data, CONFIGS, PAIRS

def test_1h_and_mtf():
    print("Loading data...")
    d15, d1h = load_data()

    print("\n" + "="*85)
    print("1H INSTITUTIONAL SWING STRATEGY (APRIL 1 TO OCTOBER 9, 2026)")
    print("="*85)

    # Indicator computation on 1H
    h1_computed = {}
    for p in PAIRS:
        df = d1h[p].copy()
        pip = CONFIGS[p]["pip"]

        # EMA 20, 50, 200
        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
        df["ema20_slope"] = df["ema20"] - df["ema20"].shift(2)

        # ATR 14
        tr = np.maximum(df["high"] - df["low"], np.maximum(np.abs(df["high"] - df["close"].shift(1)), np.abs(df["low"] - df["close"].shift(1))))
        tr.iloc[0] = df["high"].iloc[0] - df["low"].iloc[0]
        df["atr"] = tr.rolling(14).mean().bfill()

        # RSI 14
        delta = df["close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        df["rsi"] = (100.0 - (100.0 / (1.0 + rs))).bfill()

        # Donchian 20
        df["donch_high"] = df["high"].shift(1).rolling(20).max()
        df["donch_low"] = df["low"].shift(1).rolling(20).min()

        # D1 trend resampled from 1H
        df_dt = df.set_index("time")
        d1 = df_dt.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().reset_index()
        d1["ema50"] = d1["close"].ewm(span=50, adjust=False).mean()
        d1["d1_bull"] = d1["close"] > d1["ema50"]
        d1["d1_bear"] = d1["close"] < d1["ema50"]
        d1_map = d1.set_index("time")

        df["d1_time"] = df["time"].dt.floor("1D") - pd.Timedelta(days=1)
        df["d1_bull"] = df["d1_time"].map(d1_map["d1_bull"]).fillna(False)
        df["d1_bear"] = df["d1_time"].map(d1_map["d1_bear"]).fillna(False)

        h1_computed[p] = df

    # Test 1H setups across SL depths (20p, 25p, 30p) and RR ratios (1.5, 2.0, 2.5)
    for sl_pts in [20.0, 25.0, 30.0]:
        for rr in [1.5, 1.75, 2.0]:
            trades = []
            for p in PAIRS:
                df = h1_computed[p]
                pip = CONFIGS[p]["pip"]
                spread = CONFIGS[p]["spread"]
                costs = spread + 0.5 + 0.35 # Realistic friction
                n = len(df)

                state = 0
                entry_idx = 0
                entry_p, sl_p, tp_p = 0.0, 0.0, 0.0
                init_sl = sl_pts * pip
                partial_taken = False
                partial_r_banked = 0.0

                for i in range(50, n):
                    c = df.iloc[i]
                    prev = df.iloc[i-1]
                    t = c["time"]

                    if t < pd.Timestamp("2026-04-01", tz="UTC"): continue
                    if t > pd.Timestamp("2026-10-09 23:45:00", tz="UTC"): break

                    h, l, close, open_p = float(c["high"]), float(c["low"]), float(c["close"]), float(c["open"])
                    atr = float(c["atr"])

                    if state != 0:
                        hold = i - entry_idx
                        # Model J: bank 50% at 1.0R, SL to BE
                        if not partial_taken:
                            if state == 1 and (h - entry_p) >= init_sl:
                                partial_taken = True
                                partial_r_banked = 0.50
                                sl_p = entry_p + (1.0 * pip)
                            elif state == -1 and (entry_p - l) >= init_sl:
                                partial_taken = True
                                partial_r_banked = 0.50
                                sl_p = entry_p - (1.0 * pip)

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
                            elif hold >= 60: # 60 hours hold
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
                            elif hold >= 60:
                                exit_triggered = True
                                exit_price = close

                        if exit_triggered:
                            dir_mult = 1 if state == 1 else -1
                            gross_pips = (exit_price - entry_p) * dir_mult / pip
                            net_pips = gross_pips - costs

                            if partial_taken:
                                final_pips = (sl_pts * 0.50) + (net_pips * 0.50)
                                final_r = partial_r_banked + ((net_pips / sl_pts) * 0.50)
                            else:
                                final_pips = net_pips
                                final_r = net_pips / sl_pts

                            res = "WIN" if final_r > 0.02 else ("LOSS" if final_r < -0.02 else "BREAKEVEN")
                            trades.append({"pair": p, "realized_r": final_r, "net_pips": final_pips, "outcome": res})
                            state = 0
                            continue

                    # 1H Signal Logic
                    if t.weekday() >= 5: continue
                    hr = t.hour
                    # London + NY hours (07:00 to 18:00 UTC)
                    if not (7 <= hr <= 18): continue

                    bullish = (close > c["ema50"]) and (c["ema20"] > c["ema50"]) and (c["ema20_slope"] > 0) and c["d1_bull"]
                    bearish = (close < c["ema50"]) and (c["ema20"] < c["ema50"]) and (c["ema20_slope"] < 0) and c["d1_bear"]

                    # Pullback to 20-EMA with rejection
                    long_sig = bullish and (min(l, float(prev["low"])) <= c["ema20"]) and (close > open_p) and (40 <= c["rsi"] <= 75)
                    short_sig = bearish and (max(h, float(prev["high"])) >= c["ema20"]) and (close < open_p) and (25 <= c["rsi"] <= 60)

                    if long_sig:
                        state = 1
                        entry_idx = i
                        entry_p = close
                        sl_p = entry_p - init_sl
                        tp_p = entry_p + (init_sl * rr)
                        partial_taken = False
                        partial_r_banked = 0.0
                    elif short_sig:
                        state = -1
                        entry_idx = i
                        entry_p = close
                        sl_p = entry_p + init_sl
                        tp_p = entry_p - (init_sl * rr)
                        partial_taken = False
                        partial_r_banked = 0.0

            tdf = pd.DataFrame(trades)
            if tdf.empty: continue
            tot = len(tdf)
            w = (tdf["outcome"] == "WIN").sum()
            l = (tdf["outcome"] == "LOSS").sum()
            wr = (w / tot) * 100.0
            net_r = tdf["realized_r"].sum()
            net_pips = tdf["net_pips"].sum()
            gw = tdf[tdf["realized_r"] > 0]["realized_r"].sum()
            gl = abs(tdf[tdf["realized_r"] < 0]["realized_r"].sum())
            pf = (gw / gl) if gl > 0 else 99.0

            lbl = f"1H Swing (SL {sl_pts:.0f}p / TP {sl_pts*rr:.1f}p / RR {rr}:1)"
            print(f"  {lbl:45s} | Tr: {tot:3d} | WR: {wr:5.1f}% | Net R: {net_r:+6.2f}R | PF: {pf:.2f} | Net Pips: {net_pips:+7.1f}p")

if __name__ == "__main__":
    test_1h_and_mtf()
