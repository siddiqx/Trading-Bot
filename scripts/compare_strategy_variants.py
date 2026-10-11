"""
Compare Baseline against Legacy Strategy and Filter Experiments on the exact same data window.
"""

import sys
sys.path.append('.')
import pickle
import numpy as np
import pandas as pd
from scripts.generate_full_audit_report import analyze_portfolio_metrics

def run_experiments():
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        cache_data = pickle.load(f)
    pairs_data = cache_data[1]

    forex_pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'USDCHF', 'AUDUSD']
    start_date = '2025-10-01 00:00:00'
    end_date = '2026-03-31 23:45:00'

    # Load baseline
    with open('scripts/six_month_trades_baseline.pkl', 'rb') as f:
        baseline_df = pickle.load(f)
    m_base = analyze_portfolio_metrics(baseline_df, "BASELINE (15p TP / 10p SL)")

    print("================================================================================")
    print("SECTION F: COMPARATIVE STRATEGY EXPERIMENTS (OCT 1, 2025 - MAR 31, 2026)")
    print("================================================================================")
    print(f"Variant A (Baseline Fixed 15p TP / 10p SL):")
    print(f"  Trades: {m_base['total_trades']} | WR: {m_base['win_rate']:.1f}% | Net Pips: {m_base['net_pips']:+.1f} | PF: {m_base['profit_factor']:.2f} | Exp: {m_base['net_expectancy_pips']:+.2f}p")

    # Variant B: Legacy Exit Rules (Dynamic 32-50 pip targets with Breakeven move at +18p)
    legacy_trades = []
    for pair in forex_pairs:
        m15 = pairs_data[pair]['M15'].copy()
        time_to_idx = {int(t): i for i, t in enumerate(m15['time'].values)}
        pair_baseline = baseline_df[baseline_df['pair'] == pair]
        pip_unit = 0.01 if 'JPY' in pair else 0.0001

        high_arr = m15['high'].values
        low_arr = m15['low'].values
        close_arr = m15['close'].values

        for _, t in pair_baseline.iterrows():
            entry_unix = int(pd.Timestamp(t['entry_time']).timestamp())
            if entry_unix not in time_to_idx:
                continue
            e_idx = time_to_idx[entry_unix]
            entry_p = t['entry_price']
            is_long = t['direction'] == 'LONG'
            spread_p = t['spread_pips']

            tp_p = entry_p + (32.0 * pip_unit) if is_long else entry_p - (32.0 * pip_unit)
            sl_p = entry_p - (20.0 * pip_unit) if is_long else entry_p + (20.0 * pip_unit)
            be_p = entry_p + (1.0 * pip_unit) if is_long else entry_p - (1.0 * pip_unit)
            be_active = False

            outcome = None
            exit_p = 0.0
            max_bar = min(len(high_arr), e_idx + 160)
            for j in range(e_idx, max_bar):
                h = high_arr[j]
                l = low_arr[j]
                c = close_arr[j]

                if is_long:
                    if h >= entry_p + (18.0 * pip_unit):
                        be_active = True
                    cur_sl = be_p if be_active else sl_p
                    if h >= tp_p:
                        outcome = 'WIN'
                        exit_p = tp_p
                        break
                    elif l <= cur_sl:
                        outcome = 'BREAK_EVEN' if be_active else 'LOSS'
                        exit_p = cur_sl
                        break
                else:
                    if l <= entry_p - (18.0 * pip_unit):
                        be_active = True
                    cur_sl = be_p if be_active else sl_p
                    if l <= tp_p:
                        outcome = 'WIN'
                        exit_p = tp_p
                        break
                    elif h >= cur_sl:
                        outcome = 'BREAK_EVEN' if be_active else 'LOSS'
                        exit_p = cur_sl
                        break

            if exit_p == 0.0:
                exit_p = close_arr[min(len(close_arr)-1, e_idx + 160)]
                outcome = 'WIN' if ((exit_p > entry_p) if is_long else (exit_p < entry_p)) else 'LOSS'

            gross_p = (exit_p - entry_p)/pip_unit if is_long else (entry_p - exit_p)/pip_unit
            costs = spread_p + 0.85
            net_p = gross_p - costs
            legacy_trades.append({
                'pair': pair,
                'outcome': outcome,
                'gross_pips': gross_p,
                'costs_pips': costs,
                'net_pips': net_p,
                'realized_r': net_p / 20.0,
                'exit_reason': outcome,
                'hold_bars': 20,
                'spread_pips': spread_p,
                'exit_time': t['exit_time']
            })

    df_legacy = pd.DataFrame(legacy_trades)
    m_legacy = analyze_portfolio_metrics(df_legacy, "LEGACY (32p TP / 20p SL with BE)")
    print(f"\nVariant B (Legacy Reconstructed: 32p TP / 20p SL with Breakeven at +18p):")
    print(f"  Trades: {m_legacy['total_trades']} | WR: {m_legacy['win_rate']:.1f}% | Net Pips: {m_legacy['net_pips']:+.1f} | PF: {m_legacy['profit_factor']:.2f} | Exp: {m_legacy['net_expectancy_pips']:+.2f}p | MaxDD: {m_legacy['max_drawdown_pips']:.1f}p")

    # Variant C: Secondary Pair Conviction Guard (filter low momentum chop)
    from scripts.backtest_six_months_forex_audit import run_six_months_audit
    # Run simulation for Variant C
    from scripts.backtest_six_months_forex_audit import pair_dfs

if __name__ == '__main__':
    run_experiments()
