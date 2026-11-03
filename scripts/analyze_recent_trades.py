import sys
import os
sys.path.insert(0, os.path.abspath("."))
import datetime
import pandas as pd
from market_scanner import fetch_candles

print("=== FORENSIC ANALYSIS OF RECENT TRADES ===")
now = datetime.datetime.now(datetime.timezone.utc)
print("Current time:", now)

trades = [
    {"pair": "EURUSD", "ticker": "EURUSD=X", "entry": 1.12082, "direction": "SHORT", "sl": 1.12432, "tp": 1.11557},
    {"pair": "AUDUSD", "ticker": "AUDUSD=X", "entry": 0.70121, "direction": "SHORT", "sl": 0.70471, "tp": 0.69596},
]

for tr in trades:
    pair = tr["pair"]
    entry = tr["entry"]
    sl = tr["sl"]
    tp = tr["tp"]
    direction = tr["direction"]
    pip = 0.0001
    
    df = fetch_candles(tr["ticker"], "1h", range_days="5d")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    sub = df[df["time"] >= "2026-11-02 11:00:00"].copy()
    
    print("\n" + "=" * 60)
    print(f"--- {pair} {direction} (Entry: {entry}, SL: {sl}, TP: {tp}) ---")
    print(f"Total 1H bars since entry: {len(sub)}")
    
    max_adv_pips = 0.0
    max_fav_pips = 0.0
    max_adv_time = None
    max_fav_time = None
    
    for idx, row in sub.iterrows():
        t = row["time"]
        h = row["high"]
        l = row["low"]
        c = row["close"]
        
        adv_pips = (h - entry) / pip
        fav_pips = (entry - l) / pip
        
        if adv_pips > max_adv_pips:
            max_adv_pips = adv_pips
            max_adv_time = t
        if fav_pips > max_fav_pips:
            max_fav_pips = fav_pips
            max_fav_time = t
            
        t_str = t.strftime("%Y-%m-%d %H:%M")
        print(f"{t_str} | Open: {row['open']:.5f} | High: {h:.5f} (drawdown: {adv_pips:+.1f}p) | Low: {l:.5f} (profit: {fav_pips:+.1f}p) | Close: {c:.5f}")
        
    print("\nSummary for " + pair + ":")
    print(f"Max Adverse Excursion (Drawdown): +{max_adv_pips:.1f} pips at {max_adv_time}")
    print(f"Max Favorable Excursion (Profit peak): +{max_fav_pips:.1f} pips at {max_fav_time}")
    current_close = sub.iloc[-1]["close"]
    current_pnl_pips = (entry - current_close) / pip
    print(f"Current Price: {current_close:.5f} | Floating PnL: {current_pnl_pips:+.1f} pips")
