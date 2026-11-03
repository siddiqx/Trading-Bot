import sys
import os
sys.path.insert(0, os.path.abspath("."))
import datetime
import pandas as pd
import numpy as np
from market_scanner import fetch_candles, SYMBOLS, CCRS_LOOKBACK_HOURS, CCRS_Z_WINDOW_HOURS, CCRS_Z_THRESHOLD

print("=== BACKTESTING TP / SL CONFIGURATIONS ACROSS 6 FOREX PAIRS ===")

# 1. Fetch 60-day / 90-day 1H candle panel
pair_dfs = {}
for p, cfg in SYMBOLS.items():
    df = fetch_candles(cfg["ticker"], "1h", range_days="60d")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df.sort_values("time", inplace=True)
    df.reset_index(drop=True, inplace=True)
    pair_dfs[p] = df

# Align close panel for CCRS
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

# Find all CCRS trigger events
signals = []
for i in range(1, len(div)):
    t = div.index[i]
    # Filter institutional hours (07:00 - 17:00 UTC)
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
                "time": t,
                "pair": p,
                "direction": "LONG" if long_sig else "SHORT",
                "divergence": d_cur,
            })

print(f"Total raw CCRS signals identified: {len(signals)}")

# Test different TP/SL configurations
configs_to_test = [
    {"name": "Current Canonical (35p SL / 52.5p TP)", "sl": 35.0, "tp": 52.5, "rr": 1.50},
    {"name": "Medium-Swing (25p SL / 37.5p TP)", "sl": 25.0, "tp": 37.5, "rr": 1.50},
    {"name": "Standard Intraday (20p SL / 30.0p TP)", "sl": 20.0, "tp": 30.0, "rr": 1.50},
    {"name": "Responsive Intraday (18p SL / 27.0p TP)", "sl": 18.0, "tp": 27.0, "rr": 1.50},
    {"name": "Tight Scalp (15p SL / 22.5p TP)", "sl": 15.0, "tp": 22.5, "rr": 1.50},
    {"name": "Asymmetric 1:1.25 (20p SL / 25.0p TP)", "sl": 20.0, "tp": 25.0, "rr": 1.25},
]

# Simulate trades with pessimistic bar assumptions (SL checked before TP)
results = []
spread_pips = 1.2  # Real institutional spread + slippage

for cfg in configs_to_test:
    sl_pips = cfg["sl"]
    tp_pips = cfg["tp"]
    rr = cfg["rr"]
    name = cfg["name"]
    
    wins = 0
    losses = 0
    timeouts = 0
    net_r = 0.0
    durations = []
    
    for sig in signals:
        p = sig["pair"]
        t_entry = sig["time"]
        direction = sig["direction"]
        pip = SYMBOLS[p]["pip"]
        df_p = pair_dfs[p]
        
        # Find entry candle
        entry_idx = df_p[df_p["time"] == t_entry].index
        if len(entry_idx) == 0 or entry_idx[0] >= len(df_p) - 1:
            continue
        idx0 = entry_idx[0]
        
        entry_price = df_p.iloc[idx0]["close"]
        if direction == "LONG":
            sl_price = entry_price - (sl_pips * pip)
            tp_price = entry_price + (tp_pips * pip)
        else:
            sl_price = entry_price + (sl_pips * pip)
            tp_price = entry_price - (tp_pips * pip)
            
        outcome = None
        bars_held = 0
        
        for k in range(idx0 + 1, min(idx0 + 49, len(df_p))):
            bars_held += 1
            bar = df_p.iloc[k]
            h = bar["high"]
            l = bar["low"]
            
            if direction == "LONG":
                # Pessimistic: check SL first
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
            net_r += rr
            durations.append(bars_held)
        elif outcome == "LOSS":
            losses += 1
            net_r -= 1.0
            durations.append(bars_held)
        else:
            timeouts += 1
            
    total = wins + losses
    wr = (wins / total * 100) if total > 0 else 0.0
    ev = (net_r / total) if total > 0 else 0.0
    avg_dur = np.mean(durations) if durations else 0.0
    
    results.append({
        "Configuration": name,
        "Trades": total,
        "Wins": wins,
        "Losses": losses,
        "Win Rate": f"{wr:.1f}%",
        "Net R": f"{net_r:+.2f}R",
        "Expectancy": f"{ev:+.2f}R",
        "Avg Hold (Hours)": f"{avg_dur:.1f}h",
        "Timeouts (>48h)": timeouts
    })

print("\n--- 2. SIMULATION RESULTS TABLE ---")
df_res = pd.DataFrame(results)
print(df_res.to_string(index=False))
