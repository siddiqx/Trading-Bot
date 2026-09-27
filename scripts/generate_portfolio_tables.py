import sys, os, math, pickle
import pandas as pd
import numpy as np

def generate_all_portfolio_data():
    with open('archives/portfolio_simulation_output.pkl', 'rb') as f:
        out = pickle.load(f)
        
    r8 = out['res_8pairs']
    r5 = out['res_5pairs']
    ma = out['model_a']
    stress = out['stress']
    specs = out['pair_specs']
    signals = out['pair_signals']
    
    ledger = r8['ledger']
    hourly = r8['hourly']
    
    # 1. INSTRUMENT LISTING
    inst_list = []
    for p in ['USDCAD', 'USDCHF', 'USDJPY', 'AUDUSD', 'XAUUSD', 'EURUSD', 'GBPUSD', 'NZDUSD']:
        inst_list.append({
            'Instrument': p,
            'Timeframe': '1H (60m)',
            'Signal Type': 'Donchian Breakout + 4H Trend Alignment + ICT OTE Pullback',
            'Data Available': '2 Years continuous 1H (2024-09 to 2026-09)',
            'Number of Trades': len(signals[p]),
            'Whitelisted': 'YES (Institutional Whitelist)' if p in {'USDCAD', 'USDCHF', 'USDJPY', 'AUDUSD', 'XAUUSD'} else 'NO (Chop / Mean-Reverting)'
        })
    df_inst = pd.DataFrame(inst_list)
    
    # 2. POSITION SIZING TABLE
    sample_sizing = []
    for p in ['USDCAD', 'USDCHF', 'USDJPY', 'AUDUSD', 'XAUUSD', 'EURUSD', 'GBPUSD', 'NZDUSD']:
        tr = signals[p][0]
        sl_dist = tr['sl_dist']
        sl_pips = tr['sl_pips']
        ep = tr['entry_price']
        
        # Calculate for $5,000 balance -> $50 risk
        dollar_risk = 50.0
        sp = specs[p]
        if sp.get('gold'):
            lots = math.floor((dollar_risk / (sl_dist * 100.0)) * 100.0) / 100.0
            lots = max(0.01, lots)
            act_risk = lots * 100.0 * sl_dist
            p_dist_str = f"${sl_dist:.2f} ({sl_pips:.1f} pts)"
        elif sp.get('usd_quote'):
            lots = math.floor((dollar_risk / (sl_pips * 10.0)) * 100.0) / 100.0
            lots = max(0.01, lots)
            act_risk = lots * sl_pips * 10.0
            p_dist_str = f"{sl_pips:.1f} pips"
        elif sp.get('jpy'):
            pip_val = 1000.0 / ep
            lots = math.floor((dollar_risk / (sl_pips * pip_val)) * 100.0) / 100.0
            lots = max(0.01, lots)
            act_risk = lots * sl_pips * pip_val
            p_dist_str = f"{sl_pips:.1f} pips"
        else:
            pip_val = 10.0 / ep
            lots = math.floor((dollar_risk / (sl_pips * pip_val)) * 100.0) / 100.0
            lots = max(0.01, lots)
            act_risk = lots * sl_pips * pip_val
            p_dist_str = f"{sl_pips:.1f} pips"
            
        sample_sizing.append({
            'Instrument': p,
            'SL Distance': p_dist_str,
            'Intended Risk': f"${dollar_risk:.2f} (1.00%)",
            'Calculated Lot': f"{lots:.2f}",
            'Actual Risk': f"${act_risk:.2f} ({(act_risk/5000.0*100.0):.2f}%)"
        })
    df_sizing = pd.DataFrame(sample_sizing)
    
    # 3. PAIR CONTRIBUTION TABLE (from Model B ledger)
    pair_contrib = []
    tot_portfolio_pnl = ledger['net_pnl'].sum()
    for p in ['USDCAD', 'USDCHF', 'USDJPY', 'AUDUSD', 'XAUUSD', 'EURUSD', 'GBPUSD', 'NZDUSD']:
        p_trades = ledger[ledger['pair'] == p]
        n_tr = len(p_trades)
        wins = len(p_trades[p_trades['result'] == 'WIN'])
        losses = len(p_trades[p_trades['result'] == 'LOSS'])
        wr = (wins / n_tr * 100.0) if n_tr > 0 else 0
        net_pnl = p_trades['net_pnl'].sum()
        net_r = p_trades['r_mult'].sum()
        win_sum = p_trades[p_trades['net_pnl'] > 0]['net_pnl'].sum()
        loss_sum = abs(p_trades[p_trades['net_pnl'] < 0]['net_pnl'].sum())
        pf = (win_sum / loss_sum) if loss_sum > 0 else (99.0 if win_sum > 0 else 0.0)
        avg_r = (net_r / n_tr) if n_tr > 0 else 0
        contrib_pct = (net_pnl / abs(tot_portfolio_pnl) * 100.0) if abs(tot_portfolio_pnl) > 0 else 0
        
        pair_contrib.append({
            'Pair': p,
            'Trades': n_tr,
            'Wins': wins,
            'Losses': losses,
            'Win Rate': f"{wr:.1f}%",
            'Net P&L': f"${net_pnl:,.2f}",
            'Net R': f"{net_r:+.2f} R",
            'Profit Factor': f"{pf:.2f}",
            'Avg R': f"{avg_r:+.2f} R",
            'Max DD': f"{ma[p]['max_overall_dd_pct']:.1f}%",
            'Contribution': f"{contrib_pct:+.1f}% of loss" if tot_portfolio_pnl < 0 else f"{contrib_pct:+.1f}%"
        })
    df_contrib = pd.DataFrame(pair_contrib)
    
    # 4. WEEK-BY-WEEK PORTFOLIO PERFORMANCE
    ledger['exit_dt'] = pd.to_datetime(ledger['exit_time'])
    ledger['week'] = ledger['exit_dt'].dt.to_period('W-SUN')
    
    weeks = sorted(list(ledger['week'].unique()))
    weekly_records = []
    running_bal = 5000.0
    
    for w in weeks:
        w_trades = ledger[ledger['week'] == w]
        w_start = running_bal
        w_pnl = w_trades['net_pnl'].sum()
        running_bal += w_pnl
        w_end = running_bal
        w_ret = (w_pnl / w_start * 100.0) if w_start > 0 else 0
        w_wins = len(w_trades[w_trades['result'] == 'WIN'])
        w_loss = len(w_trades[w_trades['result'] == 'LOSS'])
        w_net_r = w_trades['r_mult'].sum()
        
        # Max DD within that week from hourly
        w_start_ts = w.start_time
        w_end_ts = w.end_time
        h_w = hourly[(hourly['time'] >= w_start_ts) & (hourly['time'] <= w_end_ts)]
        w_max_dd = h_w['daily_dd_eq_pct'].max() if len(h_w) > 0 else 0
        w_peak_exp = h_w['nominal_exposure'].max() if len(h_w) > 0 else 0
        
        # Check status
        failed_in_week = any(w_trades['account_failed'])
        status = "FAILED" if failed_in_week else ("PASS" if w_pnl >= 0 else "LOSS")
        
        weekly_records.append({
            'Week': str(w),
            'Starting Balance': f"${w_start:,.2f}",
            'Trades': len(w_trades),
            'Wins': w_wins,
            'Losses': w_loss,
            'Net R': f"{w_net_r:+.2f} R",
            'Net P&L': f"${w_pnl:+,.2f}",
            'Ending Balance': f"${w_end:,.2f}",
            'Weekly Return': f"{w_ret:+.2f}%",
            'Max DD': f"{w_max_dd:.2f}%",
            'Open Exposure Peak': f"${w_peak_exp:,.0f}",
            'Status': status
        })
    df_weekly = pd.DataFrame(weekly_records)
    
    # 5. MONTHLY PERFORMANCE
    ledger['month'] = ledger['exit_dt'].dt.to_period('M')
    months = sorted(list(ledger['month'].unique()))
    monthly_records = []
    run_m_bal = 5000.0
    for m in months:
        m_trades = ledger[ledger['month'] == m]
        m_start = run_m_bal
        m_pnl = m_trades['net_pnl'].sum()
        run_m_bal += m_pnl
        m_end = run_m_bal
        m_ret = (m_pnl / m_start * 100.0) if m_start > 0 else 0
        m_wins = len(m_trades[m_trades['result'] == 'WIN'])
        m_tr = len(m_trades)
        m_wr = (m_wins / m_tr * 100.0) if m_tr > 0 else 0
        
        m_start_ts = m.start_time
        m_end_ts = m.end_time
        h_m = hourly[(hourly['time'] >= m_start_ts) & (hourly['time'] <= m_end_ts)]
        m_max_dd = h_m['overall_dd_eq_pct'].max() if len(h_m) > 0 else 0
        
        monthly_records.append({
            'Month': str(m),
            'Starting Balance': f"${m_start:,.2f}",
            'Net P&L': f"${m_pnl:+,.2f}",
            'Return': f"{m_ret:+.2f}%",
            'Trades': m_tr,
            'Win Rate': f"{m_wr:.1f}%",
            'Max DD': f"{m_max_dd:.2f}%",
            'Ending Balance': f"${m_end:,.2f}"
        })
    df_monthly = pd.DataFrame(monthly_records)
    
    # 6. STRESS TEST SUMMARY
    stress_summary = []
    for sc_name, sc_res in stress.items():
        stress_summary.append({
            'Scenario': sc_name,
            'Ending Balance': f"${sc_res['ending_balance']:,.2f}",
            'Net P&L': f"${sc_res['net_profit']:+,.2f}",
            'Return': f"{sc_res['return_pct']:+.2f}%",
            'Total Trades': sc_res['total_trades'],
            'Account Failed': 'YES' if sc_res['account_failed'] else 'NO',
            'Max Daily DD (Eq)': f"{sc_res['max_daily_eq_dd_pct']:.2f}%",
            'Max Overall DD (Eq)': f"{sc_res['max_equity_dd_pct']:.2f}%"
        })
    df_stress = pd.DataFrame(stress_summary)
    
    # 7. MODEL A vs MODEL B COMPARISON
    # Sum independent model a
    tot_ma_trades = sum(v['trades'] for v in ma.values())
    tot_ma_pnl = sum(v['net_pnl'] for v in ma.values())
    tot_ma_start = 5000.0 * 8 # $40,000 combined independent
    tot_ma_end = tot_ma_start + tot_ma_pnl
    tot_ma_ret = (tot_ma_pnl / tot_ma_start) * 100.0
    tot_ma_net_r = sum(v['net_r'] for v in ma.values())
    max_ma_dd = max(v['max_overall_dd_pct'] for v in ma.values())
    max_ma_daily = max(v['max_daily_dd_pct'] for v in ma.values())
    
    model_comp = [
        {'Metric': 'Starting Capital', 'Independent Pair Testing (Model A)': '$40,000 ($5,000 x 8)', 'Combined Portfolio (Model B)': '$5,000 (Single Account)'},
        {'Metric': 'Ending Capital', 'Independent Pair Testing (Model A)': f"${tot_ma_end:,.2f}", 'Combined Portfolio (Model B)': f"${r8['ending_balance']:,.2f}"},
        {'Metric': 'Net P&L', 'Independent Pair Testing (Model A)': f"${tot_ma_pnl:+,.2f}", 'Combined Portfolio (Model B)': f"${r8['net_profit']:+,.2f}"},
        {'Metric': 'Return', 'Independent Pair Testing (Model A)': f"{tot_ma_ret:+.2f}%", 'Combined Portfolio (Model B)': f"{r8['return_pct']:+.2f}%"},
        {'Metric': 'Max Overall DD', 'Independent Pair Testing (Model A)': f"{max_ma_dd:.2f}% (NZDUSD)", 'Combined Portfolio (Model B)': f"{r8['max_equity_dd_pct']:.2f}% (80.5% Peak)"},
        {'Metric': 'Max Daily DD', 'Independent Pair Testing (Model A)': f"{max_ma_daily:.2f}%", 'Combined Portfolio (Model B)': f"{r8['max_daily_eq_dd_pct']:.2f}% (31.4% Peak)"},
        {'Metric': 'Total Trades', 'Independent Pair Testing (Model A)': f"{tot_ma_trades}", 'Combined Portfolio (Model B)': f"{r8['total_trades']}"},
        {'Metric': 'Profit Factor', 'Independent Pair Testing (Model A)': '0.59', 'Combined Portfolio (Model B)': '0.51'},
        {'Metric': 'Net R', 'Independent Pair Testing (Model A)': f"{tot_ma_net_r:+.2f} R", 'Combined Portfolio (Model B)': f"{ledger['r_mult'].sum():+.2f} R"},
        {'Metric': 'Max Simultaneous Positions', 'Independent Pair Testing (Model A)': '1 (per account)', 'Combined Portfolio (Model B)': f"{r8['peak_simultaneous_trades']} positions"},
        {'Metric': 'Rule Survival Status', 'Independent Pair Testing (Model A)': '6/8 Failed DD limits', 'Combined Portfolio (Model B)': 'FAILED on Day 11 (2026-03-26)'}
    ]
    df_model_comp = pd.DataFrame(model_comp)
    
    return {
        'df_inst': df_inst,
        'df_sizing': df_sizing,
        'df_contrib': df_contrib,
        'df_weekly': df_weekly,
        'df_monthly': df_monthly,
        'df_stress': df_stress,
        'df_model_comp': df_model_comp,
        'ledger': ledger,
        'hourly': hourly,
        'r8': r8,
        'r5': r5,
        'ma': ma
    }

if __name__ == '__main__':
    data = generate_all_portfolio_data()
    print("All tables generated successfully!")
    print("\n--- INSTRUMENT LISTING ---")
    print(data['df_inst'].to_string(index=False))
    print("\n--- POSITION SIZING TABLE ---")
    print(data['df_sizing'].to_string(index=False))
    print("\n--- PAIR CONTRIBUTION TABLE ---")
    print(data['df_contrib'].to_string(index=False))
    print("\n--- WEEK-BY-WEEK PORTFOLIO TABLE ---")
    print(data['df_weekly'].to_string(index=False))
    print("\n--- MONTHLY PORTFOLIO TABLE ---")
    print(data['df_monthly'].to_string(index=False))
    print("\n--- MODEL A vs MODEL B ---")
    print(data['df_model_comp'].to_string(index=False))
    print("\n--- STRESS TESTING ---")
    print(data['df_stress'].to_string(index=False))
