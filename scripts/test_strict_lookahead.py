"""
Strict Look-Ahead Verification for 15M Execution + 1H CCRS Macro Flow:
Enforces completed 1H candles (1H bar open at T-1h, closed at T).
At 15M timestamp t, the latest completed 1H bar is the one that closed at or before t.
Also includes spread slippage (1.2 pips per trade) to ensure real-world prop firm viability.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))
import datetime
import numpy as np
import pandas as pd
from market_scanner import fetch_candles, SYMBOLS
from core.config import CCRS_LOOKBACK_HOURS, CCRS_Z_WINDOW_HOURS

print("Loading data for strict look-ahead test...")
dfs_1h = {}
dfs_15m = {}
for p, cfg in SYMBOLS.items():
    d1 = fetch_candles(cfg["ticker"], "1h", range_days="30d")
    d1["time"] = pd.to_datetime(d1["time"], utc=True)
    d1["close_time"] = d1["time"] + pd.Timedelta(hours=1)
    dfs_1h[p] = d1.sort_values("time").reset_index(drop=True)
    
    d15 = fetch_candles(cfg["ticker"], "15m", range_days="30d")
    d15["time"] = pd.to_datetime(d15["time"], utc=True)
    d15["close_time"] = d15["time"] + pd.Timedelta(minutes=15)
    dfs_15m[p] = d15.sort_values("time").reset_index(drop=True)

# 1H CCRS Panel strictly indexed by close_time
close_1h = pd.DataFrame({p: df.set_index("close_time")["close"] for p, df in dfs_1h.items()}).dropna()
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
    ind_15m[p] = d.set_index("close_time")

def run_strict_simulation(
    z_thresh: float = 1.75,
    sl_pips: float = 22.0,
    tp_pips: float = 33.0,
    max_concurrent: int = 2,
    spread_pips: float = 1.2
):
    all_15m_times = sorted(list(set.intersection(*[set(df.index) for df in ind_15m.values()])))
    active_trades = []
    completed_trades = []
    
    for t in all_15m_times:
        hour_utc = t.hour
        surviving = []
        for tr in active_trades:
            p = tr["pair"]
            bar = ind_15m[p].loc[t]
            pip = 0.0001 if "JPY" not in p else 0.01
            entry = tr["entry"]
            sl = tr["sl"]
            tp = tr["tp"]
            
            # Pessimistic check
            if tr["direction"] == "LONG":
                if bar["low"] <= sl:
                    tr["outcome"] = "LOSS"
                    tr["pnl_pips"] = -(sl_pips + spread_pips)
                    tr["r"] = -1.0
                    completed_trades.append(tr)
                elif bar["high"] >= tp:
                    tr["outcome"] = "WIN"
                    tr["pnl_pips"] = tp_pips - spread_pips
                    tr["r"] = (tp_pips - spread_pips) / sl_pips
                    completed_trades.append(tr)
                elif (t - tr["entry_time"]).total_seconds() >= 36 * 3600:
                    pnl = ((bar["close"] - entry) / pip) - spread_pips
                    tr["outcome"] = "EXPIRED_WIN" if pnl > 0 else "EXPIRED_LOSS"
                    tr["pnl_pips"] = pnl
                    tr["r"] = pnl / sl_pips
                    completed_trades.append(tr)
                else:
                    surviving.append(tr)
            else:
                if bar["high"] >= sl:
                    tr["outcome"] = "LOSS"
                    tr["pnl_pips"] = -(sl_pips + spread_pips)
                    tr["r"] = -1.0
                    completed_trades.append(tr)
                elif bar["low"] <= tp:
                    tr["outcome"] = "WIN"
                    tr["pnl_pips"] = tp_pips - spread_pips
                    tr["r"] = (tp_pips - spread_pips) / sl_pips
                    completed_trades.append(tr)
                elif (t - tr["entry_time"]).total_seconds() >= 36 * 3600:
                    pnl = ((entry - bar["close"]) / pip) - spread_pips
                    tr["outcome"] = "EXPIRED_WIN" if pnl > 0 else "EXPIRED_LOSS"
                    tr["pnl_pips"] = pnl
                    tr["r"] = pnl / sl_pips
                    completed_trades.append(tr)
                else:
                    surviving.append(tr)
        active_trades = surviving
        
        # Session Filter: 06:00 to 17:00 UTC (London + NY)
        if not (6 <= hour_utc <= 17):
            continue
            
        if len(active_trades) >= max_concurrent:
            continue
            
        active_pairs = {tr["pair"] for tr in active_trades}
        
        # STRICT LOOK-AHEAD PREVENTION:
        # Use ONLY 1H candle bars where close_time <= t
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
                tested_ema = (curr["low"] <= curr["ema20"] * 1.0003) and (curr["close"] > curr["open"])
                swept_low = (curr["low"] < prev["donch_low10"]) and (curr["close"] > prev["donch_low10"])
                trigger = tested_ema or swept_low
            else:
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

print("\n--- STRICT ZERO-LOOKAHEAD TEST WITH SPREAD DEDUCTED (1.2 PIPS/TRADE) ---")
grid = [
    {"name": "Strict Dual-TF (1.75s, 22p SL / 33p TP, Max 2)", "z": 1.75, "sl": 22.0, "tp": 33.0, "conc": 2},
    {"name": "Strict Dual-TF (2.00s, 22p SL / 33p TP, Max 2)", "z": 2.00, "sl": 22.0, "tp": 33.0, "conc": 2},
    {"name": "Strict Dual-TF (1.75s, 22p SL / 33p TP, Max 3)", "z": 1.75, "sl": 22.0, "tp": 33.0, "conc": 3},
    {"name": "Strict Dual-TF (2.00s, 22p SL / 33p TP, Max 3)", "z": 2.00, "sl": 22.0, "tp": 33.0, "conc": 3},
    {"name": "Strict Dual-TF (1.75s, 20p SL / 30p TP, Max 2)", "z": 1.75, "sl": 20.0, "tp": 30.0, "conc": 2},
    {"name": "Strict Dual-TF (1.75s, 25p SL / 37.5p TP, Max 2)", "z": 1.75, "sl": 25.0, "tp": 37.5, "conc": 2},
]

results = []
for g in grid:
    r = run_strict_simulation(z_thresh=g["z"], sl_pips=g["sl"], tp_pips=g["tp"], max_concurrent=g["conc"])
    r["name"] = g["name"]
    results.append(r)

df_strict = pd.DataFrame(results)
print(df_strict[["name", "tpm", "trades", "wr", "pf", "exp_r", "net_pips", "dd"]].to_string(index=False))
