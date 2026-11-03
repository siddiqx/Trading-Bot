import sys
import os
sys.path.insert(0, os.path.abspath("."))
import datetime
import pandas as pd
import numpy as np
from market_scanner import fetch_candles, SYMBOLS, CCRS_LOOKBACK_HOURS, CCRS_Z_WINDOW_HOURS, CCRS_Z_THRESHOLD

print("=== DEEP RESEARCH: TARGET REALISM, PARTIAL TP, & DYNAMIC ATR SCALING ===")

# Load panel
pair_dfs = {}
for p, cfg in SYMBOLS.items():
    df = fetch_candles(cfg["ticker"], "1h", range_days="60d")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df.sort_values("time", inplace=True)
    df.reset_index(drop=True, inplace=True)
    pair_dfs[p] = df

dfs = {p: df.set_index("time")["close"] for p, df in pair_dfs.items()}
panel = pd.DataFrame(dfs).dropna()

lb = CCRS_LOOKBACK_HOURS
ret_eur = np.log(panel["EURUSD"] / panel["EURUSD"].shift(lb))
ret_gbp = np.log(panel["GBPUSD"] / panel["GBPUSD"].shift(lb))
ret_aud = np.log(panel["AUDUSD"] / panel["AUDUSD"].shift(lb))
ret_jpy = -np.log(panel["USDJPY"] / panel["USDJPY"].shift(lb))
ret_cad = -np.log(panel["USDCAD"] / panel["USDCAD"].shift(lb))
ret_chf = -np.log(panel["USDCHF"] / panel["USDCHF"].shift(lb))
ret_usd = -(ret_eur + ret_gbp + ret_aud + ret_jpy + ret_cad + ret_chf) / 6.0

curr_returns = pd.DataFrame({
    "EUR": ret_eur, "GBP": ret_gbp, "AUD": ret_aud,
    "JPY": ret_jpy, "CAD": ret_cad, "CHF": ret_chf, "USD": ret_usd
})
z_scores = (curr_returns - curr_returns.rolling(CCRS_Z_WINDOW_HOURS).mean()) / (curr_returns.rolling(CCRS_Z_WINDOW_HOURS).std() + 1e-9)

div = pd.DataFrame(index=panel.index)
div["EURUSD"] = z_scores["EUR"] - z_scores["USD"]
div["GBPUSD"] = z_scores["GBP"] - z_scores["USD"]
div["AUDUSD"] = z_scores["AUD"] - z_scores["USD"]
div["USDJPY"] = z_scores["USD"] - z_scores["JPY"]
div["USDCAD"] = z_scores["USD"] - z_scores["CAD"]
div["USDCHF"] = z_scores["USD"] - z_scores["CHF"]

signals = []
for i in range(1, len(div)):
    t = div.index[i]
    if not (7 <= t.hour <= 17):
        continue
    for p in SYMBOLS.keys():
        d_cur = div[p].iloc[i]
        d_prev = div[p].iloc[i - 1]
        if np.isnan(d_cur) or np.isnan(d_prev):
            continue
        long_sig = (d_cur >= CCRS_Z_THRESHOLD) and (d_prev < CCRS_Z_THRESHOLD)
        short_sig = (d_cur <= -CCRS_Z_THRESHOLD) and (d_prev > -CCRS_Z_THRESHOLD)
        if long_sig or short_sig:
            signals.append({
                "time": t, "pair": p,
                "direction": "LONG" if long_sig else "SHORT",
            })

# Let's test exit architectures:
# Model 1: Current Canonical 35p SL / 52.5p TP (1:1.50)
# Model 2: Calibrated Swing 22p SL / 33.0p TP (1:1.50)
# Model 3: Calibrated Swing 20p SL / 30.0p TP (1:1.50)
# Model 4: Dynamic ATR (1.5x ATR SL, bounded 18-28p, TP = 1.5x SL)
# Model 5: Two-Tier Partial TP: 50% banked at 1.0R (22p), SL moved to BE, 50% runner to 1.5R (33p)
# Model 6: Two-Tier Partial TP with Limit Entry at 3.0p Pullback

exit_models = [
    {"name": "1. Current Canonical (35p SL / 52.5p TP, Market)", "sl": 35.0, "tp": 52.5, "partial": False, "pb": 0.0},
    {"name": "2. Calibrated Swing (22p SL / 33.0p TP, Market)", "sl": 22.0, "tp": 33.0, "partial": False, "pb": 0.0},
    {"name": "3. Calibrated Swing (20p SL / 30.0p TP, Market)", "sl": 20.0, "tp": 30.0, "partial": False, "pb": 0.0},
    {"name": "4. Calibrated Swing (22p SL / 33.0p TP, 3.0p Retest Limit)", "sl": 22.0, "tp": 33.0, "partial": False, "pb": 3.0},
    {"name": "5. Two-Tier Exit (50% @ 1.0R, BE lock, 50% @ 1.5R, Market)", "sl": 22.0, "tp": 33.0, "partial": True, "pb": 0.0},
    {"name": "6. Two-Tier Exit + 3.0p Retest Limit Entry", "sl": 22.0, "tp": 33.0, "partial": True, "pb": 3.0},
]

summary = []

for em in exit_models:
    name = em["name"]
    sl_base = em["sl"]
    tp_base = em["tp"]
    use_partial = em["partial"]
    pb = em["pb"]
    
    wins = 0
    losses = 0
    be_scratches = 0
    partial_wins = 0
    full_wins = 0
    net_r = 0.0
    durations = []
    
    for sig in signals:
        p = sig["pair"]
        t_entry = sig["time"]
        direction = sig["direction"]
        pip = SYMBOLS[p]["pip"]
        df_p = pair_dfs[p]
        
        entry_idx = df_p[df_p["time"] == t_entry].index
        if len(entry_idx) == 0 or entry_idx[0] >= len(df_p) - 1:
            continue
        idx0 = entry_idx[0]
        close_price = df_p.iloc[idx0]["close"]
        
        # Check fill
        if pb == 0.0:
            is_filled = True
            fill_idx = idx0 + 1
            actual_entry = close_price
        else:
            is_filled = False
            desired = close_price - (pb * pip) if direction == "LONG" else close_price + (pb * pip)
            for k in range(idx0 + 1, min(idx0 + 4, len(df_p))):
                bar = df_p.iloc[k]
                if (direction == "LONG" and bar["low"] <= desired) or (direction == "SHORT" and bar["high"] >= desired):
                    is_filled = True
                    fill_idx = k
                    actual_entry = desired
                    break
            if not is_filled:
                continue
                
        sl_price = actual_entry - (sl_base * pip) if direction == "LONG" else actual_entry + (sl_base * pip)
        tp_price = actual_entry + (tp_base * pip) if direction == "LONG" else actual_entry - (tp_base * pip)
        tp1_price = actual_entry + (sl_base * pip) if direction == "LONG" else actual_entry - (sl_base * pip)  # 1.0R
        
        be_locked = False
        partial_banked = False
        trade_r = 0.0
        closed = False
        bars_held = 0
        
        for k in range(fill_idx, min(fill_idx + 48, len(df_p))):
            bars_held += 1
            bar = df_p.iloc[k]
            h = bar["high"]
            l = bar["low"]
            
            if not use_partial:
                # Binary direct execution
                if direction == "LONG":
                    if l <= sl_price:
                        trade_r = -1.0
                        closed = True
                        break
                    if h >= tp_price:
                        trade_r = 1.50
                        closed = True
                        break
                else:
                    if h >= sl_price:
                        trade_r = -1.0
                        closed = True
                        break
                    if l <= tp_price:
                        trade_r = 1.50
                        closed = True
                        break
            else:
                # Two-tier partial model
                if direction == "LONG":
                    # Check SL
                    curr_sl = actual_entry if be_locked else sl_price
                    if l <= curr_sl:
                        if partial_banked:
                            # 50% was banked at +1.0R (+0.50R net), remainder stopped at BE (0.0R)
                            trade_r = 0.50
                            be_scratches += 1
                        else:
                            trade_r = -1.0
                        closed = True
                        break
                    # Check TP1 (1.0R)
                    if not partial_banked and h >= tp1_price:
                        partial_banked = True
                        be_locked = True
                        partial_wins += 1
                    # Check TP2 (1.5R)
                    if h >= tp_price:
                        trade_r = 1.25  # (0.5 * 1.0) + (0.5 * 1.5) = 1.25R
                        full_wins += 1
                        closed = True
                        break
                else:
                    curr_sl = actual_entry if be_locked else sl_price
                    if h >= curr_sl:
                        if partial_banked:
                            trade_r = 0.50
                            be_scratches += 1
                        else:
                            trade_r = -1.0
                        closed = True
                        break
                    if not partial_banked and l <= tp1_price:
                        partial_banked = True
                        be_locked = True
                        partial_wins += 1
                    if l <= tp_price:
                        trade_r = 1.25
                        full_wins += 1
                        closed = True
                        break
                        
        if closed:
            net_r += trade_r
            durations.append(bars_held)
            if trade_r > 0:
                wins += 1
            elif trade_r < 0:
                losses += 1
                
    tot = wins + losses
    wr = (wins / tot * 100) if tot > 0 else 0.0
    ev = (net_r / tot) if tot > 0 else 0.0
    
    summary.append({
        "Model": name,
        "Total Closed": tot,
        "Wins": wins,
        "Losses": losses,
        "Win Rate": f"{wr:.1f}%",
        "Net Profit (R)": f"{net_r:+.2f}R",
        "Expectancy/Trade": f"{ev:+.2f}R",
        "Avg Duration": f"{np.mean(durations):.1f}h" if durations else "0.0h"
    })

print("\n--- COMPARATIVE ARCHITECTURAL AUDIT ---")
df_sum = pd.DataFrame(summary)
print(df_sum.to_string(index=False))
