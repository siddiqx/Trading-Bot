"""
Institutional Quantitative Alpha Exploration:
Tests 4 classic quantitative & algorithmic trading models across the 6 Forex pairs:
Model 1: ICT AMD Judas Swing (Asian Liquidity Sweep Reversal at London Open)
Model 2: London Open Breakout (ORB 07:00 UTC with 4H Trend Alignment)
Model 3: Multi-Timeframe Pullback to 50% Equilibrium / Order Block
Model 4: Regime-Adaptive Volatility Breakout (ADX Trend + ATR Keltner Expansion)
"""

import sys
import pickle
import pandas as pd
import numpy as np
from deep_quant_winrate_research import load_data, compute_all_indicators, CONFIGS, PAIRS

def run_quant_alpha_exploration():
    print("Loading datasets...")
    d15, d1h = load_data()
    data = compute_all_indicators(d15, d1h)

    # -------------------------------------------------------------------------
    # MODEL 1: ICT AMD Judas Swing (Asian Range Liquidity Sweep at London Open)
    # -------------------------------------------------------------------------
    def test_judas_swing():
        trades = []
        for p in PAIRS:
            df = data[p]
            pip = CONFIGS[p]["pip"]
            spread = CONFIGS[p]["spread"]
            costs = spread + 0.5 + 0.35

            # Group by day to get Asian range (00:00 to 06:00 UTC)
            df_sub = df[(df["time"] >= "2026-04-01") & (df["time"] <= "2026-10-09")].copy()
            days = df_sub["time"].dt.date.unique()

            for day in days:
                day_bars = df_sub[df_sub["time"].dt.date == day]
                asia_bars = day_bars[(day_bars["time"].dt.hour >= 0) & (day_bars["time"].dt.hour < 6)]
                if len(asia_bars) < 10: continue

                asia_h = asia_bars["high"].max()
                asia_l = asia_bars["low"].min()
                asia_rng = (asia_h - asia_l) / pip

                # In Forex, good Asian ranges are 15 to 45 pips
                if asia_rng < 12.0 or asia_rng > 50.0: continue

                # London session: 07:00 to 11:00 UTC
                london_bars = day_bars[(day_bars["time"].dt.hour >= 7) & (day_bars["time"].dt.hour <= 11)]
                if london_bars.empty: continue

                # Scan for sweep of Asia High or Low
                swept_high = False
                swept_low = False
                entered = False

                for idx, row in london_bars.iterrows():
                    if entered: break
                    bh, bl, bc, bo = row["high"], row["low"], row["close"], row["open"]
                    h4_bull = row["h4_bull"]
                    h4_bear = row["h4_bear"]

                    # Judas High Sweep -> Short Reversal (Manipulation up, Distribution down)
                    if bh > asia_h and bc < asia_h and bc < bo:
                        # Rejection candle closing back below Asian High
                        entry_p = bc
                        # SL above the sweep high + 2 pips buffer
                        sl_dist = max((bh - entry_p) + (2.0 * pip), 8.0 * pip)
                        sl_pips = sl_dist / pip
                        if sl_pips > 25.0: continue # Skip wide stops
                        # Target: Asian Low or 1.5R
                        tp_pips = max(sl_pips * 1.5, 12.0)
                        tp_p = entry_p - (tp_pips * pip)
                        sl_p = entry_p + sl_dist

                        # Evaluate trade
                        trade_res = eval_trade(df, idx, "SHORT", entry_p, sl_p, tp_p, pip, costs, sl_pips, tp_pips)
                        trades.append({"model": "Judas_Swing", "pair": p, **trade_res})
                        entered = True

                    # Judas Low Sweep -> Long Reversal (Manipulation down, Distribution up)
                    elif bl < asia_l and bc > asia_l and bc > bo:
                        entry_p = bc
                        sl_dist = max((entry_p - bl) + (2.0 * pip), 8.0 * pip)
                        sl_pips = sl_dist / pip
                        if sl_pips > 25.0: continue
                        tp_pips = max(sl_pips * 1.5, 12.0)
                        tp_p = entry_p + (tp_pips * pip)
                        sl_p = entry_p - sl_dist

                        trade_res = eval_trade(df, idx, "LONG", entry_p, sl_p, tp_p, pip, costs, sl_pips, tp_pips)
                        trades.append({"model": "Judas_Swing", "pair": p, **trade_res})
                        entered = True

        return pd.DataFrame(trades)

    # -------------------------------------------------------------------------
    # MODEL 2: London Opening Range Breakout (ORB 07:00 UTC) with 4H Trend
    # -------------------------------------------------------------------------
    def test_london_orb():
        trades = []
        for p in PAIRS:
            df = data[p]
            pip = CONFIGS[p]["pip"]
            spread = CONFIGS[p]["spread"]
            costs = spread + 0.5 + 0.35

            df_sub = df[(df["time"] >= "2026-04-01") & (df["time"] <= "2026-10-09")].copy()
            days = df_sub["time"].dt.date.unique()

            for day in days:
                day_bars = df_sub[df_sub["time"].dt.date == day]
                # Opening 30 minutes of London: 07:00 to 07:30 UTC (first 2 bars)
                orb_bars = day_bars[(day_bars["time"].dt.hour == 7) & (day_bars["time"].dt.minute < 30)]
                if len(orb_bars) < 2: continue

                orb_h = orb_bars["high"].max()
                orb_l = orb_bars["low"].min()
                orb_rng = (orb_h - orb_l) / pip
                if orb_rng < 6.0 or orb_rng > 25.0: continue

                # Look for breakout during London morning (07:30 to 11:00 UTC)
                eval_bars = day_bars[(day_bars["time"].dt.hour >= 7) & (day_bars["time"].dt.hour <= 11) & (day_bars["time"].dt.minute >= 30)]
                entered = False

                for idx, row in eval_bars.iterrows():
                    if entered: break
                    bc, bo = row["close"], row["open"]
                    h4_bull = row["h4_bull"]
                    h4_bear = row["h4_bear"]

                    if bc > orb_h and bc > bo and h4_bull:
                        entry_p = bc
                        sl_pips = orb_rng + 2.0
                        if sl_pips > 20.0: sl_pips = 20.0
                        if sl_pips < 8.0: sl_pips = 8.0
                        tp_pips = sl_pips * 1.5
                        sl_p = entry_p - (sl_pips * pip)
                        tp_p = entry_p + (tp_pips * pip)

                        trade_res = eval_trade(df, idx, "LONG", entry_p, sl_p, tp_p, pip, costs, sl_pips, tp_pips)
                        trades.append({"model": "London_ORB", "pair": p, **trade_res})
                        entered = True

                    elif bc < orb_l and bc < bo and h4_bear:
                        entry_p = bc
                        sl_pips = orb_rng + 2.0
                        if sl_pips > 20.0: sl_pips = 20.0
                        if sl_pips < 8.0: sl_pips = 8.0
                        tp_pips = sl_pips * 1.5
                        sl_p = entry_p + (sl_pips * pip)
                        tp_p = entry_p - (tp_pips * pip)

                        trade_res = eval_trade(df, idx, "SHORT", entry_p, sl_p, tp_p, pip, costs, sl_pips, tp_pips)
                        trades.append({"model": "London_ORB", "pair": p, **trade_res})
                        entered = True

        return pd.DataFrame(trades)

    # -------------------------------------------------------------------------
    # MODEL 3: Trend Pullback with Structural Fib / 20-EMA Retest & Model J Exit
    # -------------------------------------------------------------------------
    def test_structured_pullback():
        trades = []
        for p in PAIRS:
            df = data[p]
            pip = CONFIGS[p]["pip"]
            spread = CONFIGS[p]["spread"]
            costs = spread + 0.5 + 0.35
            n = len(df)

            for i in range(50, n):
                c = df.iloc[i]
                prev = df.iloc[i-1]
                t = c["time"]

                if t < pd.Timestamp("2026-04-01", tz="UTC"): continue
                if t > pd.Timestamp("2026-10-09 23:45:00", tz="UTC"): break
                if t.weekday() >= 5: continue

                hr = t.hour
                # High-volume Killzones: London 07-10 UTC, NY 12-15 UTC
                if not ((7 <= hr <= 10) or (12 <= hr <= 15)): continue

                close, open_p, h, l = float(c["close"]), float(c["open"]), float(c["high"]), float(c["low"])
                atr = float(c["atr"])
                adx_val = float(c["adx"])
                if adx_val < 22.0: continue

                plus_di, minus_di = float(c["plus_di"]), float(c["minus_di"])
                h1_bull, h1_bear = bool(c["h1_bull"]), bool(c["h1_bear"])
                h4_bull, h4_bear = bool(c["h4_bull"]), bool(c["h4_bear"])

                bullish_trend = (close > c["ema50"]) and (c["ema20"] > c["ema50"]) and (c["ema20_slope"] > 0) and h1_bull and h4_bull and (plus_di > minus_di)
                bearish_trend = (close < c["ema50"]) and (c["ema20"] < c["ema50"]) and (c["ema20_slope"] < 0) and h1_bear and h4_bear and (minus_di > plus_di)

                # Require a clean pullback into EMA 20 followed by a strong rejection bar
                long_setup = False
                short_setup = False

                if bullish_trend:
                    # Previous bar or current bar dipped to EMA20, current bar closes firmly green in top 35% of range
                    rng = (h - l) + 1e-9
                    dipped = (min(l, float(prev["low"])) <= c["ema20"])
                    strong_close = (close > open_p) and ((close - l) / rng >= 0.60)
                    rsi_ok = 45.0 <= c["rsi"] <= 72.0
                    if dipped and strong_close and rsi_ok:
                        long_setup = True

                elif bearish_trend:
                    rng = (h - l) + 1e-9
                    dipped = (max(h, float(prev["high"])) >= c["ema20"])
                    strong_close = (close < open_p) and ((h - close) / rng >= 0.60)
                    rsi_ok = 28.0 <= c["rsi"] <= 55.0
                    if dipped and strong_close and rsi_ok:
                        short_setup = True

                if long_setup:
                    entry_p = close
                    sl_dist = max((entry_p - min(l, float(prev["low"]))) + (1.5 * pip), 10.0 * pip)
                    sl_pips = sl_dist / pip
                    if sl_pips > 22.0: sl_pips = 22.0
                    tp_pips = sl_pips * 1.5
                    sl_p = entry_p - (sl_pips * pip)
                    tp_p = entry_p + (tp_pips * pip)

                    # Model J exit: bank 50% at 1.0R, move SL to BE, target 1.5R
                    trade_res = eval_model_j(df, i, "LONG", entry_p, sl_p, tp_p, pip, costs, sl_pips, tp_pips)
                    trades.append({"model": "Structured_Pullback_Model_J", "pair": p, **trade_res})

                elif short_setup:
                    entry_p = close
                    sl_dist = max((max(h, float(prev["high"])) - entry_p) + (1.5 * pip), 10.0 * pip)
                    sl_pips = sl_dist / pip
                    if sl_pips > 22.0: sl_pips = 22.0
                    tp_pips = sl_pips * 1.5
                    sl_p = entry_p + (sl_pips * pip)
                    tp_p = entry_p - (tp_pips * pip)

                    trade_res = eval_model_j(df, i, "SHORT", entry_p, sl_p, tp_p, pip, costs, sl_pips, tp_pips)
                    trades.append({"model": "Structured_Pullback_Model_J", "pair": p, **trade_res})

        return pd.DataFrame(trades)

    def eval_trade(df, start_i, direction, entry_p, sl_p, tp_p, pip, costs, sl_pips, tp_pips):
        n = len(df)
        for k in range(start_i + 1, min(n, start_i + 120)):
            bar = df.iloc[k]
            bh, bl = float(bar["high"]), float(bar["low"])
            if direction == "LONG":
                if bl <= sl_p:
                    return {"outcome": "LOSS", "realized_r": -1.0 - (costs/sl_pips), "net_pips": -sl_pips - costs}
                elif bh >= tp_p:
                    return {"outcome": "WIN", "realized_r": (tp_pips/sl_pips) - (costs/sl_pips), "net_pips": tp_pips - costs}
            else:
                if bh >= sl_p:
                    return {"outcome": "LOSS", "realized_r": -1.0 - (costs/sl_pips), "net_pips": -sl_pips - costs}
                elif bl <= tp_p:
                    return {"outcome": "WIN", "realized_r": (tp_pips/sl_pips) - (costs/sl_pips), "net_pips": tp_pips - costs}
        return {"outcome": "BREAKEVEN", "realized_r": 0.0, "net_pips": 0.0}

    def eval_model_j(df, start_i, direction, entry_p, sl_p, tp_p, pip, costs, sl_pips, tp_pips):
        n = len(df)
        partial_banked = False
        target_1r = entry_p + (sl_pips * pip) if direction == "LONG" else entry_p - (sl_pips * pip)
        be_sl = entry_p + (0.5 * pip) if direction == "LONG" else entry_p - (0.5 * pip)
        curr_sl = sl_p

        for k in range(start_i + 1, min(n, start_i + 120)):
            bar = df.iloc[k]
            bh, bl = float(bar["high"]), float(bar["low"])

            if not partial_banked:
                if direction == "LONG":
                    if bl <= curr_sl:
                        return {"outcome": "LOSS", "realized_r": -1.0 - (costs/sl_pips), "net_pips": -sl_pips - costs}
                    elif bh >= target_1r:
                        partial_banked = True
                        curr_sl = be_sl
                else:
                    if bh >= curr_sl:
                        return {"outcome": "LOSS", "realized_r": -1.0 - (costs/sl_pips), "net_pips": -sl_pips - costs}
                    elif bl <= target_1r:
                        partial_banked = True
                        curr_sl = be_sl
            else:
                # Banked 50% at 1.0R
                if direction == "LONG":
                    if bh >= tp_p:
                        # 50% at 1.0R, 50% at 1.5R = +1.25R
                        return {"outcome": "WIN", "realized_r": 1.25 - (costs/sl_pips), "net_pips": (sl_pips*1.25) - costs}
                    elif bl <= curr_sl:
                        # 50% at 1.0R, 50% at 0 = +0.50R
                        return {"outcome": "WIN", "realized_r": 0.50 - (costs/sl_pips), "net_pips": (sl_pips*0.50) - costs}
                else:
                    if bl <= tp_p:
                        return {"outcome": "WIN", "realized_r": 1.25 - (costs/sl_pips), "net_pips": (sl_pips*1.25) - costs}
                    elif bh >= curr_sl:
                        return {"outcome": "WIN", "realized_r": 0.50 - (costs/sl_pips), "net_pips": (sl_pips*0.50) - costs}

        return {"outcome": "BREAKEVEN", "realized_r": 0.0, "net_pips": 0.0}

    print("\nTesting Model 1: ICT AMD Judas Swing...")
    df_m1 = test_judas_swing()
    print_report(df_m1, "MODEL 1: ICT AMD Judas Swing (Asian Sweep Reversal)")

    print("\nTesting Model 2: London Opening Range Breakout (ORB)...")
    df_m2 = test_london_orb()
    print_report(df_m2, "MODEL 2: London Opening Range Breakout (ORB)")

    print("\nTesting Model 3: Structured Pullback with Model J...")
    df_m3 = test_structured_pullback()
    print_report(df_m3, "MODEL 3: Structured Pullback + Model J Execution")

def print_report(df_t, name):
    if df_t.empty:
        print(f"[{name}] No trades.")
        return
    tot = len(df_t)
    w = len(df_t[df_t["outcome"] == "WIN"])
    l = len(df_t[df_t["outcome"] == "LOSS"])
    be = len(df_t[df_t["outcome"] == "BREAKEVEN"])
    wr = (w / tot) * 100.0
    net_r = df_t["realized_r"].sum()
    net_pips = df_t["net_pips"].sum()
    gw = df_t[df_t["realized_r"] > 0]["realized_r"].sum()
    gl = abs(df_t[df_t["realized_r"] < 0]["realized_r"].sum())
    pf = (gw / gl) if gl > 0 else 99.0
    exp_r = net_r / tot

    print(f"\n{'='*75}")
    print(f"{name}")
    print(f"{'='*75}")
    print(f"Trades: {tot} | Wins: {w} | Losses: {l} | Breakevens: {be}")
    print(f"WIN RATE: {wr:.2f}%")
    print(f"Net R: {net_r:+6.2f}R | Expectancy: {exp_r:+.3f}R | Profit Factor: {pf:.2f}")
    print(f"Net Pips: {net_pips:+8.1f} pips")

    # Per pair breakdown
    for p in PAIRS:
        sub = df_t[df_t["pair"] == p]
        if sub.empty: continue
        p_w = len(sub[sub["outcome"] == "WIN"])
        p_wr = (p_w / len(sub)) * 100.0
        p_r = sub["realized_r"].sum()
        p_pf = (sub[sub["realized_r"] > 0]["realized_r"].sum() / abs(sub[sub["realized_r"] < 0]["realized_r"].sum())) if abs(sub[sub["realized_r"] < 0]["realized_r"].sum()) > 0 else 99.0
        print(f"  {p:8s}: {len(sub):3d} tr | WR: {p_wr:5.1f}% | Net R: {p_r:+6.2f}R | PF: {p_pf:.2f}")

if __name__ == "__main__":
    run_quant_alpha_exploration()
