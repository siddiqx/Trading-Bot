"""
Quantitative Alpha Research: Trade Frequency vs Profitability
Rigorous multi-lever backtest testing:
  1. Baseline (Current v3.1: 1H only, CCRS crossing, HTF 1D, max 2 concurrent)
  2. State-Based CCRS (Allowing pullback/retest while |D| >= threshold, not just single-bar crossing)
  3. Divergence Threshold Sensitivity (1.75s, 1.50s vs 2.0s)
  4. HTF Filter Optimization (4H EMA vs 1D EMA vs Pure 1H Structure)
  5. Dual-Timeframe 15M Execution (1H CCRS Macro Bias + 15M Pullback/Sweep Triggers)
  6. Concurrency Expansion (Max 3 vs Max 2)
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))
import datetime
import numpy as np
import pandas as pd
from market_scanner import fetch_candles, SYMBOLS
from core.config import (
    CCRS_LOOKBACK_HOURS,
    CCRS_Z_WINDOW_HOURS,
    CANONICAL_STOP_LOSS_PIPS,
    CANONICAL_TAKE_PROFIT_PIPS,
)

print("=" * 75)
print("COMPREHENSIVE BACKTEST: INCREASING TRADE FREQUENCY & PRESERVING PROFITABILITY")
print("=" * 75)

# Fetch 60d 1H and 15M candles for all 6 pairs
print("\nFetching 60 days of 1H data...")
dfs_1h = {}
for pair, cfg in SYMBOLS.items():
    df = fetch_candles(cfg["ticker"], "1h", range_days="60d")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").reset_index(drop=True)
    dfs_1h[pair] = df

print("Fetching 30 days of 15M data...")
dfs_15m = {}
for pair, cfg in SYMBOLS.items():
    df = fetch_candles(cfg["ticker"], "15m", range_days="30d")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").reset_index(drop=True)
    dfs_15m[pair] = df

# CCRS Calculation on 1H close panel
close_panel = pd.DataFrame({p: df.set_index("time")["close"] for p, df in dfs_1h.items()}).dropna()
lb = CCRS_LOOKBACK_HOURS
z_win = CCRS_Z_WINDOW_HOURS

ret_eur = np.log(close_panel["EURUSD"] / close_panel["EURUSD"].shift(lb))
ret_gbp = np.log(close_panel["GBPUSD"] / close_panel["GBPUSD"].shift(lb))
ret_aud = np.log(close_panel["AUDUSD"] / close_panel["AUDUSD"].shift(lb))
ret_jpy = -np.log(close_panel["USDJPY"] / close_panel["USDJPY"].shift(lb))
ret_cad = -np.log(close_panel["USDCAD"] / close_panel["USDCAD"].shift(lb))
ret_chf = -np.log(close_panel["USDCHF"] / close_panel["USDCHF"].shift(lb))
ret_usd = -(ret_eur + ret_gbp + ret_aud + ret_jpy + ret_cad + ret_chf) / 6.0

curr_returns = pd.DataFrame({
    "EUR": ret_eur, "GBP": ret_gbp, "AUD": ret_aud,
    "JPY": ret_jpy, "CAD": ret_cad, "CHF": ret_chf, "USD": ret_usd
})

z_scores = (curr_returns - curr_returns.rolling(z_win).mean()) / (curr_returns.rolling(z_win).std() + 1e-9)

ccrs_div_1h = pd.DataFrame(index=close_panel.index)
ccrs_div_1h["EURUSD"] = z_scores["EUR"] - z_scores["USD"]
ccrs_div_1h["GBPUSD"] = z_scores["GBP"] - z_scores["USD"]
ccrs_div_1h["AUDUSD"] = z_scores["AUD"] - z_scores["USD"]
ccrs_div_1h["USDJPY"] = z_scores["USD"] - z_scores["JPY"]
ccrs_div_1h["USDCAD"] = z_scores["USD"] - z_scores["CAD"]
ccrs_div_1h["USDCHF"] = z_scores["USD"] - z_scores["CHF"]

# Precompute 1H indicators
ind_1h = {}
for pair, df in dfs_1h.items():
    d = df.copy()
    d["ema20"] = d["close"].ewm(span=20, adjust=False).mean()
    d["ema50"] = d["close"].ewm(span=50, adjust=False).mean()
    d["ema200"] = d["close"].ewm(span=200, adjust=False).mean()
    d["donch_high10"] = d["high"].rolling(10).max()
    d["donch_low10"] = d["low"].rolling(10).min()
    d["donch_high20"] = d["high"].rolling(20).max()
    d["donch_low20"] = d["low"].rolling(20).min()
    tr = np.maximum(d["high"] - d["low"], np.maximum(abs(d["high"] - d["close"].shift(1)), abs(d["low"] - d["close"].shift(1))))
    d["atr"] = tr.rolling(14).mean()
    ind_1h[pair] = d.set_index("time")

# Precompute 15M indicators
ind_15m = {}
for pair, df in dfs_15m.items():
    d = df.copy()
    d["ema20"] = d["close"].ewm(span=20, adjust=False).mean()
    d["ema50"] = d["close"].ewm(span=50, adjust=False).mean()
    d["donch_high10"] = d["high"].rolling(10).max()
    d["donch_low10"] = d["low"].rolling(10).min()
    d["donch_high20"] = d["high"].rolling(20).max()
    d["donch_low20"] = d["low"].rolling(20).min()
    tr = np.maximum(d["high"] - d["low"], np.maximum(abs(d["high"] - d["close"].shift(1)), abs(d["low"] - d["close"].shift(1))))
    d["atr"] = tr.rolling(14).mean()
    ind_15m[pair] = d.set_index("time")

# Simulation Engine with full parameter control
def simulate_strategy(
    z_threshold: float = 2.0,
    entry_mode: str = "CROSSING_ONLY", # "CROSSING_ONLY", "STATE_PULLBACK", "STATE_BREAKOUT"
    htf_filter_mode: str = "DAILY_EMA", # "DAILY_EMA", "1H_EMA200", "NONE"
    max_concurrent: int = 2,
    timeframe: str = "1h", # "1h" or "15m"
    sl_pips: float = 22.0,
    tp_pips: float = 33.0,
    session_hours: tuple = (6, 17) # 06:00 to 17:00 UTC
):
    source_ind = ind_1h if timeframe == "1h" else ind_15m
    common_times = ccrs_div_1h.dropna().index
    if timeframe == "15m":
        # Intersect with 15m availability
        min_15m = min([df.index[0] for df in ind_15m.values()])
        common_times = [t for t in common_times if t >= min_15m]

    active_trades = []
    completed_trades = []
    
    # Run through timeline
    for t in common_times:
        hour_utc = t.hour
        # 1. Manage active trades
        surviving = []
        for tr in active_trades:
            p = tr["pair"]
            bar_df = source_ind[p]
            if t not in bar_df.index:
                surviving.append(tr)
                continue
            bar = bar_df.loc[t]
            entry = tr["entry"]
            direction = tr["direction"]
            sl = tr["sl"]
            tp = tr["tp"]
            pip = 0.0001 if "JPY" not in p else 0.01
            
            # Pessimistic SL priority
            if direction == "LONG":
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
                elif (t - tr["entry_time"]).total_seconds() >= 48 * 3600:
                    pnl = (bar["close"] - entry) / pip
                    tr["outcome"] = "EXPIRED_WIN" if pnl > 0 else "EXPIRED_LOSS"
                    tr["pnl_pips"] = pnl
                    tr["r"] = pnl / sl_pips
                    completed_trades.append(tr)
                else:
                    surviving.append(tr)
            else: # SHORT
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
                elif (t - tr["entry_time"]).total_seconds() >= 48 * 3600:
                    pnl = (entry - bar["close"]) / pip
                    tr["outcome"] = "EXPIRED_WIN" if pnl > 0 else "EXPIRED_LOSS"
                    tr["pnl_pips"] = pnl
                    tr["r"] = pnl / sl_pips
                    completed_trades.append(tr)
                else:
                    surviving.append(tr)
        active_trades = surviving
        
        # Session check
        if not (session_hours[0] <= hour_utc <= session_hours[1]):
            continue
            
        if len(active_trades) >= max_concurrent:
            continue
            
        active_pairs = {tr["pair"] for tr in active_trades}
        
        # Get CCRS divergence for this bar
        idx_ccrs = ccrs_div_1h.index.get_loc(t) if t in ccrs_div_1h.index else None
        if idx_ccrs is None or idx_ccrs < 1:
            continue
            
        cur_div = ccrs_div_1h.iloc[idx_ccrs]
        prev_div = ccrs_div_1h.iloc[idx_ccrs - 1]
        
        for pair in SYMBOLS.keys():
            if pair in active_pairs:
                continue
            if len(active_trades) >= max_concurrent:
                break
                
            div_val = cur_div[pair]
            div_prev_val = prev_div[pair]
            
            bar_df = source_ind[pair]
            if t not in bar_df.index:
                continue
            bar_idx = bar_df.index.get_loc(t)
            if bar_idx < 20:
                continue
                
            curr_bar = bar_df.iloc[bar_idx]
            prev_bar = bar_df.iloc[bar_idx - 1]
            pip = 0.0001 if "JPY" not in pair else 0.01
            
            trigger_long = False
            trigger_short = False
            
            if entry_mode == "CROSSING_ONLY":
                # Single bar cross over threshold
                trigger_long = (div_val >= z_threshold) and (div_prev_val < z_threshold)
                trigger_short = (div_val <= -z_threshold) and (div_prev_val > -z_threshold)
            elif entry_mode == "STATE_PULLBACK":
                # Macro divergence is sustained (|D| >= threshold), and current bar prints a pullback to EMA20 / 50% Fib
                if div_val >= z_threshold:
                    # Long pullback test: touched EMA20 and closed bullish
                    tested_ema = curr_bar["low"] <= curr_bar["ema20"] * 1.0005
                    confirmed = curr_bar["close"] > curr_bar["open"] and curr_bar["close"] > curr_bar["ema20"]
                    trigger_long = tested_ema and confirmed
                elif div_val <= -z_threshold:
                    # Short pullback test: touched EMA20 and closed bearish
                    tested_ema = curr_bar["high"] >= curr_bar["ema20"] * 0.9995
                    confirmed = curr_bar["close"] < curr_bar["open"] and curr_bar["close"] < curr_bar["ema20"]
                    trigger_short = tested_ema and confirmed
            elif entry_mode == "STATE_RETEST_OR_FRACTAL":
                # Macro divergence sustained: either pullback to EMA20 OR 10-bar fractal reclaim (Turtle Soup)
                if div_val >= z_threshold:
                    tested_ema = (curr_bar["low"] <= curr_bar["ema20"] * 1.0005) and (curr_bar["close"] > curr_bar["open"])
                    swept_low = (curr_bar["low"] < prev_bar["donch_low10"]) and (curr_bar["close"] > prev_bar["donch_low10"])
                    trigger_long = tested_ema or swept_low
                elif div_val <= -z_threshold:
                    tested_ema = (curr_bar["high"] >= curr_bar["ema20"] * 0.9995) and (curr_bar["close"] < curr_bar["open"])
                    swept_high = (curr_bar["high"] > prev_bar["donch_high10"]) and (curr_bar["close"] < prev_bar["donch_high10"])
                    trigger_short = tested_ema or swept_high
            elif entry_mode == "STATE_BREAKOUT":
                # Breakout when divergence is sustained
                if div_val >= z_threshold:
                    trigger_long = curr_bar["close"] > prev_bar["donch_high10"]
                elif div_val <= -z_threshold:
                    trigger_short = curr_bar["close"] < prev_bar["donch_low10"]
                    
            if not (trigger_long or trigger_short):
                continue
                
            direction = "LONG" if trigger_long else "SHORT"
            
            # HTF Filter check
            if htf_filter_mode == "1H_EMA200":
                # 1H EMA200 trend alignment (Smoother, less lag than daily)
                if direction == "LONG" and curr_bar["close"] < curr_bar["ema200"]:
                    continue
                if direction == "SHORT" and curr_bar["close"] > curr_bar["ema200"]:
                    continue
            elif htf_filter_mode == "DAILY_EMA":
                # Approximated Daily 20/50: if EMA50 slope doesn't agree, skip
                if direction == "LONG" and curr_bar["close"] < curr_bar["ema50"]:
                    continue
                if direction == "SHORT" and curr_bar["close"] > curr_bar["ema50"]:
                    continue
                    
            entry = curr_bar["close"]
            if direction == "LONG":
                sl = entry - (sl_pips * pip)
                tp = entry + (tp_pips * pip)
            else:
                sl = entry + (sl_pips * pip)
                tp = entry - (tp_pips * pip)
                
            active_trades.append({
                "pair": pair,
                "direction": direction,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "entry_time": t
            })
            active_pairs.add(pair)
            
    if not completed_trades:
        return {"total_trades": 0, "trades_per_month": 0, "win_rate": 0, "pf": 0, "expectancy_r": 0, "net_pips": 0, "max_dd_pips": 0}
        
    df_res = pd.DataFrame(completed_trades)
    total = len(df_res)
    wins = len(df_res[df_res["pnl_pips"] > 0])
    wr = (wins / total) * 100.0
    gross_win = df_res[df_res["pnl_pips"] > 0]["pnl_pips"].sum()
    gross_loss = abs(df_res[df_res["pnl_pips"] < 0]["pnl_pips"].sum())
    pf = (gross_win / gross_loss) if gross_loss > 0 else 999.0
    net_p = df_res["pnl_pips"].sum()
    exp_r = df_res["r"].mean()
    days = (common_times[-1] - common_times[0]).total_seconds() / 86400.0
    tpm = (total / days) * 30.4
    
    peak = df_res["pnl_pips"].cumsum().cummax()
    dd = (peak - df_res["pnl_pips"].cumsum()).max()
    
    return {
        "total_trades": total,
        "trades_per_month": round(tpm, 1),
        "win_rate": round(wr, 1),
        "pf": round(pf, 2),
        "expectancy_r": round(exp_r, 2),
        "net_pips": round(net_p, 1),
        "max_dd_pips": round(dd, 1)
    }

print("\nRunning Multi-Lever Quantitative Grid...")
experiments = [
    # Baseline
    {"name": "0. Baseline (Crossing Only, 2.0s, Daily HTF, Max 2)", "z": 2.0, "mode": "CROSSING_ONLY", "htf": "DAILY_EMA", "conc": 2, "tf": "1h"},
    
    # Test Lever 1: Sensitivity of Divergence Threshold
    {"name": "1A. Crossing Only (1.75s, Daily HTF, Max 2)", "z": 1.75, "mode": "CROSSING_ONLY", "htf": "DAILY_EMA", "conc": 2, "tf": "1h"},
    {"name": "1B. Crossing Only (1.50s, Daily HTF, Max 2)", "z": 1.50, "mode": "CROSSING_ONLY", "htf": "DAILY_EMA", "conc": 2, "tf": "1h"},
    
    # Test Lever 2: State-Based Pullback Retest (Enter on Pullback while divergence persists)
    {"name": "2A. State Pullback (2.0s, Daily HTF, Max 2)", "z": 2.0, "mode": "STATE_PULLBACK", "htf": "DAILY_EMA", "conc": 2, "tf": "1h"},
    {"name": "2B. State Pullback (1.75s, Daily HTF, Max 2)", "z": 1.75, "mode": "STATE_PULLBACK", "htf": "DAILY_EMA", "conc": 2, "tf": "1h"},
    {"name": "2C. State Pullback + Fractal Sweep (1.75s, Max 2)", "z": 1.75, "mode": "STATE_RETEST_OR_FRACTAL", "htf": "DAILY_EMA", "conc": 2, "tf": "1h"},
    
    # Test Lever 3: HTF Filter Optimization (Replace Daily EMA with 1H EMA200)
    {"name": "3A. State Pullback + Fractal (1.75s, 1H EMA200 HTF, Max 2)", "z": 1.75, "mode": "STATE_RETEST_OR_FRACTAL", "htf": "1H_EMA200", "conc": 2, "tf": "1h"},
    {"name": "3B. State Pullback + Fractal (2.0s, 1H EMA200 HTF, Max 2)", "z": 2.0, "mode": "STATE_RETEST_OR_FRACTAL", "htf": "1H_EMA200", "conc": 2, "tf": "1h"},

    # Test Lever 4: Concurrency Expansion (Max 3 vs Max 2)
    {"name": "4A. State Pullback + Fractal (1.75s, 1H EMA200, Max 3)", "z": 1.75, "mode": "STATE_RETEST_OR_FRACTAL", "htf": "1H_EMA200", "conc": 3, "tf": "1h"},
    {"name": "4B. State Pullback + Fractal (2.0s, 1H EMA200, Max 3)", "z": 2.0, "mode": "STATE_RETEST_OR_FRACTAL", "htf": "1H_EMA200", "conc": 3, "tf": "1h"},

    # Test Lever 5: Breakout Momentum under Sustained Divergence
    {"name": "5A. State Breakout (1.75s, 1H EMA200, Max 2)", "z": 1.75, "mode": "STATE_BREAKOUT", "htf": "1H_EMA200", "conc": 2, "tf": "1h"},
    {"name": "5B. State Breakout (1.75s, 1H EMA200, Max 3)", "z": 1.75, "mode": "STATE_BREAKOUT", "htf": "1H_EMA200", "conc": 3, "tf": "1h"},
]

out = []
for exp in experiments:
    r = simulate_strategy(
        z_threshold=exp["z"],
        entry_mode=exp["mode"],
        htf_filter_mode=exp["htf"],
        max_concurrent=exp["conc"],
        timeframe=exp["tf"],
        sl_pips=CANONICAL_STOP_LOSS_PIPS,
        tp_pips=CANONICAL_TAKE_PROFIT_PIPS
    )
    r["strategy"] = exp["name"]
    out.append(r)

df_out = pd.DataFrame(out)
cols = ["strategy", "trades_per_month", "total_trades", "win_rate", "pf", "expectancy_r", "net_pips", "max_dd_pips"]
print("\n" + "=" * 115)
print(df_out[cols].to_string(index=False))
print("=" * 115)
