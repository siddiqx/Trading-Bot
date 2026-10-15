import json
import pandas as pd
import numpy as np
import httpx
from datetime import datetime, timezone

with open("trade_records.json", "r") as f:
    records = json.load(f)

completed = records["completed_trades"]

def fetch_candles(ticker, start_dt, end_dt):
    # Fetch 5m or 15m candles covering the trade duration
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={int(start_dt.timestamp())-7200}&period2={int(end_dt.timestamp())+7200}&interval=5m"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = httpx.get(url, headers=headers, timeout=10.0)
        if res.status_code == 200:
            data = res.json()["chart"]["result"][0]
            timestamps = data["timestamp"]
            quotes = data["indicators"]["quote"][0]
            df = pd.DataFrame({
                "time": pd.to_datetime(timestamps, unit="s", utc=True),
                "open": quotes["open"],
                "high": quotes["high"],
                "low": quotes["low"],
                "close": quotes["close"]
            }).dropna()
            return df
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
    return pd.DataFrame()

print(f"{'#':2s} | {'Pair':6s} | {'Dir':5s} | {'Opened (UTC)':16s} | {'Closed (UTC)':16s} | {'Outcome':10s} | {'SL(p)':5s} | {'TP(p)':5s} | {'RealPips':8s} | {'MFE(p)':7s} | {'MAE(p)':7s} | {'Loss Reason'}")
print("-" * 115)

for idx, t in enumerate(completed, 1):
    sym = t.get("symbol") or t.get("pair")
    direction = t.get("direction")
    entry = float(t.get("entry"))
    sl = float(t.get("stop_loss"))
    tp = float(t.get("take_profit"))
    sl_pips = float(t.get("sl_pips", 10.0))
    tp_pips = float(t.get("tp_pips", 15.0))
    outcome = t.get("outcome")
    real_pips = float(t.get("realized_pips") or 0.0)
    pip = 0.01 if "JPY" in sym else 0.0001

    open_str = t.get("opened_at")
    close_str = t.get("closed_at") or open_str
    open_dt = datetime.fromisoformat(open_str.replace("Z", "+00:00"))
    close_dt = datetime.fromisoformat(close_str.replace("Z", "+00:00"))

    ticker = t.get("ticker") or f"{sym}=X"
    df = fetch_candles(ticker, open_dt, close_dt)

    mfe_pips = 0.0
    mae_pips = 0.0
    reason = "Normal"

    if not df.empty:
        df_trade = df[(df["time"] >= open_dt) & (df["time"] <= close_dt)]
        if not df_trade.empty:
            if direction == "LONG":
                max_high = df_trade["high"].max()
                min_low = df_trade["low"].min()
                mfe_pips = (max_high - entry) / pip
                mae_pips = (entry - min_low) / pip
            else:
                min_low = df_trade["low"].min()
                max_high = df_trade["high"].max()
                mfe_pips = (entry - min_low) / pip
                mae_pips = (max_high - entry) / pip

    if outcome == "LOSS":
        if mfe_pips >= 8.0:
            reason = "Premature Reversal (Hit +8p+ before SL)"
        elif mfe_pips >= 5.0:
            reason = "Partial Expansion Reversal (+5p to +8p)"
        elif mae_pips <= 12.0 and sl_pips <= 10.0:
            reason = "SL Too Tight (Stopped by 10p wick)"
        else:
            reason = "Immediate Adverse Breakout (False signal)"

    print(f"{idx:2d} | {sym:6s} | {direction:5s} | {open_str[:16]} | {close_str[:16]} | {outcome:10s} | {sl_pips:5.1f} | {tp_pips:5.1f} | {real_pips:8.1f} | {mfe_pips:7.1f} | {mae_pips:7.1f} | {reason}")
