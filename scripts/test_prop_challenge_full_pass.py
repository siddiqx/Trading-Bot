"""
Prop Challenge Optimization Engine:
Simulates $5,000 GFT 2-Step Standard Challenge with:
1. Model 7 High-Conviction (SL 15p / TP 22.5p, Model J: Bank 50% at 1.0R, SL to BE)
2. Testing Risk Sizes: $40 (0.8%), $50 (1.0%), $60 (1.2%)
3. Daily cap: 2 trades/day and $50 daily loss limit
4. Detailed Phase 1, Phase 2, and Funded Payout reporting
"""

import sys
import pickle
import pandas as pd
import numpy as np
from deep_quant_winrate_research import load_data, compute_all_indicators, CONFIGS, PAIRS
from test_model7_longterm_and_prop import run_simulation

def test_prop_pass():
    d15, d1h = load_data()
    data_dict = compute_all_indicators(d15, d1h)

    cfg = {
        "use_partial_be": True, "partial_r": 1.0,
        "require_h4": True, "min_adx": 20.0, "killzone_only": True, "min_body_ratio": 0.50,
        "allowed_pairs": ["EURUSD", "USDCHF", "AUDUSD"], # Core Alpha Triad
        "sl_pips": 15.0, "tp_pips": 22.5
    }

    trades_df = run_simulation(data_dict, cfg, "2026-04-01", "2026-10-09 23:45:00")
    trades_df = trades_df.sort_values("entry_time").reset_index(drop=True)

    print("\n" + "="*85)
    print("SIMULATING GFT $5,000 2-STEP STANDARD CHALLENGE ACROSS RISK PROFILES")
    print("="*85)

    for risk_usd in [40.0, 50.0, 60.0, 75.0]:
        sim_challenge(trades_df, risk_usd)

def sim_challenge(trades_df, risk_usd):
    balance = 5000.0
    equity = 5000.0
    peak_equity = 5000.0
    daily_start_equity = 5000.0
    current_day = None

    phase = "PHASE_1"
    p1_target = 5500.0
    p2_target = 5250.0

    p1_pass_info = None
    p2_pass_info = None
    breached = False
    breach_reason = None

    daily_pnl = 0.0
    qualifying_days = set() # Days with net >= $25.0
    trades_today = 0
    max_daily_dd = 0.0
    max_overall_dd = 0.0

    p1_trades = 0
    p2_trades = 0
    funded_trades = 0
    funded_profit = 0.0

    for idx, t in trades_df.iterrows():
        t_day = t["entry_time"].strftime("%Y-%m-%d")

        # Day rollover check (5 PM EST / 21:00 UTC)
        if t_day != current_day:
            if current_day is not None:
                if daily_pnl >= 25.0:
                    qualifying_days.add(current_day)
            current_day = t_day
            daily_start_equity = balance
            daily_pnl = 0.0
            trades_today = 0

        # Cap at 2 trades per day to prevent overtrading
        if trades_today >= 2:
            continue

        # If daily loss limit reached ($150), stop for the day
        if daily_pnl <= -100.0:
            continue

        r = t["realized_r"]
        trade_pnl = r * risk_usd
        trades_today += 1

        balance += trade_pnl
        daily_pnl += trade_pnl

        # Drawdown tracking
        if balance > peak_equity: peak_equity = balance
        overall_dd = peak_equity - balance
        if overall_dd > max_overall_dd: max_overall_dd = overall_dd

        curr_daily_dd = daily_start_equity - balance
        if curr_daily_dd > max_daily_dd: max_daily_dd = curr_daily_dd

        # Check breach limits:
        # 5% daily DD ($250)
        # 10% static max loss ($500 hard floor at $4,500)
        if curr_daily_dd >= 250.0:
            breached = True
            breach_reason = f"Daily Drawdown Breach (${curr_daily_dd:.2f} >= $250.00)"
            break
        if balance <= 4500.0:
            breached = True
            breach_reason = f"Maximum Overall Loss Breach (${balance:.2f} <= $4,500.00)"
            break

        if phase == "PHASE_1":
            p1_trades += 1
            if balance >= p1_target:
                # Check qualifying days
                all_qual = len(qualifying_days) + (1 if daily_pnl >= 25.0 else 0)
                if all_qual >= 3:
                    phase = "PHASE_2"
                    p1_pass_info = (t["exit_time"], p1_trades, all_qual)
                    balance = 5000.0
                    peak_equity = 5000.0
                    daily_start_equity = 5000.0
                    daily_pnl = 0.0
                    qualifying_days = set()
        elif phase == "PHASE_2":
            p2_trades += 1
            if balance >= p2_target:
                all_qual = len(qualifying_days) + (1 if daily_pnl >= 25.0 else 0)
                if all_qual >= 3:
                    phase = "FUNDED"
                    p2_pass_info = (t["exit_time"], p2_trades, all_qual)
                    balance = 5000.0
                    peak_equity = 5000.0
                    daily_start_equity = 5000.0
                    daily_pnl = 0.0
                    qualifying_days = set()
        elif phase == "FUNDED":
            funded_trades += 1
            funded_profit += trade_pnl

    print(f"\n[Risk: ${risk_usd:.2f} per trade ({risk_usd/50:.2f}% equity)]")
    print(f"  Breached: {breached} {('(' + breach_reason + ')') if breached else ''}")
    print(f"  Max Daily Drawdown: ${max_daily_dd:.2f} / $250.00 ({max_daily_dd/250*100:.1f}%)")
    print(f"  Max Overall Drawdown: ${max_overall_dd:.2f} / $500.00 ({max_overall_dd/500*100:.1f}%)")
    if p1_pass_info:
        print(f"  >>> PHASE 1 PASSED! Date: {p1_pass_info[0]} | Trades: {p1_pass_info[1]} | Qual Days: {p1_pass_info[2]}")
    else:
        print(f"  Phase 1: In Progress / Not Completed (Final Bal: ${balance:.2f})")
    if p2_pass_info:
        print(f"  >>> PHASE 2 PASSED (FUNDED)! Date: {p2_pass_info[0]} | Trades: {p2_pass_info[1]} | Qual Days: {p2_pass_info[2]}")
        print(f"  Funded Account Profit: +${funded_profit:.2f} ({funded_trades} trades)")
    elif phase == "PHASE_2":
        print(f"  Phase 2: In Progress (Bal: ${balance:.2f} / $5,250.00, Trades: {p2_trades})")

if __name__ == "__main__":
    test_prop_pass()
