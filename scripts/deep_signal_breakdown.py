"""
Deep Signal & Component Breakdown:
Separates ICT Liquidity Sweeps vs Trend Pullbacks, analyzes per-pair alpha,
hour-of-day edge, and identifies the exact quantitative sweet spot for >50% WR and strong profitability.
"""

import sys
import pickle
import pandas as pd
import numpy as np
from deep_quant_winrate_research import load_data, compute_all_indicators, CONFIGS, PAIRS

def deep_signal_survey(data_dict):
    all_signals = []

    for p in PAIRS:
        df = data_dict[p]
        cfg = CONFIGS[p]
        pip = cfg["pip"]
        spread_pip = cfg["spread"]
        n = len(df)

        for i in range(30, n):
            c = df.iloc[i]
            prev = df.iloc[i-1]
            t = c["time"]

            if t < pd.Timestamp("2026-04-01", tz="UTC"): continue
            if t > pd.Timestamp("2026-10-09 23:45:00", tz="UTC"): break
            if t.weekday() >= 5: continue

            h, l, close, open_p = float(c["high"]), float(c["low"]), float(c["close"]), float(c["open"])
            rng = (h - l) + 1e-9
            atr = float(c["atr"])
            adx_val = float(c["adx"])
            bar_hour = t.hour

            body_ratio = abs(close - open_p) / rng
            plus_di = float(c["plus_di"])
            minus_di = float(c["minus_di"])
            h1_bull = bool(c["h1_bull"])
            h1_bear = bool(c["h1_bear"])
            h4_bull = bool(c["h4_bull"])
            h4_bear = bool(c["h4_bear"])

            in_kz = (7 <= bar_hour <= 10) or (12 <= bar_hour <= 15)

            # Check ICT Sweep
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

            # Check Pullback
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

            sig_type = None
            direction = None
            if long_ict and c["rsi"] <= 75.0 and plus_di >= minus_di and h1_bull and h4_bull:
                sig_type = "ICT_SWEEP"
                direction = "LONG"
            elif short_ict and c["rsi"] >= 25.0 and minus_di >= plus_di and h1_bear and h4_bear:
                sig_type = "ICT_SWEEP"
                direction = "SHORT"
            elif long_pb and bullish_trend and 40 <= c["rsi"] <= 75 and not conv_failed and plus_di >= minus_di and h1_bull and h4_bull:
                sig_type = "PULLBACK"
                direction = "LONG"
            elif short_pb and bearish_trend and 25 <= c["rsi"] <= 60 and not conv_failed and minus_di >= plus_di and h1_bear and h4_bear:
                sig_type = "PULLBACK"
                direction = "SHORT"

            if sig_type:
                all_signals.append({
                    "pair": p,
                    "bar_idx": i,
                    "time": t,
                    "hour": bar_hour,
                    "weekday": t.day_name(),
                    "sig_type": sig_type,
                    "direction": direction,
                    "entry_p": close,
                    "atr_pips": atr / pip,
                    "adx": adx_val,
                    "body_ratio": body_ratio,
                    "spread_pip": spread_pip,
                    "pip": pip
                })

    print(f"Total raw signals extracted: {len(all_signals)}")
    df_sig = pd.DataFrame(all_signals)
    print("\nSignal counts by type:")
    print(df_sig["sig_type"].value_counts())
    print("\nSignal counts by pair:")
    print(df_sig["pair"].value_counts())

    # Now simulate outcomes for each signal independently to measure individual edge
    # Let's test multiple exit profiles:
    # Exit A: 15p TP / 10p SL
    # Exit B: 10p TP / 10p SL
    # Exit C: 12p TP / 8p SL
    # Exit D: Model J (Bank 50% at 10p, SL to BE, 15p target)
    results = []
    for sig in all_signals:
        p = sig["pair"]
        df = data_dict[p]
        start_idx = sig["bar_idx"]
        direction = sig["direction"]
        entry_p = sig["entry_p"]
        pip = sig["pip"]
        spread_pip = sig["spread_pip"]
        costs_pips = spread_pip + 0.5 + 0.35

        # Forward scan up to 160 bars
        n = len(df)
        end_idx = min(n, start_idx + 160)

        # Track MFE (Max Favorable Excursion) and MAE (Max Adverse Excursion) in pips
        mfe_pips = 0.0
        mae_pips = 0.0

        for k in range(start_idx + 1, end_idx):
            bar = df.iloc[k]
            bh, bl = float(bar["high"]), float(bar["low"])
            if direction == "LONG":
                f_pips = (bh - entry_p) / pip
                a_pips = (entry_p - bl) / pip
            else:
                f_pips = (entry_p - bl) / pip
                a_pips = (bh - entry_p) / pip
            if f_pips > mfe_pips: mfe_pips = f_pips
            if a_pips > mae_pips: mae_pips = a_pips

        # Outcome under 15p / 10p
        # Outcome under 10p / 10p
        # Outcome under Model J (10p partial, BE, 15p TP)
        # Scan bar by bar to see what hits first
        # 15p / 10p:
        hit_15_10 = None
        hit_10_10 = None
        # Model J:
        partial_banked = False
        model_j_res = None

        sl_10 = entry_p - (10.0 * pip) if direction == "LONG" else entry_p + (10.0 * pip)
        tp_15 = entry_p + (15.0 * pip) if direction == "LONG" else entry_p - (15.0 * pip)
        tp_10 = entry_p + (10.0 * pip) if direction == "LONG" else entry_p - (10.0 * pip)
        be_sl = entry_p + (0.5 * pip) if direction == "LONG" else entry_p - (0.5 * pip)
        curr_sl = sl_10

        for k in range(start_idx + 1, end_idx):
            bar = df.iloc[k]
            bh, bl, bc = float(bar["high"]), float(bar["low"]), float(bar["close"])

            # 15p / 10p test
            if hit_15_10 is None:
                if direction == "LONG":
                    if bl <= sl_10: hit_15_10 = "LOSS"
                    elif bh >= tp_15: hit_15_10 = "WIN"
                else:
                    if bh >= sl_10: hit_15_10 = "LOSS"
                    elif bl <= tp_15: hit_15_10 = "WIN"

            # 10p / 10p test
            if hit_10_10 is None:
                if direction == "LONG":
                    if bl <= sl_10: hit_10_10 = "LOSS"
                    elif bh >= tp_10: hit_10_10 = "WIN"
                else:
                    if bh >= sl_10: hit_10_10 = "LOSS"
                    elif bl <= tp_10: hit_10_10 = "WIN"

            # Model J test
            if model_j_res is None:
                if not partial_banked:
                    if direction == "LONG":
                        if bh >= tp_10:
                            partial_banked = True
                            curr_sl = be_sl
                        elif bl <= curr_sl:
                            model_j_res = ("LOSS", -10.0 - costs_pips)
                    else:
                        if bl <= tp_10:
                            partial_banked = True
                            curr_sl = be_sl
                        elif bh >= curr_sl:
                            model_j_res = ("LOSS", -10.0 - costs_pips)
                else: # Partial banked
                    if direction == "LONG":
                        if bh >= tp_15:
                            # 50% at 10p, 50% at 15p minus costs
                            model_j_res = ("WIN", 12.5 - costs_pips)
                        elif bl <= curr_sl:
                            # 50% at 10p, 50% at 0.5p minus costs
                            model_j_res = ("WIN", 5.25 - costs_pips)
                    else:
                        if bl <= tp_15:
                            model_j_res = ("WIN", 12.5 - costs_pips)
                        elif bh >= curr_sl:
                            model_j_res = ("WIN", 5.25 - costs_pips)

        if hit_15_10 is None: hit_15_10 = "TIMEOUT"
        if hit_10_10 is None: hit_10_10 = "TIMEOUT"
        if model_j_res is None: model_j_res = ("TIMEOUT", 0.0)

        sig["hit_15_10"] = hit_15_10
        sig["hit_10_10"] = hit_10_10
        sig["model_j_res"] = model_j_res[0]
        sig["model_j_pips"] = model_j_res[1]
        sig["mfe_pips"] = mfe_pips
        sig["mae_pips"] = mae_pips
        results.append(sig)

    df_res = pd.DataFrame(results)

    print("\n" + "="*80)
    print("MFE / MAE ANALYSIS (Edge potential):")
    print("="*80)
    print(f"Mean MFE across all setups: {df_res['mfe_pips'].mean():.1f} pips")
    print(f"Median MFE across all setups: {df_res['mfe_pips'].median():.1f} pips")
    print(f"Percentage of trades reaching +8 pips: {(df_res['mfe_pips'] >= 8.0).mean()*100:.1f}%")
    print(f"Percentage of trades reaching +10 pips: {(df_res['mfe_pips'] >= 10.0).mean()*100:.1f}%")
    print(f"Percentage of trades reaching +12 pips: {(df_res['mfe_pips'] >= 12.0).mean()*100:.1f}%")
    print(f"Percentage of trades reaching +15 pips: {(df_res['mfe_pips'] >= 15.0).mean()*100:.1f}%")

    print("\n" + "="*80)
    print("PERFORMANCE BY SIGNAL TYPE:")
    print("="*80)
    for st in ["ICT_SWEEP", "PULLBACK"]:
        sub = df_res[df_res["sig_type"] == st]
        print(f"\n--- {st} (Count: {len(sub)}) ---")
        wr_15_10 = (sub["hit_15_10"] == "WIN").mean() * 100
        wr_10_10 = (sub["hit_10_10"] == "WIN").mean() * 100
        wr_mj = (sub["model_j_res"] == "WIN").mean() * 100
        net_mj_pips = sub["model_j_pips"].sum()
        print(f"  Fixed 15p/10p Win Rate: {wr_15_10:.1f}%")
        print(f"  Fixed 10p/10p Win Rate: {wr_10_10:.1f}%")
        print(f"  Model J Win Rate: {wr_mj:.1f}% | Net Pips: {net_mj_pips:+.1f}p")

    print("\n" + "="*80)
    print("PERFORMANCE BY PAIR (Model J):")
    print("="*80)
    for p in PAIRS:
        sub = df_res[df_res["pair"] == p]
        wr = (sub["model_j_res"] == "WIN").mean() * 100
        net_pips = sub["model_j_pips"].sum()
        gw = sub[sub["model_j_pips"] > 0]["model_j_pips"].sum()
        gl = abs(sub[sub["model_j_pips"] < 0]["model_j_pips"].sum())
        pf = (gw / gl) if gl > 0 else 99.0
        print(f"  {p:8s}: {len(sub):3d} setups | Model J WR: {wr:5.1f}% | Net Pips: {net_pips:+7.1f}p | PF: {pf:.2f}")

    print("\n" + "="*80)
    print("PERFORMANCE BY HOUR (Model J):")
    print("="*80)
    for h in sorted(df_res["hour"].unique()):
        sub = df_res[df_res["hour"] == h]
        wr = (sub["model_j_res"] == "WIN").mean() * 100
        net_pips = sub["model_j_pips"].sum()
        print(f"  Hour {h:02d}:00 UTC: {len(sub):3d} setups | WR: {wr:5.1f}% | Net Pips: {net_pips:+7.1f}p")

if __name__ == "__main__":
    d15, d1h = load_data()
    data_dict = compute_all_indicators(d15, d1h)
    deep_signal_survey(data_dict)
