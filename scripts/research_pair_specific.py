import sys
import os
sys.path.insert(0, os.path.abspath("."))
import datetime
import pandas as pd
import numpy as np
from market_scanner import fetch_candles, SYMBOLS, CCRS_LOOKBACK_HOURS, CCRS_Z_WINDOW_HOURS, CCRS_Z_THRESHOLD

print("=== TESTING PAIR-SPECIFIC VOLATILITY-ALIGNED EXITS ===")

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

# Pair-specific calibrated exits (based on individual pair ADR and 1H ATR)
pair_calibrations = {
    "EURUSD": {"sl": 24.0, "tp": 36.0},  # ADR 67p: 36p is ~53% of ADR (ideal)
    "AUDUSD": {"sl": 18.0, "tp": 27.0},  # ADR 51p: 27p is ~53% of ADR (ideal)
    "GBPUSD": {"sl": 26.0, "tp": 39.0},  # ADR 78p: 39p is ~50% of ADR (ideal)
    "USDJPY": {"sl": 30.0, "tp": 45.0},  # ADR 96p: 45p is ~47% of ADR (ideal)
    "USDCAD": {"sl": 24.0, "tp": 36.0},  # ADR 65p: 36p is ~55% of ADR (ideal)
    "USDCHF": {"sl": 22.0, "tp": 33.0},  # ADR 58p: 33p is ~56% of ADR (ideal)
}

test_models = [
    {"name": "1. Baseline Canonical (Static 35p SL / 52.5p TP)", "mode": "static_35"},
    {"name": "2. Uniform Calibrated (Static 25p SL / 37.5p TP)", "mode": "static_25"},
    {"name": "3. Uniform Calibrated (Static 22p SL / 33.0p TP)", "mode": "static_22"},
    {"name": "4. Pair-Specific Volatility-Anchored (18p - 30p SL / 27p - 45p TP)", "mode": "pair_specific"},
    {"name": "5. Pair-Specific + 3.0p Retest Limit Order", "mode": "pair_specific_limit"},
]

results = []

for tm in test_models:
    name = tm["name"]
    mode = tm["mode"]
    
    wins = 0
    losses = 0
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
        
        # Determine SL and TP
        if mode == "static_35":
            sl_pips = 35.0
            tp_pips = 52.5
            pb = 0.0
        elif mode == "static_25":
            sl_pips = 25.0
            tp_pips = 37.5
            pb = 0.0
        elif mode == "static_22":
            sl_pips = 22.0
            tp_pips = 33.0
            pb = 0.0
        elif mode == "pair_specific":
            sl_pips = pair_calibrations[p]["sl"]
            tp_pips = pair_calibrations[p]["tp"]
            pb = 0.0
        elif mode == "pair_specific_limit":
            sl_pips = pair_calibrations[p]["sl"]
            tp_pips = pair_calibrations[p]["tp"]
            pb = 3.0
            
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
                
        sl_price = actual_entry - (sl_pips * pip) if direction == "LONG" else actual_entry + (sl_pips * pip)
        tp_price = actual_entry + (tp_pips * pip) if direction == "LONG" else actual_entry - (tp_pips * pip)
        
        outcome = None
        for k in range(fill_idx, min(fill_idx + 48, len(df_p))):
            bar = df_p.iloc[k]
            h = bar["high"]
            l = bar["low"]
            
            if direction == "LONG":
                if l <= sl_price:
                    outcome = "LOSS"
                    break
                if h >= tp_price:
                    outcome = "WIN"
                    break
            else:
                if h >= sl_price:
                    outcome = "LOSS"
                    break
                if l <= tp_price:
                    outcome = "WIN"
                    break
                    
        if outcome == "WIN":
            wins += 1
            net_r += 1.50
            durations.append(k - fill_idx)
        elif outcome == "LOSS":
            losses += 1
            net_r -= 1.00
            durations.append(k - fill_idx)
            
    tot = wins + losses
    wr = (wins / tot * 100) if tot > 0 else 0.0
    ev = (net_r / tot) if tot > 0 else 0.0
    
    results.append({
        "Model": name,
        "Closed Trades": tot,
        "Wins": wins,
        "Losses": losses,
        "Win Rate": f"{wr:.1f}%",
        "Net Profit (R)": f"{net_r:+.2f}R",
        "Expectancy": f"{ev:+.2f}R",
        "Avg Duration": f"{np.mean(durations):.1f}h" if durations else "0.0h"
    })

print("\n--- RESULTS ---")
df_res = pd.DataFrame(results)
print(df_res.to_string(index=False))
