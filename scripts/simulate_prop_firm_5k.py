#!/usr/bin/env python3
"""Canonical Prop Firm Challenge Simulation ($5,000 Account).

Evaluates the canonical institutional strategy under standard 2-step prop firm rules:
- Reference Account: $5,000 USD
- Risk per trade: 1.0% ($50) or 0.5% ($25)
- Daily Loss Limit: 3.0% ($150)
- Max Trailing / Overall Drawdown: 7.0% ($350)
- Phase 1 Profit Target: 8.0% (+$400 to $5,400)
- Phase 2 Profit Target: 5.0% (+$250 to $5,650)
- Canonical Universe: 6 institutional Forex pairs (EURUSD, USDCAD, GBPUSD, USDJPY, USDCHF, AUDUSD). Zero Gold.
- Zero look-ahead bias, fixed 15p TP / 10p SL, real transaction friction.
"""

import sys
from pathlib import Path
from typing import Dict, Any, List

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config import (
    CANONICAL_SYMBOLS,
    CANONICAL_TAKE_PROFIT_PIPS,
    CANONICAL_STOP_LOSS_PIPS,
    REFERENCE_ACCOUNT_EQUITY,
    REFERENCE_RISK_PCT,
    REFERENCE_RISK_BUDGET_USD,
)
from scripts.run_canonical_backtest import (
    load_historical_forex_data,
    simulate_portfolio_backtest,
)


def evaluate_prop_firm_challenge(
    trades: List[Dict[str, Any]],
    initial_balance: float = 5000.0,
    daily_limit_pct: float = 3.0,
    max_dd_limit_pct: float = 7.0,
    phase1_target_pct: float = 8.0,
    phase2_target_pct: float = 5.0,
    risk_pct_label: float = 1.0,
) -> Dict[str, Any]:
    """Evaluates chronological trade series against prop firm challenge pass/fail criteria."""
    balance = initial_balance
    peak_balance = initial_balance
    max_overall_dd_dollars = 0.0
    max_overall_dd_pct = 0.0
    max_daily_dd_pct = 0.0
    daily_pnl: Dict[str, float] = {}

    phase1_passed = False
    phase1_trade_idx = None
    phase2_passed = False
    phase2_trade_idx = None

    breached = False
    breach_reason = None

    print("=" * 115)
    print(f"PROP FIRM SIMULATION: ${initial_balance:,.2f} ACCOUNT | RISK PER TRADE: {risk_pct_label:.1f}%")
    print(f"Daily Loss Limit: {daily_limit_pct:.1f}% (${initial_balance * daily_limit_pct / 100:.2f}) | "
          f"Overall Max Drawdown: {max_dd_limit_pct:.1f}% (${initial_balance * max_dd_limit_pct / 100:.2f})")
    print(f"Phase 1 Target: {phase1_target_pct:.1f}% (+${initial_balance * phase1_target_pct / 100:.2f}) | "
          f"Phase 2 Target: {phase2_target_pct:.1f}% (+${initial_balance * phase2_target_pct / 100:.2f})")
    print(f"Strategy: Canonical Fixed Exits ({CANONICAL_TAKE_PROFIT_PIPS}p TP / {CANONICAL_STOP_LOSS_PIPS}p SL)")
    print("=" * 115)
    print(f"{'#':<3} | {'Entry Date':<16} | {'Pair':<7} {'Dir':<5} | {'Exit Date':<16} | {'Net R':<7} | {'Net PnL':<10} | {'Balance':<10} | {'Exit Reason'}")
    print("-" * 115)

    for idx, t in enumerate(trades, 1):
        pnl = t["net_usd"]
        balance += pnl

        exit_day = t["exit_time"].strftime("%Y-%m-%d")
        daily_pnl[exit_day] = daily_pnl.get(exit_day, 0.0) + pnl

        if balance > peak_balance:
            peak_balance = balance

        dd_dollars = peak_balance - balance
        dd_pct = (dd_dollars / peak_balance) * 100.0 if peak_balance > 0 else 0.0
        if dd_pct > max_overall_dd_pct:
            max_overall_dd_pct = dd_pct
            max_overall_dd_dollars = dd_dollars

        # Check phase completions
        p1_thresh = initial_balance * (1.0 + phase1_target_pct / 100.0)
        p2_thresh = initial_balance * (1.0 + (phase1_target_pct + phase2_target_pct) / 100.0)

        if not phase1_passed and balance >= p1_thresh:
            phase1_passed = True
            phase1_trade_idx = idx

        if phase1_passed and not phase2_passed and balance >= p2_thresh:
            phase2_passed = True
            phase2_trade_idx = idx

        # Check daily drawdown rule
        day_loss_pct = (-daily_pnl[exit_day] / balance) * 100.0 if daily_pnl[exit_day] < 0 else 0.0
        if day_loss_pct > max_daily_dd_pct:
            max_daily_dd_pct = day_loss_pct

        if not breached:
            if day_loss_pct >= daily_limit_pct:
                breached = True
                breach_reason = f"Daily Loss Limit Breached on {exit_day}: -{day_loss_pct:.2f}%"
            elif dd_pct >= max_dd_limit_pct:
                breached = True
                breach_reason = f"Max Drawdown Breached: {dd_pct:.2f}% (${dd_dollars:.2f})"

        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
        r_str = f"+{t['net_r']:.2f}R" if t['net_r'] >= 0 else f"{t['net_r']:.2f}R"
        print(f"{idx:<3} | {t['entry_time'].strftime('%Y-%m-%d %H:%M')} | {t['pair']:<7} {t['direction']:<5} | "
              f"{t['exit_time'].strftime('%Y-%m-%d %H:%M')} | {r_str:<7} | {pnl_str:<10} | ${balance:<9.2f} | {t['exit_reason']}")

    print("-" * 115)
    print("PROP FIRM PERFORMANCE SUMMARY:")
    print(f"Final Balance: ${balance:.2f} (Net Return: +${balance - initial_balance:.2f} / "
          f"+{((balance - initial_balance) / initial_balance) * 100:.2f}%)")
    print(f"Max Daily Drawdown: {max_daily_dd_pct:.2f}% (Limit: {daily_limit_pct:.1f}%) -> "
          f"{'SURVIVED' if max_daily_dd_pct < daily_limit_pct else 'BREACHED'}")
    print(f"Max Overall Drawdown: {max_overall_dd_pct:.2f}% (${max_overall_dd_dollars:.2f}) (Limit: {max_dd_limit_pct:.1f}%) -> "
          f"{'SURVIVED' if max_overall_dd_pct < max_dd_limit_pct else 'BREACHED'}")
    print(f"Phase 1 ({phase1_target_pct:.1f}% Target = ${initial_balance * (1.0 + phase1_target_pct / 100):.2f}): "
          f"{'PASSED at Trade #' + str(phase1_trade_idx) if phase1_passed else 'Not hit'}")
    print(f"Phase 2 ({phase2_target_pct:.1f}% Target = ${initial_balance * (1.0 + (phase1_target_pct + phase2_target_pct) / 100):.2f}): "
          f"{'PASSED at Trade #' + str(phase2_trade_idx) if phase2_passed else 'Not hit'}")
    print(f"Prop Firm Challenge Survival Status: "
          f"{'100% SURVIVED & PASSED' if (not breached and phase1_passed) else ('BREACHED: ' + str(breach_reason) if breached else 'SURVIVED (In Progress)')}")

    return {
        "final_balance": balance,
        "net_profit": balance - initial_balance,
        "max_daily_dd_pct": max_daily_dd_pct,
        "max_overall_dd_pct": max_overall_dd_pct,
        "phase1_passed": phase1_passed,
        "phase2_passed": phase2_passed,
        "breached": breached,
        "breach_reason": breach_reason,
    }


def main():
    try:
        data_dict = load_historical_forex_data()
    except FileNotFoundError as e:
        print(f"Dataset notice: {e}")
        return

    print("Executing Canonical Simulation at 1.0% Risk ($50 / trade)...")
    sim_1pct = simulate_portfolio_backtest(
        data_dict,
        initial_equity=5000.0,
        risk_pct=1.0,
        use_transaction_costs=True,
    )
    if "trades" in sim_1pct:
        evaluate_prop_firm_challenge(sim_1pct["trades"], initial_balance=5000.0, risk_pct_label=1.0)

    print("\n\nExecuting Canonical Simulation at 0.5% Risk ($25 / trade)...")
    sim_05pct = simulate_portfolio_backtest(
        data_dict,
        initial_equity=5000.0,
        risk_pct=0.5,
        use_transaction_costs=True,
    )
    if "trades" in sim_05pct:
        evaluate_prop_firm_challenge(sim_05pct["trades"], initial_balance=5000.0, risk_pct_label=0.5)


if __name__ == "__main__":
    main()
