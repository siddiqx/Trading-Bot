import sys
import os
sys.path.insert(0, os.path.abspath("."))
import datetime
import numpy as np
import pandas as pd
from market_scanner import fetch_candles, SYMBOLS
from core.config import CCRS_LOOKBACK_HOURS, CCRS_Z_WINDOW_HOURS

print("Fetching 60d data for 6 pairs...")
dfs = {}
for p, cfg in SYMBOLS.items():
    d = fetch_candles(cfg["ticker"], "1h", range_days="60d")
    d["time"] = pd.to_datetime(d["time"], utc=True)
    d["close_time"] = d["time"] + pd.Timedelta(hours=1)
    dfs[p] = d.set_index("time")["close"]

panel = pd.DataFrame(dfs).dropna()
print(f"Panel shape: {panel.shape}")

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

today_div = div[div.index >= "2026-11-03 00:00:00"]
print("\n=== HOURLY CCRS ORDER FLOW DIVERGENCE (NOV 3, 2026) ===")
for t, row in today_div.iterrows():
    div_str = ", ".join([f"{k}: {row[k]:+.2f}s" for k in ['EURUSD', 'GBPUSD', 'AUDUSD', 'USDCAD', 'USDJPY', 'USDCHF']])
    qual = [f"{k} ({row[k]:+.2f}s)" for k in ['EURUSD', 'GBPUSD', 'AUDUSD', 'USDCAD', 'USDJPY', 'USDCHF'] if abs(row[k]) >= 2.0]
    q_str = f"QUALIFIED: {qual}" if qual else "Neutral (all < 2.0s)"
    print(f"{t.strftime('%H:%M UTC')} | {div_str} | {q_str}")
