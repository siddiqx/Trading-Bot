"""
Diagnostic & Quantitative Edge Engine:
Tests SL depth (10p, 12p, 15p, 18p, 20p, 25p) and Limit Retest entries vs Market entries
to solve the wick-out problem and unlock the massive MFE edge (where 84% reach +10p and 77% reach +15p).
"""

import sys
import pickle
import pandas as pd
import numpy as np
from deep_quant_winrate_research import load_data, compute_all_indicators, CONFIGS, PAIRS

def test_sl_and_retest_depth(data_dict):
    d15 = data_dict

    sl_levels = [10.0, 12.0, 15.0, 18.0, 20.0, 25.0]
    rr_levels = [1.0, 1.25, 1.5, 1.75, 2.0]

    # First: evaluate the raw market entry across different SL and TP combinations
    print("="*85)
    print("GRID SEARCH: STOP LOSS DEPTH vs TAKE PROFIT RATIO (Clean Market Entry)")
    print("="*85)

    # Let's collect signals with our high-conviction filter:
    # 4H trend + 1H trend + ADX >= 20 + KZ hours (06-17 UTC, Mon-Fri)
    filtered_signals = []
    for p in PAIRS:
        df = d15[p]
        pip = CONFIGS[p]["pip"]
        spread_pip = CONFIGS[p]["spread"]
        n = len(df)

        for i in range(30, n):
            c = df.iloc[i]
            prev = df.iloc[i-1]
            t = c["time"]

            if t < pd.Timestamp("2026-04-01", tz="UTC"): continue
            if t > pd.Timestamp("2026-10-09 23:45:00", tz="UTC"): break
            if t.weekday() >= 5: continue

            hr = t.hour
            if not ((6 <= hr <= 10) or (12 <= hr <= 16)): continue

            close, open_p, h, l = float(c["close"]), float(c["open"]), float(c["high"]), float(c["low"])
            rng = (h - l) + 1e-9
            atr = float(c["atr"])
            adx_val = float(c["adx"])
            if adx_val < 20.0: continue

            body_ratio = abs(close - open_p) / rng
            if body_ratio < 0.45: continue

            plus_di = float(c["plus_di"])
            minus_di = float(c["minus_di"])

            h1_bull = bool(c["h1_bull"])
            h1_bear = bool(c["h1_bear"])
            h4_bull = bool(c["h4_bull"])
            h4_bear = bool(c["h4_bear"])

            # Pullback or Sweep
            bullish_trend = (close > c["ema50"]) and (c["ema20"] > c["ema50"]) and (c["ema20_slope"] > 0)
            bearish_trend = (close < c["ema50"]) and (c["ema20"] < c["ema50"]) and (c["ema20_slope"] < 0)

            lookback = df.iloc[max(0, i-12):i]
            long_pb = bullish_trend and (lookback["close"] > lookback["donch_high"]).any() and (l <= c["ema20"] <= close) and (close > open_p)
            short_pb = bearish_trend and (lookback["close"] < lookback["donch_low"]).any() and (close <= c["ema20"] <= h) and (close < open_p)

            # Sweep
            long_ict = False
            short_ict = False
            if rng >= 0.50 * atr:
                asia_l = c["asia_low"] if pd.notna(c["asia_low"]) else None
                sw10_l = c["sw10_low"] if pd.notna(c["sw10_low"]) else None
                swept_l = min(l, float(prev["low"]))
                if close > open_p and ((close - l) / rng >= 0.50) and ((asia_l and swept_l < asia_l and close > asia_l) or (sw10_l and swept_l < sw10_l and close > sw10_l)):
                    long_ict = True

                asia_h = c["asia_high"] if pd.notna(c["asia_high"]) else None
                sw10_h = c["sw10_high"] if pd.notna(c["sw10_high"]) else None
                swept_h = max(h, float(prev["high"]))
                if close < open_p and ((h - close) / rng >= 0.50) and ((asia_h and swept_h > asia_h and close < asia_h) or (sw10_h and swept_h > sw10_h and close < sw10_h)):
                    short_ict = True

            direction = None
            if ((long_pb and 40 <= c["rsi"] <= 75) or (long_ict and c["rsi"] <= 75)) and plus_di >= minus_di and h1_bull and h4_bull:
                direction = "LONG"
            elif ((short_pb and 25 <= c["rsi"] <= 60) or (short_ict and c["rsi"] >= 25)) and minus_di >= plus_di and h1_bear and h4_bear:
                direction = "SHORT"

            if direction:
                filtered_signals.append({
                    "pair": p,
                    "bar_idx": i,
                    "direction": direction,
                    "entry_p": close,
                    "pip": pip,
                    "spread_pip": spread_pip,
                    "atr_pips": atr / pip,
                    "time": t
                })

    print(f"Total High-Conviction Confluence Signals: {len(filtered_signals)}")

    # Test SL and TP grid
    grid_results = []
    for sl in [10.0, 12.0, 15.0, 18.0, 20.0, 25.0]:
        for rr in [1.0, 1.25, 1.5, 1.75, 2.0]:
            tp = sl * rr
            wins = 0
            losses = 0
            net_r = 0.0
            net_pips = 0.0
            gw_pips = 0.0
            gl_pips = 0.0

            for sig in filtered_signals:
                p = sig["pair"]
                df = d15[p]
                start_i = sig["bar_idx"]
                direction = sig["direction"]
                entry_p = sig["entry_p"]
                pip = sig["pip"]
                spread_pip = sig["spread_pip"]
                costs_pips = spread_pip + 0.5 + 0.35 # Realistic spread + 0.5p slippage + 0.35p comm

                sl_price = entry_p - (sl * pip) if direction == "LONG" else entry_p + (sl * pip)
                tp_price = entry_p + (tp * pip) if direction == "LONG" else entry_p - (tp * pip)

                outcome = None
                exit_price = None

                for k in range(start_i + 1, min(len(df), start_i + 160)):
                    bar = df.iloc[k]
                    bh, bl = float(bar["high"]), float(bar["low"])

                    if direction == "LONG":
                        if bl <= sl_price:
                            outcome = "LOSS"
                            exit_price = sl_price
                            break
                        elif bh >= tp_price:
                            outcome = "WIN"
                            exit_price = tp_price
                            break
                    else:
                        if bh >= sl_price:
                            outcome = "LOSS"
                            exit_price = sl_price
                            break
                        elif bl <= tp_price:
                            outcome = "WIN"
                            exit_price = tp_price
                            break

                if outcome == "WIN":
                    wins += 1
                    pips = tp - costs_pips
                    r_val = pips / sl
                    net_r += r_val
                    net_pips += pips
                    gw_pips += pips
                elif outcome == "LOSS":
                    losses += 1
                    pips = -sl - costs_pips
                    r_val = pips / sl
                    net_r += r_val
                    net_pips += pips
                    gl_pips += abs(pips)

            tot = wins + losses
            if tot == 0: continue
            wr = (wins / tot) * 100.0
            pf = (gw_pips / gl_pips) if gl_pips > 0 else 99.0
            exp_r = net_r / tot

            grid_results.append({
                "SL_pips": sl,
                "RR": rr,
                "TP_pips": tp,
                "Trades": tot,
                "Wins": wins,
                "Losses": losses,
                "WinRate%": round(wr, 1),
                "Net_R": round(net_r, 2),
                "Expectancy_R": round(exp_r, 3),
                "ProfitFactor": round(pf, 2),
                "Net_Pips": round(net_pips, 1)
            })

    df_grid = pd.DataFrame(grid_results)
    # Filter to only WinRate > 50%
    print("\nALL CONFIGURATIONS WITH WIN RATE > 50%:")
    df_wr50 = df_grid[df_grid["WinRate%"] >= 50.0].sort_values(by="ProfitFactor", ascending=False)
    print(df_wr50.to_string(index=False))

    print("\nTOP 10 MOST PROFITABLE CONFIGURATIONS:")
    df_top = df_grid.sort_values(by="Net_R", ascending=False).head(10)
    print(df_top.to_string(index=False))

if __name__ == "__main__":
    d15, d1h = load_data()
    data_dict = compute_all_indicators(d15, d1h)
    test_sl_and_retest_depth(data_dict)
