#!/usr/bin/env python3
"""Comprehensive Empirical Analysis: Gold (XAUUSD) Performance on Fridays.

Evaluates:
1. Day-of-Week performance breakdown (Win Rate, Profit Factor, Net R, Expectancy).
2. Granular Friday hourly performance (London Open, US Overlap, Friday Afternoon Drift).
3. Impact of complete Friday exclusion vs Friday session cutoff (e.g. 12:00 UTC).
4. Statistical significance and portfolio expectancy comparison.
"""

import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import pickle
import numpy as np
import pandas as pd
from satellite.gold_config import (
    CCRS_LOOKBACK_HOURS, CCRS_Z_WINDOW_HOURS,
    ATR_PERIOD, ATR_MULTIPLIER, MIN_SL_POINTS, MAX_SL_POINTS,
    TRANSACTION_COSTS, CONTRACT_SIZE_OZ, BASE_RISK_REWARD_RATIO,
    VOLATILITY_CUSHION_TIER1_R, VOLATILITY_CUSHION_TIER2_R, VOLATILITY_CUSHION_RUNNER_R,
    CCRS_USD_THRESHOLD
)
from satellite.market_scanner_gold import compute_gold_indicators
from satellite.gold_validator import calculate_gold_position_size


def run_detailed_gold_backtest(
    df_gold: pd.DataFrame,
    z_usd_series: pd.Series,
    ccrs_threshold: float = 1.25,
    rr_ratio: float = BASE_RISK_REWARD_RATIO,
    use_volatility_cushion: bool = True,
    account_equity: float = 25000.0,
    risk_pct: float = 1.00,
    friday_mode: str = "ALL",  # "ALL", "NO_FRIDAY", "FRIDAY_CUTOFF_12UTC", "FRIDAY_CUTOFF_15UTC"
):
    df = compute_gold_indicators(df_gold)
    costs_per_oz = TRANSACTION_COSTS["total_points"]  # $0.36/oz

    balance = account_equity
    peak_balance = account_equity
    max_dd_usd = 0.0
    trades = []
    active_trade = None

    for i in range(50, len(df)):
        cur_bar = df.iloc[i]
        prev_bar = df.iloc[i - 1]
        bar_time = cur_bar["time_dt"]
        day_name = bar_time.strftime("%A")
        hour_utc = bar_time.hour

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

            # Friday Weekend Flat Cutoff: Close at Friday 21:00 UTC to avoid weekend gap
            is_weekend_close = (day_name == "Friday" and hour_utc >= 21)

            # Volatility Cushion Logic
            if use_volatility_cushion and not is_weekend_close:
                stage = active_trade.get("cushion_stage", 0)
                if direction == "LONG":
                    favorable_r = (cur_bar["high"] - entry_p) / init_sl_dist
                    if stage == 0 and favorable_r >= VOLATILITY_CUSHION_TIER1_R:
                        active_trade["current_sl_price"] = entry_p - (0.50 * init_sl_dist)
                        active_trade["cushion_stage"] = 1
                    elif stage == 1 and favorable_r >= VOLATILITY_CUSHION_TIER2_R:
                        active_trade["current_sl_price"] = entry_p + (0.50 * init_sl_dist)
                        active_trade["current_tp_price"] = entry_p + (VOLATILITY_CUSHION_RUNNER_R * init_sl_dist)
                        active_trade["cushion_stage"] = 2
                else:
                    favorable_r = (entry_p - cur_bar["low"]) / init_sl_dist
                    if stage == 0 and favorable_r >= VOLATILITY_CUSHION_TIER1_R:
                        active_trade["current_sl_price"] = entry_p + (0.50 * init_sl_dist)
                        active_trade["cushion_stage"] = 1
                    elif stage == 1 and favorable_r >= VOLATILITY_CUSHION_TIER2_R:
                        active_trade["current_sl_price"] = entry_p - (0.50 * init_sl_dist)
                        active_trade["current_tp_price"] = entry_p - (VOLATILITY_CUSHION_RUNNER_R * init_sl_dist)
                        active_trade["cushion_stage"] = 2

                sl_p = active_trade["current_sl_price"]
                tp_p = active_trade["current_tp_price"]

            # Pessimistic Intra-bar check (SL takes precedence)
            hit_sl = False
            hit_tp = False
            exit_price = None
            reason = None

            if is_weekend_close:
                exit_price = cur_bar["close"]
                reason = "WEEKEND_FLAT"
            elif direction == "LONG":
                if cur_bar["low"] <= sl_p:
                    hit_sl = True
                    exit_price = sl_p
                    reason = "STOP_LOSS" if active_trade.get("cushion_stage", 0) < 2 else "PROFIT_LOCK"
                elif cur_bar["high"] >= tp_p:
                    hit_tp = True
                    exit_price = tp_p
                    reason = "TAKE_PROFIT"
            else:
                if cur_bar["high"] >= sl_p:
                    hit_sl = True
                    exit_price = sl_p
                    reason = "STOP_LOSS" if active_trade.get("cushion_stage", 0) < 2 else "PROFIT_LOCK"
                elif cur_bar["low"] <= tp_p:
                    hit_tp = True
                    exit_price = tp_p
                    reason = "TAKE_PROFIT"

            # 48-hour timeout
            if exit_price is None and hold_hours >= 48.0:
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
                    "entry_day": active_trade["entry_day"],
                    "entry_hour": active_trade["entry_hour"],
                    "exit_day": day_name,
                    "direction": direction,
                    "entry_price": entry_p,
                    "exit_price": exit_price,
                    "lots": lots,
                    "gross_pnl": gross_pnl,
                    "net_pnl": net_pnl,
                    "r_mult": r_mult,
                    "reason": reason,
                    "is_win": net_pnl > 0,
                    "hold_hours": hold_hours
                })
                active_trade = None

        # 2. Check Fresh Signal Entry
        if active_trade is None:
            # Check Friday filters
            if friday_mode == "NO_FRIDAY" and day_name == "Friday":
                continue
            elif friday_mode == "FRIDAY_CUTOFF_12UTC" and day_name == "Friday" and hour_utc >= 12:
                continue
            elif friday_mode == "FRIDAY_CUTOFF_15UTC" and day_name == "Friday" and hour_utc >= 15:
                continue

            # Standard session window: 06:00 to 20:00 UTC
            if not (6 <= hour_utc < 20):
                continue

            # CCRS USD Factor
            close_t = cur_bar["time_dt"]
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

            # ATR stops
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
                "entry_day": day_name,
                "entry_hour": hour_utc,
                "direction": direction,
                "entry_price": entry_price,
                "current_sl_price": sl_price,
                "current_tp_price": tp_price,
                "init_sl_points": sl_points,
                "lots": lots,
                "monetary_risk": monetary_risk,
                "cushion_stage": 0
            }

    df_trades = pd.DataFrame(trades)
    return df_trades, balance, max_dd_usd


def print_performance_table(df_trades: pd.DataFrame, label: str = "PORTFOLIO"):
    if df_trades.empty:
        print(f"[{label}] No trades recorded.")
        return

    total = len(df_trades)
    wins = df_trades[df_trades["is_win"]]
    losses = df_trades[~df_trades["is_win"]]
    wr = (len(wins) / total) * 100.0
    net_r = df_trades["r_mult"].sum()
    net_pnl = df_trades["net_pnl"].sum()
    gross_win = wins["net_pnl"].sum() if len(wins) > 0 else 0.0
    gross_loss = abs(losses["net_pnl"].sum()) if len(losses) > 0 else 0.001
    pf = gross_win / gross_loss

    avg_win_r = wins["r_mult"].mean() if len(wins) > 0 else 0.0
    avg_loss_r = losses["r_mult"].mean() if len(losses) > 0 else 0.0
    exp_r = net_r / total

    print(f"--- {label} ---")
    print(f"Trades: {total:3d} | Wins: {len(wins):2d} | Losses: {len(losses):2d} | Win Rate: {wr:5.1f}%")
    print(f"Net PnL: ${net_pnl:+9.2f} | Net R: {net_r:+6.2f}R | Profit Factor: {pf:5.2f} | Expectancy: {exp_r:+5.2f}R/trade")
    print(f"Avg Win: {avg_win_r:+5.2f}R (${(gross_win/len(wins) if len(wins)>0 else 0):.2f}) | Avg Loss: {avg_loss_r:+5.2f}R (${(gross_loss/len(losses) if len(losses)>0 else 0):.2f})")


def main():
    print("Loading 2-year institutional dataset...")
    with open("archives/portfolio_8pairs_cache.pkl", "rb") as f:
        d = pickle.load(f)

    pairs = ['EURUSD', 'GBPUSD', 'AUDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
    fx_closes = {}
    for p in pairs:
        df_p = d[p].copy()
        df_p['time_dt'] = pd.to_datetime(df_p['time_dt'], utc=True)
        fx_closes[p] = df_p.set_index('time_dt')['close']
    df_fx = pd.DataFrame(fx_closes).dropna()

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

    df_gold = d['XAUUSD'].copy()
    df_gold['time_dt'] = pd.to_datetime(df_gold['time_dt'], utc=True)

    print(f"Data range: {df_gold['time_dt'].min()} to {df_gold['time_dt'].max()} ({len(df_gold)} bars)\n")

    # =========================================================================
    # PART 1: BASELINE (ALL DAYS PERMITTED) - DAY OF WEEK BREAKDOWN
    # =========================================================================
    print("="*85)
    print("PART 1: EMPIRICAL PERFORMANCE BREAKDOWN BY DAY OF WEEK (Baseline)")
    print("="*85)
    df_trades, final_bal, max_dd = run_detailed_gold_backtest(df_gold, z_usd_series, ccrs_threshold=CCRS_USD_THRESHOLD, friday_mode="ALL")
    print_performance_table(df_trades, "TOTAL PORTFOLIO (All Days)")

    print("\n" + "-"*85)
    print(f"{'DAY OF WEEK':12s} | {'TRADES':6s} | {'WINS':4s} | {'LOSSES':6s} | {'WIN RATE':9s} | {'NET R':8s} | {'NET PNL':11s} | {'PROFIT FACTOR':13s} | {'EXPECTANCY':10s}")
    print("-"*85)

    days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    for day in days_order:
        d_tr = df_trades[df_trades["entry_day"] == day]
        if d_tr.empty:
            print(f"{day:12s} | 0 trades")
            continue
        tot = len(d_tr)
        w = len(d_tr[d_tr["is_win"]])
        l = tot - w
        wr = (w / tot) * 100.0
        nr = d_tr["r_mult"].sum()
        npnl = d_tr["net_pnl"].sum()
        gw = d_tr[d_tr["is_win"]]["net_pnl"].sum() if w > 0 else 0.0
        gl = abs(d_tr[~d_tr["is_win"]]["net_pnl"].sum()) if l > 0 else 0.001
        pf = gw / gl
        exp_r = nr / tot
        print(f"{day:12s} | {tot:6d} | {w:4d} | {l:6d} | {wr:8.1f}% | {nr:+7.2f}R | ${npnl:+10.2f} | {pf:13.2f} | {exp_r:+8.2f}R/tr")

    print("-"*85)

    # =========================================================================
    # PART 2: GRANULAR FRIDAY HOURLY PERFORMANCE
    # =========================================================================
    print("\n" + "="*85)
    print("PART 2: GRANULAR FRIDAY HOURLY BREAKDOWN")
    print("="*85)
    fri_trades = df_trades[df_trades["entry_day"] == "Friday"]
    if not fri_trades.empty:
        print(f"{'ENTRY HOUR (UTC)':16s} | {'TRADES':6s} | {'WINS':4s} | {'LOSSES':6s} | {'WIN RATE':9s} | {'NET R':8s} | {'NET PNL':11s} | {'REASON LIST':25s}")
        print("-"*85)
        for hr, grp in fri_trades.groupby("entry_hour"):
            tot = len(grp)
            w = len(grp[grp["is_win"]])
            l = tot - w
            wr = (w / tot) * 100.0
            nr = grp["r_mult"].sum()
            npnl = grp["net_pnl"].sum()
            reasons = ", ".join(grp["reason"].tolist())
            print(f"{hr:02d}:00 - {hr+1:02d}:00 UTC  | {tot:6d} | {w:4d} | {l:6d} | {wr:8.1f}% | {nr:+7.2f}R | ${npnl:+10.2f} | {reasons:25s}")
        print("-"*85)
    else:
        print("No Friday trades recorded in baseline.")

    # =========================================================================
    # PART 3: POLICY COMPARISON (ALL vs NO FRIDAY vs FRIDAY CUTOFFS)
    # =========================================================================
    print("\n" + "="*85)
    print("PART 3: POLICY EXPERIMENT COMPARISON")
    print("="*85)
    policies = [
        ("Policy A: Trade All Days (No Filter)", "ALL"),
        ("Policy B: Complete Friday Blacklist (No Friday Trades)", "NO_FRIDAY"),
        ("Policy C: Friday London Cutoff (No entries >= 12:00 UTC)", "FRIDAY_CUTOFF_12UTC"),
        ("Policy D: Friday NY Cutoff (No entries >= 15:00 UTC)", "FRIDAY_CUTOFF_15UTC"),
    ]

    for label, mode in policies:
        tr_df, bal, dd = run_detailed_gold_backtest(df_gold, z_usd_series, ccrs_threshold=CCRS_USD_THRESHOLD, friday_mode=mode)
        tot = len(tr_df)
        w = len(tr_df[tr_df["is_win"]])
        l = tot - w
        wr = (w / tot) * 100.0 if tot > 0 else 0
        nr = tr_df["r_mult"].sum() if tot > 0 else 0
        npnl = tr_df["net_pnl"].sum() if tot > 0 else 0
        gw = tr_df[tr_df["is_win"]]["net_pnl"].sum() if w > 0 else 0.0
        gl = abs(tr_df[~tr_df["is_win"]]["net_pnl"].sum()) if l > 0 else 0.001
        pf = gw / gl
        print(f"\n{label}")
        print(f"Trades: {tot:2d} | Win Rate: {wr:5.1f}% ({w}W / {l}L) | Net PnL: ${npnl:+9.2f} | Net R: {nr:+6.2f}R | PF: {pf:5.2f} | Max DD: ${dd:.2f}")


if __name__ == "__main__":
    main()
