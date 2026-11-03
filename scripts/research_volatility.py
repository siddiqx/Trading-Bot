import sys
import os
sys.path.insert(0, os.path.abspath("."))
import datetime
import pandas as pd
import numpy as np
from market_scanner import fetch_candles, SYMBOLS

print("=== QUANTITATIVE RESEARCH: ATR, ADR, AND PIP TARGET DISTRIBUTIONS ===")

# 1. Compute Daily ADR and 1H ATR across all 6 pairs
print("\n--- 1. VOLATILITY METRICS (30-DAY & 60-DAY DAILY ATR) ---")
adr_data = []
for p, cfg in SYMBOLS.items():
    ticker = cfg["ticker"]
    pip = cfg["pip"]
    
    # Fetch 1D candles for ADR
    df_d = fetch_candles(ticker, "1d", range_days="60d")
    df_d["tr"] = np.maximum(
        df_d["high"] - df_d["low"],
        np.maximum(
            abs(df_d["high"] - df_d["close"].shift(1)),
            abs(df_d["low"] - df_d["close"].shift(1))
        )
    )
    adr_14 = (df_d["tr"].tail(14).mean()) / pip
    adr_30 = (df_d["tr"].tail(30).mean()) / pip
    
    # Fetch 1H candles for 1H ATR
    df_1h = fetch_candles(ticker, "1h", range_days="30d")
    df_1h["tr"] = np.maximum(
        df_1h["high"] - df_1h["low"],
        np.maximum(
            abs(df_1h["high"] - df_1h["close"].shift(1)),
            abs(df_1h["low"] - df_1h["close"].shift(1))
        )
    )
    atr_1h_14 = (df_1h["tr"].tail(14).mean()) / pip
    atr_1h_30 = (df_1h["tr"].tail(200).mean()) / pip
    
    adr_data.append({
        "Pair": p,
        "ADR 14D (pips)": round(adr_14, 1),
        "ADR 30D (pips)": round(adr_30, 1),
        "1H ATR (pips)": round(atr_1h_30, 1),
        "50p as % of ADR": f"{round((50.0 / adr_30) * 100, 1)}%",
        "30p as % of ADR": f"{round((30.0 / adr_30) * 100, 1)}%",
        "25p as % of ADR": f"{round((25.0 / adr_30) * 100, 1)}%",
    })

df_adr = pd.DataFrame(adr_data)
print(df_adr.to_string(index=False))
