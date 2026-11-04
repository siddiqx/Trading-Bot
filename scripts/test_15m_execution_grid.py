"""
Dual Timeframe Execution Test:
1H CCRS Macro Flow Bias (|D| >= 1.75s or 2.0s) + 15M Entry Triggers
Tests whether 15M pullback/sweep execution increases trade frequency while preserving positive expectancy.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))
import datetime
import numpy as np
import pandas as pd
from market_scanner import fetch_candles, SYMBOLS
from core.config import CCRS_LOOKBACK_HOURS, CCRS_Z_WINDOW_HOURS

print("Fetching 30 days of 1H and 15M candles...")
dfs_1h = {}
dfs_15m = {}
for p, cfg in SYMBOLS.items():
    d1 = fetch_candles(cfg["ticker"], "1h", range_days="30d")
    d1["time"] = pd.to_datetime(d1["time"], utc=True)
    dfs_1h[p] = d1.sort_values("time").reset_index(drop=True)
    
    d15 = fetch_candles(cfg["ticker"], "15m", range_days="30d")
    d15["time"] = pd.to_datetime(d15["time"], utc=True)
    dfs_15m[p] = d15.sort_values("time").reset_index(drop=True)

# 1H CCRS Panel
close_1h = pd.DataFrame({p: df.set_index("time")["close"] for p, df in dfs_1h.items()}).dropna()
lb = CCRS_LOOKBACK_HOURS
z_win = CCRS_Z_WINDOW_HOURS

ret_eur = np.log(close_1h["EURUSD"] / close_1h["EURUSD"].shift(lb))
ret_gbp = np.log(close_1h["GBPUSD"] / close_1h["GBPUSD"].shift(lb))
ret_aud = np.log(close_1h["AUDUSD"] / close_1h["AUDUSD"].shift(lb))
ret_jpy = -np.log(close_1h["USDJPY"] / close_1h["USDJPY"].shift(lb))
ret_cad = -np.log(close_1h["USDCAD"] / close_1h["USDCAD"].shift(lb))
ret_chf = -np.log(close_1h["USDCHF"] / close_1h["USDCHF"].shift(lb))
ret_usd = -(ret_eur + ret_gbp + ret_aud + ret_jpy + ret_cad + ret_chf) / 6.0

curr_returns = pd.DataFrame({
    "EUR": ret_eur, "GBP": ret_gbp, "AUD": ret_aud,
    "JPY": ret_jpy, "CAD": ret_cad, "CHF": ret_chf, "USD": ret_usd
})

z_scores = (curr_returns - curr_returns.rolling(z_win).mean()) / (curr_returns.rolling(z_win).std() + 1e-9)
ccrs_div_1h = pd.DataFrame(index=close_1h.index)
ccrs_div_1h["EURUSD"] = z_scores["EUR"] - z_scores["USD"]
ccrs_div_1h["GBPUSD"] = z_scores["GBP"] - z_scores["USD"]
ccrs_div_1h["AUDUSD"] = z_scores["AUD"] - z_scores["USD"]
ccrs_div_1h["USDJPY"] = z_scores["USD"] - z_scores["JPY"]
ccrs_div_1h["USDCAD"] = z_scores["USD"] - z_scores["CAD"]
ccrs_div_1h["USDCHF"] = z_scores["USD"] - z_scores["CHF"]

# Compute 15M Indicators
ind_15m = {}
for p, df in dfs_15m.items():
    d = df.copy()
    d["ema20"] = d["close"].ewm(span=20, adjust=False).mean()
    d["ema50"] = d["close"].ewm(span=50, adjust=False).mean()
    d["donch_high10"] = d["high"].rolling(10).max()
    d["donch_low10"] = d["low"].rolling(10).min()
    d["donch_high20"] = d["high"].rolling(20).max()
    d["donch_low20"] = d["low"].rolling(20).min()
    tr = np.maximum(d["high"] - d["low"], np.maximum(abs(d["high"] - d["close"].shift(1)), abs(d["low"] - d["close"].shift(1))))
    d["atr"] = tr.rolling(14).mean()
    ind_15m[p] = d.set_index("time")

def run_15m_simulation(
    z_thresh: float = 1.75,
    sl_pips: float = 15.0, # tighter 15m SL
    tp_pips: float = 22.5, # 1:1.5 RR
    max_concurrent: int = 2,
    mode: str = "PULLBACK"
):
    # Align 15M timeline with 1H CCRS (ffill 1H CCRS to 15m bars)
    all_15m_times = sorted(list(set.intersection(*[set(df.index) for df in ind_15m.values()])))
    active_trades = []
    completed_trades = []
    
    for t in all_15m_times:
        hour_utc = t.hour
        # Update active trades
        surviving = []
        for tr in active_trades:
            p = tr["pair"]
            bar = ind_15m[p].loc[t]
            pip = 0.0001 if "JPY" not in p else 0.01
            entry = tr["entry"]
            sl = tr["sl"]
            tp = tr["tp"]
            
            if tr["direction"] == "LONG":
                if bar["low"] <= sl:
                    tr["outcome"] = "LOSS"
                    tr["pnl_pips"] = -sl_pips
                    tr["r"] = -1.0
                    completed_trades.append(tr)
                elif bar["high"] >= tp:
                    tr["outcome"] = "WIN"
                    tr["pnl_pips"] = tp_pips
                    tr["r"] = tp_pips / sl_pips
                    completed_trades.append(tr)
                elif (t - tr["entry_time"]).total_seconds() >= 24 * 3600:
                    pnl = (bar["close"] - entry) / pip
                    tr["outcome"] = "EXPIRED_WIN" if pnl > 0 else "EXPIRED_LOSS"
                    tr["pnl_pips"] = pnl
                    tr["r"] = pnl / sl_pips
                    completed_trades.append(tr)
                else:
                    surviving.append(tr)
            else:
                if bar["high"] >= sl:
                    tr["outcome"] = "LOSS"
                    tr["pnl_pips"] = -sl_pips
                    tr["r"] = -1.0
                    completed_trades.append(tr)
                elif bar["low"] <= tp:
                    tr["outcome"] = "WIN"
                    tr["pnl_pips"] = tp_pips
                    tr["r"] = tp_pips / sl_pips
                    completed_trades.append(tr)
                elif (t - tr["entry_time"]).total_seconds() >= 24 * 3600:
                    pnl = (entry - bar["close"]) / pip
                    tr["outcome"] = "EXPIRED_WIN" if pnl > 0 else "EXPIRED_LOSS"
                    tr["pnl_pips"] = pnl
                    tr["r"] = pnl / sl_pips
                    completed_trades.append(tr)
                else:
                    surviving.append(tr)
        active_trades = surviving
        
        # Session Filter (06:00 to 17:00 UTC)
        if not (6 <= hour_utc <= 17):
            continue
            
        if len(active_trades) >= max_concurrent:
            continue
            
        active_pairs = {tr["pair"] for tr in active_trades}
        
        # Find 1H CCRS as of this 15M bar (as_of <= t)
        past_1h = ccrs_div_1h[ccrs_div_1h.index <= t]
        if past_1h.empty:
            continue
        cur_div_row = past_1h.iloc[-1]
        
        for p in SYMBOLS.keys():
            if p in active_pairs or len(active_trades) >= max_concurrent:
                continue
            div_val = cur_div_row[p]
            if abs(div_val) < z_thresh:
                continue
                
            is_long = div_val > 0
            df_bar = ind_15m[p]
            idx = df_bar.index.get_loc(t)
            if idx < 20:
                continue
            curr = df_bar.iloc[idx]
            prev = df_bar.iloc[idx - 1]
            pip = 0.0001 if "JPY" not in p else 0.01
            
            trigger = False
            if is_long:
                if mode == "PULLBACK":
                    tested_ema = curr["low"] <= curr["ema20"] * 1.0003
                    confirmed = curr["close"] > curr["open"] and curr["close"] > curr["ema20"]
                    trigger = tested_ema and confirmed
                elif mode == "FRACTAL_SWEEP":
                    swept_low = curr["low"] < prev["donch_low10"]
                    closed_above = curr["close"] > prev["donch_low10"]
                    trigger = swept_low and closed_above
                elif mode == "BOTH":
                    tested_ema = (curr["low"] <= curr["ema20"] * 1.0003) and (curr["close"] > curr["open"])
                    swept_low = (curr["low"] < prev["donch_low10"]) and (curr["close"] > prev["donch_low10"])
                    trigger = tested_ema or swept_low
            else:
                if mode == "PULLBACK":
                    tested_ema = curr["high"] >= curr["ema20"] * 0.9997
                    confirmed = curr["close"] < curr["open"] and curr["close"] < curr["ema20"]
                    trigger = tested_ema and confirmed
                elif mode == "FRACTAL_SWEEP":
                    swept_high = curr["high"] > prev["donch_high10"]
                    closed_below = curr["close"] < prev["donch_high10"]
                    trigger = swept_high and closed_below
                elif mode == "BOTH":
                    tested_ema = (curr["high"] >= curr["ema20"] * 0.9997) and (curr["close"] < curr["open"])
                    swept_high = (curr["high"] > prev["donch_high10"]) and (curr["close"] < prev["donch_high10"])
                    trigger = tested_ema or swept_high
                    
            if trigger:
                entry = curr["close"]
                direction = "LONG" if is_long else "SHORT"
                if direction == "LONG":
                    sl = entry - (sl_pips * pip)
                    tp = entry + (tp_pips * pip)
                else:
                    sl = entry + (sl_pips * pip)
                    tp = entry - (tp_pips * pip)
                    
                active_trades.append({
                    "pair": p,
                    "direction": direction,
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "entry_time": t
                })
                active_pairs.add(p)
                
    if not completed_trades:
        return {"trades": 0, "tpm": 0, "wr": 0, "pf": 0, "exp_r": 0, "net_pips": 0, "dd": 0}
        
    df_res = pd.DataFrame(completed_trades)
    tot = len(df_res)
    w = len(df_res[df_res["pnl_pips"] > 0])
    wr = (w / tot) * 100.0
    gw = df_res[df_res["pnl_pips"] > 0]["pnl_pips"].sum()
    gl = abs(df_res[df_res["pnl_pips"] < 0]["pnl_pips"].sum())
    pf = gw / gl if gl > 0 else 999.0
    days = (all_15m_times[-1] - all_15m_times[0]).total_seconds() / 86400.0
    tpm = (tot / days) * 30.4
    net_p = df_res["pnl_pips"].sum()
    exp_r = df_res["r"].mean()
    peak = df_res["pnl_pips"].cumsum().cummax()
    dd = (peak - df_res["pnl_pips"].cumsum()).max()
    
    return {
        "trades": tot,
        "tpm": round(tpm, 1),
        "wr": round(wr, 1),
        "pf": round(pf, 2),
        "exp_r": round(exp_r, 2),
        "net_pips": round(net_p, 1),
        "dd": round(dd, 1)
    }

print("\n--- 15M EXECUTION UNDER 1H CCRS MACRO BIAS ---")
configs_15m = [
    {"name": "15M Pullback (1.75s, 15p SL / 22.5p TP, Max 2)", "z": 1.75, "sl": 15.0, "tp": 22.5, "conc": 2, "m": "PULLBACK"},
    {"name": "15M Pullback (2.0s, 15p SL / 22.5p TP, Max 2)", "z": 2.0, "sl": 15.0, "tp": 22.5, "conc": 2, "m": "PULLBACK"},
    {"name": "15M Fractal Sweep (1.75s, 15p SL / 22.5p TP, Max 2)", "z": 1.75, "sl": 15.0, "tp": 22.5, "conc": 2, "m": "FRACTAL_SWEEP"},
    {"name": "15M Both (1.75s, 15p SL / 22.5p TP, Max 2)", "z": 1.75, "sl": 15.0, "tp": 22.5, "conc": 2, "m": "BOTH"},
    {"name": "15M Both (1.75s, 15p SL / 22.5p TP, Max 3)", "z": 1.75, "sl": 15.0, "tp": 22.5, "conc": 3, "m": "BOTH"},
    {"name": "15M Both (1.75s, 22p SL / 33p TP, Max 2)", "z": 1.75, "sl": 22.0, "tp": 33.0, "conc": 2, "m": "BOTH"},
]

res_15m = []
for c in configs_15m:
    r = run_15m_simulation(z_thresh=c["z"], sl_pips=c["sl"], tp_pips=c["tp"], max_concurrent=c["conc"], mode=c["m"])
    r["config"] = c["name"]
    res_15m.append(r)

df_15m_out = pd.DataFrame(res_15m)
print(df_15m_out[["config", "tpm", "trades", "wr", "pf", "exp_r", "net_pips", "dd"]].to_string(index=False))
