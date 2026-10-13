"""
High-Yield Institutional Multi-Pair Portfolio Engine:
Applies asset-specific volume killzones and pair-specific calibration:
1. EURUSD: European Morning & NY (06-07, 09-13, 15 UTC) - avoids 08:00 whip. SL 16p, TP 24p (1.5R), Bank 60% @ 1R.
2. USDCHF: European expansion & NY (06-07, 12-15 UTC) - avoids 08-09 whip and 16 close. SL 16p, TP 24p, Bank 60% @ 1R.
3. USDCAD: North American Session (10-11, 13-16 UTC) - avoids European morning noise. SL 16p, TP 24p, Bank 60% @ 1R.
4. AUDUSD: Core Killzones (06-07, 09-11, 14-15 UTC). SL 14p, TP 21p, Bank 60% @ 1R.
5. GBPUSD: Selective London Mid-Morning & NY (09, 13-14, 16 UTC). SL 20p, TP 30p, Bank 60% @ 1R.

Evaluates:
- 6-Month Dataset (April 1 to October 9, 2026)
- Multi-Year Dataset (2024 to 2026)
Full friction (spread + 0.5p slippage + 0.35p commission + SL-first ambiguity).
"""

import sys
import pickle
import pandas as pd
import numpy as np

sys.path.append('scripts')
from deep_quant_winrate_research import load_data, compute_all_indicators, CONFIGS, PAIRS

PAIR_SCHEDULES = {
    "EURUSD": {
        "sl_pips": 16.0, "tp_rr": 1.50, "bank_pct": 0.60,
        "hours": [6, 7, 9, 10, 11, 12, 13, 15] # skips hour 8 and hour 14
    },
    "USDCHF": {
        "sl_pips": 16.0, "tp_rr": 1.50, "bank_pct": 0.60,
        "hours": [6, 7, 10, 12, 13, 15] # skips hours 8, 9, 11, 16
    },
    "USDCAD": {
        "sl_pips": 16.0, "tp_rr": 1.50, "bank_pct": 0.60,
        "hours": [9, 10, 11, 13, 14, 15, 16] # North American alignment, skips 6, 7, 8, 12
    },
    "AUDUSD": {
        "sl_pips": 14.0, "tp_rr": 1.50, "bank_pct": 0.60,
        "hours": [6, 7, 9, 10, 11, 14, 15]
    },
    "GBPUSD": {
        "sl_pips": 20.0, "tp_rr": 1.50, "bank_pct": 0.60,
        "hours": [9, 13, 14, 16]
    }
}

def run_high_yield_portfolio():
    d15, d1h = load_data()
    data = compute_all_indicators(d15, d1h)

    for window_name, start_d, end_d in [
        ("6-MONTH WINDOW (2026-04-01 to 2026-10-09)", "2026-04-01", "2026-10-09 23:45:00"),
        ("MULTI-YEAR AUDIT (2024 to 2026)", "2024-01-01", "2026-10-09 23:45:00")
    ]:
        print("\n" + "="*90)
        print(f"PORTFOLIO EVALUATION: {window_name}")
        print("="*90)

        all_trades = []

        for p, p_cfg in PAIR_SCHEDULES.items():
            df = data[p]
            pip = CONFIGS[p]["pip"]
            spread = CONFIGS[p]["spread"]
            costs = spread + 0.5 + 0.35
            sl_pts = p_cfg["sl_pips"]
            tp_rr = p_cfg["tp_rr"]
            bank_pct = p_cfg["bank_pct"]
            allowed_hrs = set(p_cfg["hours"])
            init_sl = sl_pts * pip

            n = len(df)
            state = 0
            entry_idx = 0
            entry_p, sl_p, tp_p = 0.0, 0.0, 0.0
            partial_taken = False
            partial_r_banked = 0.0

            for i in range(30, n):
                c = df.iloc[i]
                prev = df.iloc[i-1]
                t = c["time"]

                if t < pd.Timestamp(start_d, tz="UTC"): continue
                if t > pd.Timestamp(end_d, tz="UTC"): break

                h, l, close, open_p = float(c["high"]), float(c["low"]), float(c["close"]), float(c["open"])
                rng = (h - l) + 1e-9

                # Active position management
                if state != 0:
                    hold = i - entry_idx
                    if not partial_taken:
                        target_1r = init_sl * 1.0
                        if state == 1 and (h - entry_p) >= target_1r:
                            partial_taken = True
                            partial_r_banked = bank_pct * 1.0
                            sl_p = entry_p + (0.5 * pip) # Breakeven + buffer
                        elif state == -1 and (entry_p - l) >= target_1r:
                            partial_taken = True
                            partial_r_banked = bank_pct * 1.0
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

                # Signal filtering
                if t.weekday() >= 5: continue
                hr = t.hour
                if hr not in allowed_hrs: continue

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
                    if (asia_l and swept_l < asia_l and close > asia_l) or (sw10_l and swept_l < sw10_l and close > sw10_l):
                        long_ict = True

                    asia_h = c["asia_high"] if pd.notna(c["asia_high"]) else None
                    sw10_h = c["sw10_high"] if pd.notna(c["sw10_high"]) else None
                    swept_h = max(h, float(prev["high"]))
                    if (asia_h and swept_h > asia_h and close < asia_h) or (sw10_h and swept_h > sw10_h and close < sw10_h):
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
                    state = 1; entry_idx = i; entry_p = close; sl_p = entry_p - init_sl; tp_p = entry_p + (init_sl * tp_rr); partial_taken = False
                elif is_short:
                    state = -1; entry_idx = i; entry_p = close; sl_p = entry_p + init_sl; tp_p = entry_p - (init_sl * tp_rr); partial_taken = False

        tdf = pd.DataFrame(all_trades)
        if tdf.empty: continue
        tot = len(tdf)
        w = (tdf["outcome"] == "WIN").sum()
        l = (tdf["outcome"] == "LOSS").sum()
        be = (tdf["outcome"] == "BREAKEVEN").sum()
        wr = (w / tot) * 100.0
        net_r = tdf["realized_r"].sum()
        net_pips = tdf["net_pips"].sum()
        gw = tdf[tdf["realized_r"] > 0]["realized_r"].sum()
        gl = abs(tdf[tdf["realized_r"] < 0]["realized_r"].sum())
        pf = (gw / gl) if gl > 0 else 99.0
        exp_r = net_r / tot

        print(f"\n>>> HIGH-YIELD PORTFOLIO SUMMARY <<<")
        print(f"Total Trades: {tot} (avg {tot/135:.1f}/day)")
        print(f"Wins: {w} | Losses: {l} | Breakevens: {be}")
        print(f"WIN RATE: {wr:.2f}%")
        print(f"NET RETURN: {net_r:+6.2f} R")
        print(f"NET PIPS: {net_pips:+8.1f} pips")
        print(f"PROFIT FACTOR: {pf:.2f}")
        print(f"EXPECTANCY: {exp_r:+.3f} R/trade")

        print("\n--- INDIVIDUAL PAIR CONTRIBUTION ---")
        for p in PAIR_SCHEDULES.keys():
            sub = tdf[tdf["pair"] == p]
            if sub.empty: continue
            p_tot = len(sub)
            p_w = (sub["outcome"] == "WIN").sum()
            p_wr = (p_w / p_tot) * 100.0
            p_r = sub["realized_r"].sum()
            p_pips = sub["net_pips"].sum()
            p_gw = sub[sub["realized_r"] > 0]["realized_r"].sum()
            p_gl = abs(sub[sub["realized_r"] < 0]["realized_r"].sum())
            p_pf = (p_gw / p_gl) if p_gl > 0 else 99.0
            print(f"  {p:8s}: {p_tot:3d} tr | WR: {p_wr:5.1f}% | Net R: {p_r:+6.2f}R | Net Pips: {p_pips:+7.1f}p | PF: {p_pf:.2f}")

if __name__ == "__main__":
    run_high_yield_portfolio()
