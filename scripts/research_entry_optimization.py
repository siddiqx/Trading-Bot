import sys
import os
sys.path.insert(0, os.path.abspath("."))
import datetime
import pandas as pd
import numpy as np
from market_scanner import fetch_candles, SYMBOLS, CCRS_LOOKBACK_HOURS, CCRS_Z_WINDOW_HOURS, CCRS_Z_THRESHOLD

print("=== RESEARCH: RETEST / PULLBACK LIMIT ENTRIES VS MARKET ENTRIES ===")

# Load cached or fetched panel
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

print(f"Total raw signals: {len(signals)}")

entry_models = [
    {"name": "Market Entry at Bar Close (0p Pullback)", "pullback_pips": 0.0, "sl": 25.0, "tp": 37.5, "rr": 1.50},
    {"name": "Limit Entry at 3.0p Pullback", "pullback_pips": 3.0, "sl": 25.0, "tp": 37.5, "rr": 1.50},
    {"name": "Limit Entry at 5.0p Pullback (OTE / Re-test)", "pullback_pips": 5.0, "sl": 22.0, "tp": 33.0, "rr": 1.50},
    {"name": "Limit Entry at 7.0p Pullback (Deep Discount)", "pullback_pips": 7.0, "sl": 20.0, "tp": 30.0, "rr": 1.50},
    {"name": "Limit Entry at 50% Candle Retest", "pullback_mode": "candle_50", "sl": 22.0, "tp": 33.0, "rr": 1.50},
]

results = []
for em in entry_models:
    name = em["name"]
    pb_fixed = em.get("pullback_pips", 0.0)
    pb_mode = em.get("pullback_mode", "fixed")
    sl_pips = em["sl"]
    tp_pips = em["tp"]
    rr = em["rr"]
    
    filled = 0
    unfilled = 0
    wins = 0
    losses = 0
    net_r = 0.0
    
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
        
        trigger_bar = df_p.iloc[idx0]
        close_price = trigger_bar["close"]
        
        # Calculate desired entry price
        if pb_mode == "candle_50":
            # 50% midpoint of the trigger candle
            desired_pb = abs(trigger_bar["high"] - trigger_bar["low"]) * 0.50 / pip
            desired_pb = max(2.0, min(10.0, desired_pb))
        else:
            desired_pb = pb_fixed
            
        if direction == "LONG":
            desired_entry = close_price - (desired_pb * pip)
        else:
            desired_entry = close_price + (desired_pb * pip)
            
        # Check if limit order gets filled within next 3 bars (3 hours)
        is_filled = False
        fill_bar_idx = None
        
        if desired_pb == 0.0:
            is_filled = True
            fill_bar_idx = idx0 + 1
            actual_entry = close_price
        else:
            for k in range(idx0 + 1, min(idx0 + 4, len(df_p))):
                bar = df_p.iloc[k]
                if direction == "LONG" and bar["low"] <= desired_entry:
                    is_filled = True
                    fill_bar_idx = k
                    actual_entry = desired_entry
                    break
                elif direction == "SHORT" and bar["high"] >= desired_entry:
                    is_filled = True
                    fill_bar_idx = k
                    actual_entry = desired_entry
                    break
                    
        if not is_filled:
            unfilled += 1
            continue
            
        filled += 1
        
        # Now track trade from fill_bar_idx forward
        if direction == "LONG":
            sl_price = actual_entry - (sl_pips * pip)
            tp_price = actual_entry + (tp_pips * pip)
        else:
            sl_price = actual_entry + (sl_pips * pip)
            tp_price = actual_entry - (tp_pips * pip)
            
        outcome = None
        for k in range(fill_bar_idx, min(fill_bar_idx + 48, len(df_p))):
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
            net_r += rr
        elif outcome == "LOSS":
            losses += 1
            net_r -= 1.0
            
    total = wins + losses
    fill_rate = (filled / len(signals)) * 100
    wr = (wins / total * 100) if total > 0 else 0.0
    ev = (net_r / total) if total > 0 else 0.0
    
    results.append({
        "Entry Model": name,
        "Total Signals": len(signals),
        "Filled Trades": filled,
        "Fill Rate": f"{fill_rate:.1f}%",
        "Wins": wins,
        "Losses": losses,
        "Win Rate": f"{wr:.1f}%",
        "Net R": f"{net_r:+.2f}R",
        "Expectancy": f"{ev:+.2f}R",
    })

print("\n--- 3. ENTRY OPTIMIZATION RESULTS TABLE ---")
df_res = pd.DataFrame(results)
print(df_res.to_string(index=False))
