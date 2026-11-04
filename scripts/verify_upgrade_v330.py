import sys
import os
import pandas as pd
import numpy as np

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from market_scanner import fetch_candles, SYMBOLS
from core.config import (
    CCRS_LOOKBACK_HOURS,
    CCRS_Z_WINDOW_HOURS,
    CANONICAL_STOP_LOSS_PIPS,
    CANONICAL_TAKE_PROFIT_PIPS,
    CANONICAL_TRANSACTION_COSTS
)

print("=" * 90)
print("VERIFICATION BACKTEST: CURRENT BASELINE (v3.2.0) vs UPGRADED (v3.3.0)")
print("=" * 90)

# 1. Fetch 180 days (6 months) of 1H data
print("\n[Step 1] Loading 180 days of 1H historical candles for 6 pairs...")
dfs_1h = {}
for p, cfg in SYMBOLS.items():
    df = fetch_candles(cfg["ticker"], "1h", range_days="180d")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df["close_time"] = df["time"] + pd.Timedelta(hours=1)
    df = df.sort_values("time").reset_index(drop=True)
    dfs_1h[p] = df

# 2. Build Zero-Lookahead CCRS Divergence Matrix
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

# Precompute 1H Indicators
ind_1h = {}
for p, df in dfs_1h.items():
    d = df.copy()
    d["ema20"] = d["close"].ewm(span=20, adjust=False).mean()
    d["donch_high10"] = d["high"].shift(1).rolling(10).max()
    d["donch_low10"] = d["low"].shift(1).rolling(10).min()
    ind_1h[p] = d.set_index("time")

def run_simulation(
    enable_volatility_cushion: bool = False,
    enable_daily_circuit_breaker: bool = False,
    risk_pct: float = 0.50,
    z_thresh: float = 1.75
):
    common_times = ccrs_div_1h.dropna().index
    active_trades = []
    completed_trades = []
    equity = 5000.0
    equity_curve = []
    daily_losses = {} # date -> count of losses
    
    for t in common_times:
        hour_utc = t.hour
        date_utc = t.date()
        if date_utc not in daily_losses:
            daily_losses[date_utc] = 0
            
        surviving = []
        for tr in active_trades:
            p = tr["pair"]
            bar = ind_1h[p].loc[t]
            pip = 0.0001 if "JPY" not in p else 0.01
            entry = tr["entry"]
            spread_pips = CANONICAL_TRANSACTION_COSTS.get(p, {}).get("total_pips", 1.3)
            risk_usd = tr["risk_usd"]
            
            # Adverse / Favorable excursion
            if tr["direction"] == "LONG":
                mfe_pips = (bar["high"] - entry) / pip
                mae_pips = (entry - bar["low"]) / pip
            else:
                mfe_pips = (entry - bar["low"]) / pip
                mae_pips = (bar["high"] - entry) / pip
                
            # Volatility Cushion Logic:
            # Stage 0: Initial full SL (22.0 pips)
            # Stage 1: At +1.2R (+26.4p), SL moves from 22.0p to 10.0p (halving risk, leaving 36p breathing room)
            # Stage 2: At +1.5R (+33.0p), SL moves to -11.0p (+0.5R lock) and TP extends to 44.0p (+2.0R)
            if enable_volatility_cushion:
                if mfe_pips >= 26.4 and tr["sl_stage"] == 0:
                    tr["sl_stage"] = 1
                    tr["current_sl_pips"] = 10.0 # cut risk from 22p to 10p
                if mfe_pips >= 33.0 and tr["sl_stage"] == 1:
                    tr["sl_stage"] = 2
                    tr["current_sl_pips"] = -11.0 # lock in +11 pips profit
                    tr["current_tp_pips"] = 44.0 # extend TP
            
            hit_sl = False
            hit_tp = False
            
            if tr["current_sl_pips"] > 0:
                if mae_pips >= tr["current_sl_pips"]:
                    hit_sl = True
            else:
                # Locked in profit: if favorable dropped back below +11p
                if mfe_pips < abs(tr["current_sl_pips"]) and tr["sl_stage"] >= 2:
                    hit_sl = True
                    
            if mfe_pips >= tr["current_tp_pips"]:
                hit_tp = True
                
            # Intra-candle precedence: SL takes precedence if both hit
            if hit_sl and hit_tp:
                hit_tp = False
                
            if hit_sl:
                if tr["current_sl_pips"] > 0:
                    pnl_pips = -(tr["current_sl_pips"] + spread_pips)
                    r_val = pnl_pips / 22.0
                    realized_usd = risk_usd * r_val
                    equity += realized_usd
                    tr.update({"outcome": "LOSS", "pnl_pips": pnl_pips, "pnl_usd": realized_usd, "r": r_val, "exit_time": t})
                    completed_trades.append(tr)
                    daily_losses[date_utc] += 1
                else:
                    pnl_pips = abs(tr["current_sl_pips"]) - spread_pips
                    r_val = pnl_pips / 22.0
                    realized_usd = risk_usd * r_val
                    equity += realized_usd
                    tr.update({"outcome": "PROFIT_LOCK", "pnl_pips": pnl_pips, "pnl_usd": realized_usd, "r": r_val, "exit_time": t})
                    completed_trades.append(tr)
            elif hit_tp:
                pnl_pips = tr["current_tp_pips"] - spread_pips
                r_val = pnl_pips / 22.0
                realized_usd = risk_usd * r_val
                equity += realized_usd
                tr.update({"outcome": "WIN", "pnl_pips": pnl_pips, "pnl_usd": realized_usd, "r": r_val, "exit_time": t})
                completed_trades.append(tr)
            elif (t - tr["entry_time"]).total_seconds() >= 48 * 3600:
                # 48h timeout
                if tr["direction"] == "LONG":
                    pnl_raw = ((bar["close"] - entry) / pip) - spread_pips
                else:
                    pnl_raw = ((entry - bar["close"]) / pip) - spread_pips
                r_val = pnl_raw / 22.0
                realized_usd = risk_usd * r_val
                equity += realized_usd
                tr.update({"outcome": "EXPIRED_WIN" if pnl_raw > 0 else "EXPIRED_LOSS", "pnl_pips": pnl_raw, "pnl_usd": realized_usd, "r": r_val, "exit_time": t})
                completed_trades.append(tr)
                if pnl_raw <= 0:
                    daily_losses[date_utc] += 1
            else:
                surviving.append(tr)
                
        active_trades = surviving
        equity_curve.append({"time": t, "equity": equity})
        
        # Session Filter: 06:00 to 17:00 UTC
        if not (6 <= hour_utc <= 17):
            continue
        if len(active_trades) >= 2:
            continue
            
        # Daily Circuit Breaker: Halt if 2 losses today
        if enable_daily_circuit_breaker and daily_losses.get(date_utc, 0) >= 2:
            continue
            
        active_pairs = {tr["pair"] for tr in active_trades}
        idx_ccrs = ccrs_div_1h.index.get_loc(t)
        if idx_ccrs < 1:
            continue
        cur_div = ccrs_div_1h.iloc[idx_ccrs]
        
        for p in SYMBOLS.keys():
            if p in active_pairs or len(active_trades) >= 2:
                continue
            div_val = cur_div[p]
            if abs(div_val) < z_thresh:
                continue
            is_long = div_val > 0
            df_bar = ind_1h[p]
            if t not in df_bar.index:
                continue
            idx = df_bar.index.get_loc(t)
            if idx < 20:
                continue
            curr = df_bar.iloc[idx]
            prev = df_bar.iloc[idx - 1]
            pip = 0.0001 if "JPY" not in p else 0.01
            
            trigger = False
            if is_long:
                tested_ema = (curr["low"] <= curr["ema20"] * 1.0005) and (curr["close"] > curr["open"])
                swept_low = (curr["low"] < prev["donch_low10"]) and (curr["close"] > prev["donch_low10"])
                trigger = tested_ema or swept_low
            else:
                tested_ema = (curr["high"] >= curr["ema20"] * 0.9995) and (curr["close"] < curr["open"])
                swept_high = (curr["high"] > prev["donch_high10"]) and (curr["close"] < prev["donch_high10"])
                trigger = tested_ema or swept_high
                
            if trigger:
                entry = curr["close"]
                direction = "LONG" if is_long else "SHORT"
                risk_usd = equity * (risk_pct / 100.0)
                active_trades.append({
                    "pair": p,
                    "direction": direction,
                    "entry": entry,
                    "current_sl_pips": 22.0,
                    "current_tp_pips": 33.0,
                    "sl_stage": 0,
                    "risk_usd": risk_usd,
                    "entry_time": t
                })
                
    # Compile performance
    df_trades = pd.DataFrame(completed_trades)
    df_eq = pd.DataFrame(equity_curve).set_index("time")
    
    total_trades = len(df_trades)
    wins = len(df_trades[df_trades["r"] > 0])
    losses = len(df_trades[df_trades["r"] <= 0])
    wr = (wins / total_trades) * 100.0 if total_trades > 0 else 0.0
    net_pips = df_trades["pnl_pips"].sum() if total_trades > 0 else 0.0
    net_usd = df_trades["pnl_usd"].sum() if total_trades > 0 else 0.0
    
    # Calculate Max Daily Drawdown
    df_daily = df_eq.resample("1D").last().dropna()
    df_daily["daily_ret"] = df_daily["equity"].diff()
    max_daily_dd = abs(df_daily["daily_ret"].min()) if len(df_daily) > 0 else 0.0
    
    # Calculate Max Overall Drawdown
    roll_max = df_eq["equity"].cummax()
    dd_series = roll_max - df_eq["equity"]
    max_overall_dd = dd_series.max()
    
    # Profit factor
    gross_win = df_trades[df_trades["pnl_usd"] > 0]["pnl_usd"].sum() if total_trades > 0 else 0.0
    gross_loss = abs(df_trades[df_trades["pnl_usd"] < 0]["pnl_usd"].sum()) if total_trades > 0 else 1.0
    pf = gross_win / gross_loss if gross_loss > 0 else 0.0
    
    return {
        "trades": total_trades,
        "win_rate": round(wr, 1),
        "net_pips": round(net_pips, 1),
        "net_usd": round(net_usd, 2),
        "profit_factor": round(pf, 2),
        "max_daily_dd_usd": round(max_daily_dd, 2),
        "max_daily_dd_pct": round((max_daily_dd / 5000.0) * 100.0, 1),
        "max_overall_dd_usd": round(max_overall_dd, 2),
        "max_overall_dd_pct": round((max_overall_dd / 5000.0) * 100.0, 1)
    }

print("\nRunning Model 1: Baseline v3.2.0 (No Cushion, No Circuit Breaker, 0.5% Risk)...")
res_base = run_simulation(enable_volatility_cushion=False, enable_daily_circuit_breaker=False, risk_pct=0.50)

print("Running Model 2: Volatility Cushion Trailing Only (0.5% Risk)...")
res_cushion = run_simulation(enable_volatility_cushion=True, enable_daily_circuit_breaker=False, risk_pct=0.50)

print("Running Model 3: Daily Circuit Breaker Only (0.5% Risk)...")
res_breaker = run_simulation(enable_volatility_cushion=False, enable_daily_circuit_breaker=True, risk_pct=0.50)

print("Running Model 4: Full Upgraded v3.3.0 Engine (Cushion + Circuit Breaker, 0.5% Risk)...")
res_v330 = run_simulation(enable_volatility_cushion=True, enable_daily_circuit_breaker=True, risk_pct=0.50)

summary_table = pd.DataFrame([
    {"Model": "1. Baseline (v3.2.0)", **res_base},
    {"Model": "2. + Volatility Cushion", **res_cushion},
    {"Model": "3. + Daily Circuit Breaker", **res_breaker},
    {"Model": "4. UPGRADED (v3.3.0 Complete)", **res_v330},
])

print("\n" + "=" * 115)
print("EMPIRICAL COMPARISON RESULTS (PAST 6 MONTHS - 180 DAYS)")
print("=" * 115)
print(summary_table.to_string(index=False))
print("=" * 115)
