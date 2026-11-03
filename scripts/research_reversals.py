import sys
import os
sys.path.insert(0, os.path.abspath("."))
import datetime
import pandas as pd
from market_scanner import fetch_candles

print("=== DEEP DIVE: RETRACEMENT & ENTRY PRICE INVESTIGATION ===")

for pair, ticker, entry, t_start in [
    ("EURUSD", "EURUSD=X", 1.12082, "2026-11-02 10:00:00"),
    ("AUDUSD", "AUDUSD=X", 0.70121, "2026-11-02 10:00:00")
]:
    print(f"\n--- {pair} 15M Chart around Entry ({t_start}) ---")
    df = fetch_candles(ticker, "15m", range_days="3d")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    sub = df[(df["time"] >= "2026-11-02 10:00:00") & (df["time"] <= "2026-11-02 16:00:00")].copy()
    pip = 0.0001
    
    for idx, row in sub.iterrows():
        t_str = row["time"].strftime("%H:%M")
        adv = (row["high"] - entry) / pip
        fav = (entry - row["low"]) / pip
        print(f"15M {t_str} | O: {row['open']:.5f} | H: {row['high']:.5f} (+{adv:+.1f}p adv) | L: {row['low']:.5f} (+{fav:+.1f}p fav) | C: {row['close']:.5f}")
