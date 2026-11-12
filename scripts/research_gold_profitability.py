#!/usr/bin/env python3
"""Quantitative Research Engine: Optimizing Gold (XAUUSD) Satellite Profitability.

Tests empirical parameters across:
1. Pure Binary Target vs Volatility Cushion Trailing Stop.
2. Risk-Reward Ratio (1.25R, 1.50R, 1.75R, 2.00R).
3. CCRS USD Macro Flow Threshold (1.50σ, 1.75σ, 2.00σ).
4. Institutional Session Window (06-18 UTC vs 06-20 UTC).
5. Sizing & Risk Budgets for a $25,000 account (0.5% vs 1.0% vs 1.5%).
"""

import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import pandas as pd
from datetime import datetime, timezone
from satellite.gold_config import (
    GOLD_TICKER, CCRS_LOOKBACK_HOURS, CCRS_Z_WINDOW_HOURS,
    ATR_PERIOD, ATR_MULTIPLIER, MIN_SL_POINTS, MAX_SL_POINTS,
    TRANSACTION_COSTS, POINT_VALUE_PER_LOT, CONTRACT_SIZE_OZ
)
from satellite.market_scanner_gold import fetch_candles_1h, compute_gold_indicators
from satellite.gold_validator import calculate_gold_position_size
from market_scanner import fetch_candles

def run_gold_simulation(
    df_gold: pd.DataFrame,
    z_usd_series: pd.Series,
    rr_ratio: float = 1.50,
    use_volatility_cushion: bool = False,
    ccrs_threshold: float = 1.75,
    active_hours: tuple = (6, 18),
    account_equity: float = 25000.0,
    risk_pct: float = 0.50,
):
    df = compute_gold_indicators(df_gold)
    costs_per_oz = TRANSACTION_COSTS["total_points"] # $0.36/oz

    balance = account_equity
    peak_balance = account_equity
    max_dd_usd = 0.0
    trades = []
    active_trade = None

    for i in range(50, len(df)):
        cur_bar = df.iloc[i]
        prev_bar = df.iloc[i - 1]
        bar_time = cur_bar["time_dt"]

        # 1. Manage Active Trade
        if active_trade is not None:
            entry_p = active_trade["entry_price"]
            sl_p = active_trade["current_sl_price"]
            tp_p = active_trade["current_tp_price"]
            init_sl_dist = active_trade["init_sl_points"]
            lots = active_trade["lots"]
            oz = lots * CONTRACT_SIZE_OZ
            direction = active_trade["direction"]
            hold_hours = (bar_time - active_trade["entry_time"]).total_seconds() / 3600.0

            # Volatility Cushion Logic
            if use_volatility_cushion:
                stage = active_trade.get("cushion_stage", 0)
                if direction == "LONG":
                    favorable_r = (cur_bar["high"] - entry_p) / init_sl_dist
                    if stage == 0 and favorable_r >= 1.20:
                        active_trade["current_sl_price"] = entry_p - (0.50 * init_sl_dist)
                        active_trade["cushion_stage"] = 1
                    elif stage == 1 and favorable_r >= 1.50:
                        active_trade["current_sl_price"] = entry_p + (0.50 * init_sl_dist)
                        active_trade["current_tp_price"] = entry_p + (2.00 * init_sl_dist)
                        active_trade["cushion_stage"] = 2
                else:
                    favorable_r = (entry_p - cur_bar["low"]) / init_sl_dist
                    if stage == 0 and favorable_r >= 1.20:
                        active_trade["current_sl_price"] = entry_p + (0.50 * init_sl_dist)
                        active_trade["cushion_stage"] = 1
                    elif stage == 1 and favorable_r >= 1.50:
                        active_trade["current_sl_price"] = entry_p - (0.50 * init_sl_dist)
                        active_trade["current_tp_price"] = entry_p - (2.00 * init_sl_dist)
                        active_trade["cushion_stage"] = 2

                sl_p = active_trade["current_sl_price"]
                tp_p = active_trade["current_tp_price"]

            # Intra-bar pessimistic exit check (SL takes precedence)
            hit_sl = False
            hit_tp = False
            exit_price = None
            reason = None

            if direction == "LONG":
                if cur_bar["low"] <= sl_p:
                    hit_sl = True
                    exit_price = sl_p
                    reason = "STOP_LOSS"
                elif cur_bar["high"] >= tp_p:
                    hit_tp = True
                    exit_price = tp_p
                    reason = "TAKE_PROFIT"
            else:
                if cur_bar["high"] >= sl_p:
                    hit_sl = True
                    exit_price = sl_p
                    reason = "STOP_LOSS"
                elif cur_bar["low"] <= tp_p:
                    hit_tp = True
                    exit_price = tp_p
                    reason = "TAKE_PROFIT"

            # 48-hour timeout
            if not hit_sl and not hit_tp and hold_hours >= 48.0:
                exit_price = cur_bar["close"]
                reason = "TIMEOUT_48H"

            if exit_price is not None:
                if direction == "LONG":
                    gross_pnl = (exit_price - entry_p) * oz
                else:
                    gross_pnl = (entry_p - exit_price) * oz
                friction = costs_per_oz * oz
                net_pnl = gross_pnl - friction
                balance += net_pnl
                peak_balance = max(peak_balance, balance)
                dd = peak_balance - balance
                max_dd_usd = max(max_dd_usd, dd)

                r_mult = net_pnl / active_trade["monetary_risk"] if active_trade["monetary_risk"] > 0 else 0.0
                trades.append({
                    "entry_time": active_trade["entry_time"],
                    "exit_time": bar_time,
                    "direction": direction,
                    "entry_price": entry_p,
                    "exit_price": exit_price,
                    "lots": lots,
                    "gross_pnl": gross_pnl,
                    "net_pnl": net_pnl,
                    "r_mult": r_mult,
                    "reason": reason,
                    "is_win": net_pnl > 0
                })
                active_trade = None

        # 2. Check Fresh Signal Entry
        if active_trade is None:
            # Active volume window check
            if not (active_hours[0] <= bar_time.hour < active_hours[1]):
                continue

            # CCRS USD Factor
            close_t = cur_bar["close_time"]
            if close_t not in z_usd_series.index:
                continue
            z_usd = z_usd_series.loc[close_t]
            if pd.isna(z_usd):
                continue

            is_long_macro = z_usd <= -ccrs_threshold
            is_short_macro = z_usd >= ccrs_threshold
            if not is_long_macro and not is_short_macro:
                continue

            direction = "LONG" if is_long_macro else "SHORT"
            cur_c = cur_bar["close"]
            cur_o = cur_bar["open"]
            cur_l = cur_bar["low"]
            cur_h = cur_bar["high"]
            cur_atr = cur_bar["atr14"]

            trigger = False
            if is_long_macro:
                tested_ema = (cur_l <= cur_bar["ema20"] * 1.0005) and (cur_c > cur_o)
                swept_low = (cur_l < prev_bar["donch_l10"]) and (cur_c > prev_bar["donch_l10"])
                rsi_ok = cur_bar["rsi14"] <= 75.0
                if (tested_ema or swept_low) and rsi_ok:
                    trigger = True
            else:
                tested_ema = (cur_h >= cur_bar["ema20"] * 0.9995) and (cur_c < cur_o)
                swept_high = (cur_h > prev_bar["donch_h10"]) and (cur_c < prev_bar["donch_h10"])
                rsi_ok = cur_bar["rsi14"] >= 25.0
                if (tested_ema or swept_high) and rsi_ok:
                    trigger = True

            if not trigger:
                continue

            # Calculate dynamic ATR stops
            sl_points = min(max(cur_atr * ATR_MULTIPLIER, MIN_SL_POINTS), MAX_SL_POINTS)
            tp_points = sl_points * rr_ratio

            lots, monetary_risk = calculate_gold_position_size(
                account_equity=balance,
                risk_pct=risk_pct,
                sl_points=sl_points
            )
            if lots <= 0.0:
                continue

            entry_price = cur_c
            sl_price = entry_price - sl_points if direction == "LONG" else entry_price + sl_points
            tp_price = entry_price + tp_points if direction == "LONG" else entry_price - tp_points

            active_trade = {
                "entry_time": bar_time,
                "direction": direction,
                "entry_price": entry_price,
                "current_sl_price": sl_price,
                "current_tp_price": tp_price,
                "init_sl_points": sl_points,
                "lots": lots,
                "monetary_risk": monetary_risk,
                "cushion_stage": 0
            }

    # Summary Statistics
    total_trades = len(trades)
    if total_trades == 0:
        return {"trades": 0, "win_rate": 0, "net_pnl": 0, "pf": 0, "max_dd_pct": 0}

    wins = [t for t in trades if t["is_win"]]
    losses = [t for t in trades if not t["is_win"]]
    win_rate = (len(wins) / total_trades) * 100.0
    gross_win = sum(t["net_pnl"] for t in wins)
    gross_loss = abs(sum(t["net_pnl"] for t in losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
    net_pnl = balance - account_equity
    max_dd_pct = (max_dd_usd / peak_balance) * 100.0

    return {
        "trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 1),
        "net_pnl": round(net_pnl, 2),
        "pf": round(pf, 2),
        "max_dd_usd": round(max_dd_usd, 2),
        "max_dd_pct": round(max_dd_pct, 2),
        "final_balance": round(balance, 2)
    }

if __name__ == "__main__":
    print("Preparing data...")
    forex_pairs = ['EURUSD', 'GBPUSD', 'AUDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
    tickers = {'EURUSD': 'EURUSD=X', 'GBPUSD': 'GBPUSD=X', 'AUDUSD': 'AUDUSD=X', 'USDJPY': 'USDJPY=X', 'USDCAD': 'USDCAD=X', 'USDCHF': 'USDCHF=X'}
    dfs = {}
    for p in forex_pairs:
        d = fetch_candles(tickers[p], '1h', range_days='60d')
        d['time'] = pd.to_datetime(d['time'], utc=True)
        d['close_time'] = d['time'] + pd.Timedelta(hours=1)
        dfs[p] = d.set_index('close_time')['close']
    df_fx = pd.DataFrame(dfs).dropna()

    lb = CCRS_LOOKBACK_HOURS
    z_win = CCRS_Z_WINDOW_HOURS
    r_eur = np.log(df_fx['EURUSD'] / df_fx['EURUSD'].shift(lb))
    r_gbp = np.log(df_fx['GBPUSD'] / df_fx['GBPUSD'].shift(lb))
    r_aud = np.log(df_fx['AUDUSD'] / df_fx['AUDUSD'].shift(lb))
    r_jpy = -np.log(df_fx['USDJPY'] / df_fx['USDJPY'].shift(lb))
    r_cad = -np.log(df_fx['USDCAD'] / df_fx['USDCAD'].shift(lb))
    r_chf = -np.log(df_fx['USDCHF'] / df_fx['USDCHF'].shift(lb))
    r_usd = -(r_eur + r_gbp + r_aud + r_jpy + r_cad + r_chf) / 6.0
    curr_ret = pd.DataFrame({'EUR': r_eur, 'GBP': r_gbp, 'AUD': r_aud, 'JPY': r_jpy, 'CAD': r_cad, 'CHF': r_chf, 'USD': r_usd})
    z_scores = (curr_ret - curr_ret.rolling(z_win).mean()) / (curr_ret.rolling(z_win).std() + 1e-9)
    z_usd_series = z_scores['USD']

    df_gold = fetch_candles_1h(GOLD_TICKER, range_days='60d')

    print("\n" + "="*80)
    print("EXPERIMENT 1: EXIT ARCHITECTURE (Pure Binary Target vs Volatility Cushion)")
    print("="*80)
    for cushion in [False, True]:
        label = "Volatility Cushion Trailing" if cushion else "Pure Binary Target (No Trailing)"
        res = run_gold_simulation(df_gold, z_usd_series, rr_ratio=1.50, use_volatility_cushion=cushion, account_equity=25000.0, risk_pct=0.50)
        print(f"[{label:32s}] Trades: {res['trades']:2d} | WinRate: {res['win_rate']:4.1f}% | Net PnL: ${res['net_pnl']:+8.2f} | PF: {res['pf']:4.2f} | MaxDD: {res['max_dd_pct']:.2f}%")

    print("\n" + "="*80)
    print("EXPERIMENT 2: RISK-REWARD RATIO CALIBRATION (Pure Binary Target)")
    print("="*80)
    for rr in [1.25, 1.40, 1.50, 1.60, 1.75, 2.00]:
        res = run_gold_simulation(df_gold, z_usd_series, rr_ratio=rr, use_volatility_cushion=False, account_equity=25000.0, risk_pct=0.50)
        print(f"[R:R = 1:{rr:4.2f}] Trades: {res['trades']:2d} | WinRate: {res['win_rate']:4.1f}% | Net PnL: ${res['net_pnl']:+8.2f} | PF: {res['pf']:4.2f} | MaxDD: {res['max_dd_pct']:.2f}%")

    print("\n" + "="*80)
    print("EXPERIMENT 3: CCRS USD MACRO THRESHOLD")
    print("="*80)
    for thresh in [1.50, 1.65, 1.75, 1.90, 2.00]:
        res = run_gold_simulation(df_gold, z_usd_series, rr_ratio=1.50, use_volatility_cushion=False, ccrs_threshold=thresh, account_equity=25000.0, risk_pct=0.50)
        print(f"[Threshold = {thresh:4.2f}σ] Trades: {res['trades']:2d} | WinRate: {res['win_rate']:4.1f}% | Net PnL: ${res['net_pnl']:+8.2f} | PF: {res['pf']:4.2f} | MaxDD: {res['max_dd_pct']:.2f}%")

    print("\n" + "="*80)
    print("EXPERIMENT 4: INSTITUTIONAL SESSION TRADING HOURS")
    print("="*80)
    for hrs in [(6, 18), (6, 20), (7, 17), (8, 16)]:
        res = run_gold_simulation(df_gold, z_usd_series, rr_ratio=1.50, use_volatility_cushion=False, active_hours=hrs, account_equity=25000.0, risk_pct=0.50)
        print(f"[Session {hrs[0]:02d}:00-{hrs[1]:02d}:00 UTC] Trades: {res['trades']:2d} | WinRate: {res['win_rate']:4.1f}% | Net PnL: ${res['net_pnl']:+8.2f} | PF: {res['pf']:4.2f} | MaxDD: {res['max_dd_pct']:.2f}%")

    print("\n" + "="*80)
    print("EXPERIMENT 5: $25,000 ACCOUNT SIZING CALIBRATION (Risk % Comparison)")
    print("="*80)
    for risk in [0.25, 0.50, 0.75, 1.00, 1.25, 1.50]:
        res = run_gold_simulation(df_gold, z_usd_series, rr_ratio=1.50, use_volatility_cushion=False, account_equity=25000.0, risk_pct=risk)
        print(f"[Risk {risk:4.2f}% (${25000*risk/100:6.1f})] Trades: {res['trades']:2d} | WinRate: {res['win_rate']:4.1f}% | Net PnL: ${res['net_pnl']:+8.2f} | PF: {res['pf']:4.2f} | MaxDD: ${res['max_dd_usd']:7.2f} ({res['max_dd_pct']:.2f}%)")
