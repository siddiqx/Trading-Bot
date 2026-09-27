"""
Test the combination of:
1. Breakeven at +1.0R
2. Friday Cutoff at 15:00 UTC
3. Dynamic Risk Sizing (1.25% Phase 1 / 1.0% Phase 2)
"""

import pickle
import pandas as pd
import numpy as np

def run_combined_test():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
    df = all_data['XAUUSD'].copy()
    if df['time_dt'].dt.tz is not None:
        df['time_dt'] = df['time_dt'].dt.tz_localize(None)

    import sys, os
    sys.path.insert(0, os.path.abspath('.'))
    from scripts.deep_strategy_enhancement_audit import simulate_exact_gold, eval_simulation_metrics
    
    # 1. Benchmark
    t_bench = simulate_exact_gold(df, fri_cutoff_hour=12, be_r=None, rr=1.75)
    
    # 2. Strategy Improvement: Fri 15h Cutoff + BE at +1.0R
    t_improved = simulate_exact_gold(df, fri_cutoff_hour=15, be_r=1.0, rr=1.75)
    
    # Let's evaluate under standard 1.0% risk:
    r_bench = eval_simulation_metrics(t_bench, risk_pct=1.0)
    r_imp_10 = eval_simulation_metrics(t_improved, risk_pct=1.0)
    
    # Let's evaluate under 1.25% Phase 1 risk sizing:
    # Custom simulation for phase-specific sizing on improved trades:
    def eval_dynamic_risk(trades, r1=1.25, r2=1.0, name=""):
        tdf = pd.DataFrame(trades)
        n = len(tdf)
        cash_r1 = 5000.0 * (r1 / 100.0)
        cash_r2 = 5000.0 * (r2 / 100.0)
        max_dd = 5000.0 * 0.08 # $400
        
        p1_days, p2_days, tot_days = [], [], []
        p1_trades, p2_trades = [], []
        runs, breaches = 0, 0
        
        for start_i in range(0, n - 15):
            runs += 1
            # Phase 1: $400
            p1_cum = 0.0
            p1_i = start_i
            p1_pass = False
            p1_peak = 0.0
            while p1_i < n:
                pnl = tdf.iloc[p1_i]['r'] * cash_r1
                p1_cum += pnl
                p1_peak = max(p1_peak, p1_cum)
                if (p1_peak - p1_cum) >= max_dd:
                    breaches += 1
                    break
                if p1_cum >= 400.0:
                    p1_pass = True
                    break
                p1_i += 1
            if not p1_pass:
                continue
            p1_d = (tdf.iloc[p1_i]['exit_dt'] - tdf.iloc[start_i]['entry_dt']).days
            p1_tr = p1_i - start_i + 1
            
            # Phase 2: $250
            p2_cum = 0.0
            p2_i = p1_i + 1
            p2_pass = False
            p2_peak = 0.0
            while p2_i < n:
                pnl = tdf.iloc[p2_i]['r'] * cash_r2
                p2_cum += pnl
                p2_peak = max(p2_peak, p2_cum)
                if (p2_peak - p2_cum) >= max_dd:
                    breaches += 1
                    break
                if p2_cum >= 250.0:
                    p2_pass = True
                    break
                p2_i += 1
            if not p2_pass:
                continue
            p2_d = (tdf.iloc[p2_i]['exit_dt'] - tdf.iloc[p1_i + 1]['entry_dt']).days
            p2_tr = p2_i - (p1_i + 1) + 1
            
            tot_d = p1_d + 1 + p2_d + 1 + 14
            p1_days.append(p1_d)
            p2_days.append(p2_d)
            tot_days.append(tot_d)
            p1_trades.append(p1_tr)
            p2_trades.append(p2_tr)
            
        pass_rate = (len(tot_days) / runs * 100.0) if runs > 0 else 0.0
        wins = (tdf['result'] == 'WIN').sum()
        wr = (wins / n) * 100.0
        win_r = tdf[tdf['result'] == 'WIN']['r'].sum()
        loss_r = abs(tdf[tdf['result'] == 'LOSS']['r'].sum())
        pf = win_r / loss_r if loss_r > 0 else 99.0
        
        # Max DD calculation under 1.25% risk
        equity, peak, max_dd_dollars = 0.0, 0.0, 0.0
        for r in tdf['r']:
            equity += r * cash_r1
            peak = max(peak, equity)
            dd = peak - equity
            if dd > max_dd_dollars:
                max_dd_dollars = dd
                
        return {
            'Architecture': name,
            'Trades': n,
            'Win Rate': f"{wr:.1f}%",
            'Profit Factor': f"{pf:.2f}",
            'Max DD ($)': f"${max_dd_dollars:.0f} ({(max_drawdown_dollars/5000)*100:.1f}%)" if 'max_drawdown_dollars' in locals() else f"${max_dd_dollars:.0f} ({(max_dd_dollars/5000)*100:.1f}%)",
            'Phase 1 (Days)': f"{np.median(p1_days):.0f} d (~{np.median(p1_days)/7:.1f} w)",
            'Phase 2 (Days)': f"{np.median(p2_days):.0f} d (~{np.median(p2_days)/7:.1f} w)",
            'Total Payout (Days)': f"{np.median(tot_days):.0f} d (~{np.median(tot_days)/30:.1f} mo)",
            'Pass Rate': f"{pass_rate:.1f}%"
        }

    out = []
    out.append(eval_dynamic_risk(t_bench, 1.0, 1.0, name="1. Current Benchmark (Gold Tuned @ 1.0% Risk)"))
    out.append(eval_dynamic_risk(t_improved, 1.0, 1.0, name="2. Strategy Upgrade: BE @ +1.0R + Fri 15h (@ 1.0% Risk)"))
    out.append(eval_dynamic_risk(t_improved, 1.25, 1.0, name="3. Optimized Acceleration: Strategy Upgrade + 1.25% Phase 1 Risk"))
    out.append(eval_dynamic_risk(t_improved, 1.50, 1.0, name="4. Max Acceleration: Strategy Upgrade + 1.50% Phase 1 Risk"))

    print("=" * 130)
    print("RESULTS: SPEEDUP POTENTIAL THROUGH STRATEGY IMPROVEMENT + ASYMMETRIC SIZING")
    print("=" * 130)
    print(pd.DataFrame(out).to_string(index=False))

    # Also test on 2-Year Dataset
    t_bench_2y = simulate_exact_gold(df, fri_cutoff_hour=12, be_r=None, rr=1.75, start_date=None)
    t_imp_2y = simulate_exact_gold(df, fri_cutoff_hour=15, be_r=1.0, rr=1.75, start_date=None)
    
    out_2y = []
    out_2y.append(eval_dynamic_risk(t_bench_2y, 1.0, 1.0, name="1. 2-Year Benchmark (Gold Tuned @ 1.0% Risk)"))
    out_2y.append(eval_dynamic_risk(t_imp_2y, 1.0, 1.0, name="2. 2-Year Strategy Upgrade: BE @ +1.0R + Fri 15h (@ 1.0% Risk)"))
    out_2y.append(eval_dynamic_risk(t_imp_2y, 1.25, 1.0, name="3. 2-Year Optimized Acceleration: Strategy Upgrade + 1.25% P1"))

    print("\n" + "=" * 130)
    print("RESULTS: 2-YEAR EXTENDED HISTORICAL VALIDATION (104 WEEKS: 2024-2026)")
    print("=" * 130)
    print(pd.DataFrame(out_2y).to_string(index=False))

if __name__ == '__main__':
    run_combined_test()
