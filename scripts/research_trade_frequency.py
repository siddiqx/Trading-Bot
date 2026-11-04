"""
Quantitative Research: Trade Frequency Optimization vs Profitability
Tests multiple systematic levers to increase trade frequency without destroying expectancy.
"""
import sys
import os
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

print("=" * 70)
print("QUANTITATIVE RESEARCH: INCREASING TRADE FREQUENCY WHILE MAINTAINING PROFITABILITY")
print("=" * 70)

# 1. Fetch 60 days of 1H data for the 6 institutional pairs
print("\n[Step 1] Fetching historical 1H data (60 days) for all 6 pairs...")
dfs_1h = {}
for pair, cfg in SYMBOLS.items():
    df = fetch_candles(cfg["ticker"], "1h", range_days="60d")
    if df.empty:
        print(f"Error fetching data for {pair}")
        sys.exit(1)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").reset_index(drop=True)
    dfs_1h[pair] = df
    print(f"  {pair}: {len(df)} 1H candles loaded ({df['time'].iloc[0]} to {df['time'].iloc[-1]})")

# Panel of close prices for CCRS
close_panel = pd.DataFrame({p: df.set_index("time")["close"] for p, df in dfs_1h.items()}).dropna()
print(f"  Aligned Panel Length: {len(close_panel)} bars")

# Precompute CCRS Divergences for each bar
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

ccrs_div = pd.DataFrame(index=close_panel.index)
ccrs_div["EURUSD"] = z_scores["EUR"] - z_scores["USD"]
ccrs_div["GBPUSD"] = z_scores["GBP"] - z_scores["USD"]
ccrs_div["AUDUSD"] = z_scores["AUD"] - z_scores["USD"]
ccrs_div["USDJPY"] = z_scores["USD"] - z_scores["JPY"]
ccrs_div["USDCAD"] = z_scores["USD"] - z_scores["CAD"]
ccrs_div["USDCHF"] = z_scores["USD"] - z_scores["CHF"]

# Precompute Indicators for each pair
indicators = {}
for pair, df in dfs_1h.items():
    d = df.copy()
    d["ema20"] = d["close"].ewm(span=20, adjust=False).mean()
    d["ema50"] = d["close"].ewm(span=50, adjust=False).mean()
    d["donch_high20"] = d["high"].rolling(20).max()
    d["donch_low20"] = d["low"].rolling(20).min()
    d["donch_high10"] = d["high"].rolling(10).max()
    d["donch_low10"] = d["low"].rolling(10).min()
    tr = np.maximum(d["high"] - d["low"], np.maximum(abs(d["high"] - d["close"].shift(1)), abs(d["low"] - d["close"].shift(1))))
    d["atr14"] = tr.rolling(14).mean()
    indicators[pair] = d.set_index("time")

# Simulation Engine Function
def run_simulation(
    z_threshold: float = 2.0,
    sl_pips: float = 22.0,
    tp_pips: float = 33.0,
    max_concurrent: int = 2,
    allow_direct_breakout: bool = False,
    include_10_bar_fractals: bool = True,
    session_filter: bool = True
):
    """
    Simulates portfolio execution across all 6 pairs on identical historical timeline.
    """
    common_times = ccrs_div.dropna().index
    active_trades = [] # list of dicts
    completed_trades = []
    
    for t in common_times:
        hour_utc = t.hour
        # Check active trades for TP / SL hits on this bar
        surviving_trades = []
        for tr in active_trades:
            pair = tr["pair"]
            bar = indicators[pair].loc[t] if t in indicators[pair].index else None
            if bar is None:
                surviving_trades.append(tr)
                continue
                
            entry = tr["entry"]
            direction = tr["direction"]
            sl = tr["sl"]
            tp = tr["tp"]
            pip = 0.0001 if "JPY" not in pair else 0.01
            
            # Check Pessimistic Intra-Candle Assumption: SL takes precedence if both touched
            if direction == "LONG":
                hit_sl = bar["low"] <= sl
                hit_tp = bar["high"] >= tp
                if hit_sl:
                    tr["exit_price"] = sl
                    tr["outcome"] = "LOSS"
                    tr["pnl_pips"] = -sl_pips
                    tr["r"] = -1.0
                    tr["exit_time"] = t
                    completed_trades.append(tr)
                elif hit_tp:
                    tr["exit_price"] = tp
                    tr["outcome"] = "WIN"
                    tr["pnl_pips"] = tp_pips
                    tr["r"] = tp_pips / sl_pips
                    tr["exit_time"] = t
                    completed_trades.append(tr)
                elif (t - tr["entry_time"]).total_seconds() >= 48 * 3600:
                    # Max hold expired
                    pnl = (bar["close"] - entry) / pip
                    tr["exit_price"] = bar["close"]
                    tr["outcome"] = "EXPIRED_WIN" if pnl > 0 else "EXPIRED_LOSS"
                    tr["pnl_pips"] = pnl
                    tr["r"] = pnl / sl_pips
                    tr["exit_time"] = t
                    completed_trades.append(tr)
                else:
                    surviving_trades.append(tr)
            else: # SHORT
                hit_sl = bar["high"] >= sl
                hit_tp = bar["low"] <= tp
                if hit_sl:
                    tr["exit_price"] = sl
                    tr["outcome"] = "LOSS"
                    tr["pnl_pips"] = -sl_pips
                    tr["r"] = -1.0
                    tr["exit_time"] = t
                    completed_trades.append(tr)
                elif hit_tp:
                    tr["exit_price"] = tp
                    tr["outcome"] = "WIN"
                    tr["pnl_pips"] = tp_pips
                    tr["r"] = tp_pips / sl_pips
                    tr["exit_time"] = t
                    completed_trades.append(tr)
                elif (t - tr["entry_time"]).total_seconds() >= 48 * 3600:
                    pnl = (entry - bar["close"]) / pip
                    tr["exit_price"] = bar["close"]
                    tr["outcome"] = "EXPIRED_WIN" if pnl > 0 else "EXPIRED_LOSS"
                    tr["pnl_pips"] = pnl
                    tr["r"] = pnl / sl_pips
                    tr["exit_time"] = t
                    completed_trades.append(tr)
                else:
                    surviving_trades.append(tr)
        active_trades = surviving_trades
        
        # Check Session Filter (06:00 to 20:00 UTC - London + NY active hours)
        if session_filter and not (6 <= hour_utc <= 20):
            continue
            
        # Check if we can open new trades
        if len(active_trades) >= max_concurrent:
            continue
            
        active_pairs = {tr["pair"] for tr in active_trades}
        
        # Scan pairs for signals on this bar
        row_div = ccrs_div.loc[t]
        for pair in SYMBOLS.keys():
            if pair in active_pairs:
                continue
            if len(active_trades) >= max_concurrent:
                break
                
            div_val = row_div[pair]
            if abs(div_val) < z_threshold:
                continue
                
            # Pair has sufficient macro order flow divergence!
            is_long = div_val > 0
            direction = "LONG" if is_long else "SHORT"
            
            bar_df = indicators[pair]
            if t not in bar_df.index:
                continue
            idx = bar_df.index.get_loc(t)
            if idx < 20:
                continue
                
            curr_bar = bar_df.iloc[idx]
            prev_bar = bar_df.iloc[idx - 1]
            pip = 0.0001 if "JPY" not in pair else 0.01
            
            # Entry Signal Check:
            # 1. Structural Pullback / Rejection (Price tests 20-EMA / 50% Fib and closes in trend direction)
            rejection_signal = False
            if is_long:
                tested_ema = curr_bar["low"] <= curr_bar["ema20"] * 1.0005
                confirmed_bullish = curr_bar["close"] > curr_bar["open"] and curr_bar["close"] > curr_bar["ema20"]
                rejection_signal = tested_ema and confirmed_bullish
            else:
                tested_ema = curr_bar["high"] >= curr_bar["ema20"] * 0.9995
                confirmed_bearish = curr_bar["close"] < curr_bar["open"] and curr_bar["close"] < curr_bar["ema20"]
                rejection_signal = tested_ema and confirmed_bearish
                
            # 2. Direct Breakout / Momentum Reclaim (Optional lever)
            breakout_signal = False
            if allow_direct_breakout:
                if is_long:
                    breakout_signal = curr_bar["close"] > prev_bar["donch_high10"] and curr_bar["close"] > curr_bar["ema20"]
                else:
                    breakout_signal = curr_bar["close"] < prev_bar["donch_low10"] and curr_bar["close"] < curr_bar["ema20"]
                    
            # 3. 10-bar Fractal Liquidity Sweep (Turtle Soup)
            fractal_signal = False
            if include_10_bar_fractals:
                if is_long:
                    swept_low = curr_bar["low"] < prev_bar["donch_low10"]
                    closed_above = curr_bar["close"] > prev_bar["donch_low10"]
                    fractal_signal = swept_low and closed_above
                else:
                    swept_high = curr_bar["high"] > prev_bar["donch_high10"]
                    closed_below = curr_bar["close"] < prev_bar["donch_high10"]
                    fractal_signal = swept_high and closed_below
                    
            if rejection_signal or breakout_signal or fractal_signal:
                # Trigger Trade!
                entry = curr_bar["close"]
                if direction == "LONG":
                    sl = entry - (sl_pips * pip)
                    tp = entry + (tp_pips * pip)
                else:
                    sl = entry + (sl_pips * pip)
                    tp = entry - (tp_pips * pip)
                    
                trade = {
                    "pair": pair,
                    "direction": direction,
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "entry_time": t,
                    "div_val": div_val,
                    "setup_type": "PULLBACK" if rejection_signal else ("BREAKOUT" if breakout_signal else "FRACTAL_SWEEP")
                }
                active_trades.append(trade)
                active_pairs.add(pair)
                
    # Compile performance stats
    if not completed_trades:
        return {"total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "net_pips": 0.0, "expectancy_r": 0.0, "trades_per_month": 0.0}
        
    df_res = pd.DataFrame(completed_trades)
    total = len(df_res)
    wins = len(df_res[df_res["pnl_pips"] > 0])
    losses = len(df_res[df_res["pnl_pips"] <= 0])
    win_rate = (wins / total) * 100.0 if total > 0 else 0.0
    
    gross_win_pips = df_res[df_res["pnl_pips"] > 0]["pnl_pips"].sum()
    gross_loss_pips = abs(df_res[df_res["pnl_pips"] < 0]["pnl_pips"].sum())
    pf = (gross_win_pips / gross_loss_pips) if gross_loss_pips > 0 else 999.0
    net_pips = df_res["pnl_pips"].sum()
    exp_r = df_res["r"].mean()
    
    # Days elapsed in test
    days = (common_times[-1] - common_times[0]).total_seconds() / 86400.0
    trades_per_month = (total / days) * 30.4
    
    return {
        "total_trades": total,
        "win_rate": round(win_rate, 1),
        "profit_factor": round(pf, 2),
        "net_pips": round(net_pips, 1),
        "expectancy_r": round(exp_r, 2),
        "trades_per_month": round(trades_per_month, 1),
        "max_drawdown_pips": round(calculate_max_dd(df_res["pnl_pips"].cumsum()), 1)
    }

def calculate_max_dd(equity_series):
    peak = equity_series.cummax()
    dd = peak - equity_series
    return dd.max() if not dd.empty else 0.0

print("\n[Step 2] Executing Parameter Matrix & Frequency Levers...")

scenarios = [
    # Baseline
    {"name": "Baseline (Current v3.1: 2.0s, Max 2, Pullback+Fractal)", "z": 2.0, "conc": 2, "direct": False, "sess": True},
    # Lever 1: Sensitivity Tuning (Lowering Divergence Threshold)
    {"name": "Lever 1A: Sensitivity 1.75s (Max 2)", "z": 1.75, "conc": 2, "direct": False, "sess": True},
    {"name": "Lever 1B: Sensitivity 1.50s (Max 2)", "z": 1.50, "conc": 2, "direct": False, "sess": True},
    {"name": "Lever 1C: Sensitivity 1.25s (Max 2)", "z": 1.25, "conc": 2, "direct": False, "sess": True},
    
    # Lever 2: Concurrency Expansion
    {"name": "Lever 2A: Max Concurrent 3 (2.0s)", "z": 2.0, "conc": 3, "direct": False, "sess": True},
    {"name": "Lever 2B: Max Concurrent 4 (2.0s)", "z": 2.0, "conc": 4, "direct": False, "sess": True},
    {"name": "Lever 2C: Max Concurrent 3 (1.75s)", "z": 1.75, "conc": 3, "direct": False, "sess": True},
    {"name": "Lever 2D: Max Concurrent 4 (1.75s)", "z": 1.75, "conc": 4, "direct": False, "sess": True},

    # Lever 3: Trigger Flexibility (Adding Direct 10-bar Donchian Momentum Breakout)
    {"name": "Lever 3A: Direct Breakouts Allowed (2.0s, Max 2)", "z": 2.0, "conc": 2, "direct": True, "sess": True},
    {"name": "Lever 3B: Direct Breakouts Allowed (1.75s, Max 2)", "z": 1.75, "conc": 2, "direct": True, "sess": True},
    {"name": "Lever 3C: Direct Breakouts + Max Conc 3 (1.75s)", "z": 1.75, "conc": 3, "direct": True, "sess": True},
    
    # Lever 4: 24/7 Session Expansion (Removing Session Filter)
    {"name": "Lever 4A: 24/7 All Sessions (2.0s, Max 2)", "z": 2.0, "conc": 2, "direct": False, "sess": False},
    {"name": "Lever 4B: 24/7 All Sessions (1.75s, Max 3)", "z": 1.75, "conc": 3, "direct": False, "sess": False},
]

results = []
for sc in scenarios:
    res = run_simulation(
        z_threshold=sc["z"],
        sl_pips=CANONICAL_STOP_LOSS_PIPS,
        tp_pips=CANONICAL_TAKE_PROFIT_PIPS,
        max_concurrent=sc["conc"],
        allow_direct_breakout=sc["direct"],
        session_filter=sc["sess"]
    )
    res["name"] = sc["name"]
    results.append(res)

df_results = pd.DataFrame(results)
cols = ["name", "trades_per_month", "total_trades", "win_rate", "profit_factor", "expectancy_r", "net_pips", "max_drawdown_pips"]
print("\n" + "=" * 105)
print(df_results[cols].to_string(index=False))
print("=" * 105)
