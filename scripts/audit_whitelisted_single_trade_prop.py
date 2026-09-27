import sys, os, math, pickle
from datetime import datetime, timezone
import pandas as pd
import numpy as np

def run_single_trade_whitelisted_audit():
    with open('archives/portfolio_simulation_output.pkl', 'rb') as f:
        out = pickle.load(f)
        
    all_signals = out['pair_signals']
    pair_specs = out['pair_specs']
    
    # Whitelisted pairs only
    whitelisted_pairs = ['XAUUSD', 'USDCAD', 'AUDUSD', 'USDJPY', 'USDCHF']
    pair_priority = {
        'XAUUSD': 1, # Top performer / priority
        'USDCAD': 2,
        'AUDUSD': 3,
        'USDJPY': 4,
        'USDCHF': 5
    }
    
    STARTING_BALANCE = 5000.0
    RISK_PCT = 0.01 # 1% dynamic risk
    MAX_DAILY_DD_PCT = 0.03 # 3% = $150
    MAX_OVERALL_DD_PCT = 0.08 # 8% = $400
    
    # Collect all signals from whitelisted pairs into one list
    raw_signal_list = []
    for pair in whitelisted_pairs:
        for tr in all_signals[pair]:
            raw_signal_list.append({
                'pair': pair,
                'direction': tr['direction'],
                'entry_time': tr['entry_time'],
                'entry_price': tr['entry_price'],
                'sl_price': tr['sl_price'],
                'tp_price': tr['tp_price'],
                'exit_time': tr['exit_time'],
                'exit_price': tr['exit_price'],
                'result': tr['result'],
                'sl_dist': tr['sl_dist'],
                'sl_pips': tr['sl_pips'],
                'hold_bars': tr['hold_bars'],
                'priority': pair_priority[pair]
            })
            
    # Sort signals by entry_time, then priority
    raw_signal_list.sort(key=lambda x: (x['entry_time'], x['priority']))
    
    # -------------------------------------------------------------
    # SIMULATION: STRICT SINGLE TRADE AT A TIME
    # -------------------------------------------------------------
    balance = STARTING_BALANCE
    peak_balance = STARTING_BALANCE
    cur_day = None
    day_start_balance = STARTING_BALANCE
    
    executed_trades = []
    skipped_trades = []
    
    current_open_trade = None
    daily_dd_breached = False
    overall_dd_breached = False
    account_failed = False
    failure_time = None
    failure_reason = ""
    
    # Helper: calculate lots & risk
    def calculate_lots_and_risk(pair, balance, entry_price, sl_dist, sl_pips):
        dollar_risk = balance * RISK_PCT
        spec = pair_specs[pair]
        
        if spec.get('gold'):
            lots = math.floor((dollar_risk / (sl_dist * 100.0)) * 100.0) / 100.0
            lots = max(0.01, lots)
            actual_risk = lots * 100.0 * sl_dist
        elif spec.get('usd_quote'):
            lots = math.floor((dollar_risk / (sl_pips * 10.0)) * 100.0) / 100.0
            lots = max(0.01, lots)
            actual_risk = lots * sl_pips * 10.0
        elif spec.get('jpy'):
            pip_val = 1000.0 / entry_price
            lots = math.floor((dollar_risk / (sl_pips * pip_val)) * 100.0) / 100.0
            lots = max(0.01, lots)
            actual_risk = lots * sl_pips * pip_val
        else:
            pip_val = 10.0 / entry_price
            lots = math.floor((dollar_risk / (sl_pips * pip_val)) * 100.0) / 100.0
            lots = max(0.01, lots)
            actual_risk = lots * sl_pips * pip_val
            
        return lots, actual_risk

    def calculate_trade_pnl(pair, trade, lots, entry_price, exit_price):
        spec = pair_specs[pair]
        dir_mult = 1.0 if trade['direction'] == 'LONG' else -1.0
        price_diff = (exit_price - entry_price) * dir_mult
        
        if spec.get('gold'):
            gross_pnl = lots * 100.0 * price_diff
            costs = lots * 100.0 * spec['cost_oz']
        elif spec.get('usd_quote'):
            pips = price_diff / spec['pip_unit']
            gross_pnl = lots * pips * 10.0
            costs = lots * spec['cost_pips'] * 10.0
        elif spec.get('jpy'):
            pips = price_diff / spec['pip_unit']
            pip_val = 1000.0 / exit_price
            gross_pnl = lots * pips * pip_val
            costs = lots * spec['cost_pips'] * pip_val
        else:
            pips = price_diff / spec['pip_unit']
            pip_val = 10.0 / exit_price
            gross_pnl = lots * pips * pip_val
            costs = lots * spec['cost_pips'] * pip_val
            
        net_pnl = gross_pnl - costs
        return gross_pnl, costs, net_pnl

    for tr in raw_signal_list:
        sig_time = tr['entry_time']
        
        # Check if previous trade has already exited before or at this signal time
        if current_open_trade is not None:
            if sig_time < current_open_trade['exit_time']:
                # ACCOUNT IS CURRENTLY IN A TRADE -> SKIP THIS SIGNAL
                skipped_trades.append({
                    'pair': tr['pair'],
                    'entry_time': tr['entry_time'],
                    'reason': f"Blocked by active {current_open_trade['pair']} trade until {current_open_trade['exit_time']}"
                })
                continue
            else:
                # Active trade has finished, free the slot!
                current_open_trade = None
                
        # Now flat -> Enter this trade
        pair = tr['pair']
        entry_price = tr['entry_price']
        exit_price = tr['exit_price']
        exit_time = tr['exit_time']
        bar_date = exit_time.date()
        
        # Daily reset on exit date
        if bar_date != cur_day:
            cur_day = bar_date
            day_start_balance = balance
            
        lots, actual_risk = calculate_lots_and_risk(pair, balance, entry_price, tr['sl_dist'], tr['sl_pips'])
        gross_pnl, costs, net_pnl = calculate_trade_pnl(pair, tr, lots, entry_price, exit_price)
        r_mult = net_pnl / actual_risk if actual_risk > 0 else 0
        
        balance_before = balance
        balance += net_pnl
        peak_balance = max(peak_balance, balance)
        
        daily_loss = day_start_balance - balance
        daily_dd_pct = (daily_loss / day_start_balance * 100.0) if day_start_balance > 0 else 0.0
        overall_loss = STARTING_BALANCE - balance
        overall_dd_pct = (overall_loss / STARTING_BALANCE * 100.0)
        
        # Check prop limits
        if not account_failed:
            if daily_loss >= (day_start_balance * MAX_DAILY_DD_PCT):
                daily_dd_breached = True
                account_failed = True
                failure_time = exit_time
                failure_reason = f"DAILY DD LIMIT BREACHED: Lost ${daily_loss:.2f} ({daily_dd_pct:.2f}% > 3.0%) on {exit_time}"
            elif balance <= (STARTING_BALANCE * (1.0 - MAX_OVERALL_DD_PCT)):
                overall_dd_breached = True
                account_failed = True
                failure_time = exit_time
                failure_reason = f"OVERALL DD LIMIT BREACHED: Balance fell to ${balance:.2f} (DD {overall_dd_pct:.2f}% > 8.0%) on {exit_time}"
                
        rec = {
            'trade_idx': len(executed_trades) + 1,
            'pair': pair,
            'direction': tr['direction'],
            'entry_time': tr['entry_time'],
            'entry_price': entry_price,
            'sl_price': tr['sl_price'],
            'tp_price': tr['tp_price'],
            'lots': lots,
            'risk_dollars': actual_risk,
            'exit_time': exit_time,
            'exit_price': exit_price,
            'result': tr['result'],
            'gross_pnl': gross_pnl,
            'costs': costs,
            'net_pnl': net_pnl,
            'balance': balance,
            'daily_dd_pct': max(0.0, daily_dd_pct),
            'overall_dd_pct': max(0.0, overall_dd_pct),
            'r_mult': r_mult,
            'hold_bars': tr['hold_bars'],
            'account_failed': account_failed
        }
        executed_trades.append(rec)
        current_open_trade = rec

    df_exec = pd.DataFrame(executed_trades)
    
    # -------------------------------------------------------------
    # WEEK-BY-WEEK ANALYSIS
    # -------------------------------------------------------------
    df_exec['exit_dt'] = pd.to_datetime(df_exec['exit_time'])
    df_exec['week'] = df_exec['exit_dt'].dt.to_period('W-SUN')
    
    weeks = sorted(list(df_exec['week'].unique()))
    weekly_records = []
    run_bal = STARTING_BALANCE
    
    for w in weeks:
        w_trades = df_exec[df_exec['week'] == w]
        w_start = run_bal
        w_pnl = w_trades['net_pnl'].sum()
        run_bal += w_pnl
        w_end = run_bal
        w_ret = (w_pnl / w_start * 100.0) if w_start > 0 else 0
        w_wins = len(w_trades[w_trades['result'] == 'WIN'])
        w_losses = len(w_trades[w_trades['result'] == 'LOSS'])
        w_net_r = w_trades['r_mult'].sum()
        w_max_d_dd = w_trades['daily_dd_pct'].max() if len(w_trades) > 0 else 0
        
        status = "FAIL" if any(w_trades['account_failed']) else ("PASS" if w_pnl >= 0 else "LOSS")
        
        weekly_records.append({
            'Week': str(w),
            'Starting Balance': f"${w_start:,.2f}",
            'Trades': len(w_trades),
            'Wins': w_wins,
            'Losses': w_losses,
            'Net R': f"{w_net_r:+.2f} R",
            'Net P&L': f"${w_pnl:+,.2f}",
            'Ending Balance': f"${w_end:,.2f}",
            'Weekly Return': f"{w_ret:+.2f}%",
            'Max Daily DD': f"{w_max_d_dd:.2f}%",
            'Status': status
        })
    df_weekly = pd.DataFrame(weekly_records)
    
    # -------------------------------------------------------------
    # MONTH-BY-MONTH ANALYSIS
    # -------------------------------------------------------------
    df_exec['month'] = df_exec['exit_dt'].dt.to_period('M')
    months = sorted(list(df_exec['month'].unique()))
    monthly_records = []
    run_m_bal = STARTING_BALANCE
    for m in months:
        m_trades = df_exec[df_exec['month'] == m]
        m_start = run_m_bal
        m_pnl = m_trades['net_pnl'].sum()
        run_m_bal += m_pnl
        m_end = run_m_bal
        m_ret = (m_pnl / m_start * 100.0) if m_start > 0 else 0
        m_wins = len(m_trades[m_trades['result'] == 'WIN'])
        m_tr = len(m_trades)
        m_wr = (m_wins / m_tr * 100.0) if m_tr > 0 else 0
        m_max_dd = m_trades['overall_dd_pct'].max() if len(m_trades) > 0 else 0
        
        monthly_records.append({
            'Month': str(m),
            'Starting Balance': f"${m_start:,.2f}",
            'Net P&L': f"${m_pnl:+,.2f}",
            'Return': f"{m_ret:+.2f}%",
            'Trades': m_tr,
            'Win Rate': f"{m_wr:.1f}%",
            'Max Overall DD': f"{m_max_dd:.2f}%",
            'Ending Balance': f"${m_end:,.2f}"
        })
    df_monthly = pd.DataFrame(monthly_records)
    
    # -------------------------------------------------------------
    # PER-PAIR BREAKDOWN
    # -------------------------------------------------------------
    pair_records = []
    tot_pnl = df_exec['net_pnl'].sum()
    for p in whitelisted_pairs:
        p_tr = df_exec[df_exec['pair'] == p]
        n_p = len(p_tr)
        w_p = len(p_tr[p_tr['result'] == 'WIN'])
        l_p = len(p_tr[p_tr['result'] == 'LOSS'])
        wr_p = (w_p / n_p * 100.0) if n_p > 0 else 0
        pnl_p = p_tr['net_pnl'].sum()
        r_p = p_tr['r_mult'].sum()
        win_sum = p_tr[p_tr['net_pnl'] > 0]['net_pnl'].sum()
        loss_sum = abs(p_tr[p_tr['net_pnl'] < 0]['net_pnl'].sum())
        pf_p = (win_sum / loss_sum) if loss_sum > 0 else (99.0 if win_sum > 0 else 0.0)
        
        pair_records.append({
            'Pair': p,
            'Trades': n_p,
            'Wins': w_p,
            'Losses': l_p,
            'Win Rate': f"{wr_p:.1f}%",
            'Net P&L': f"${pnl_p:+,.2f}",
            'Net R': f"{r_p:+.2f} R",
            'Profit Factor': f"{pf_p:.2f}"
        })
    df_pair_summary = pd.DataFrame(pair_records)
    
    # Metrics
    n_total = len(df_exec)
    n_wins = len(df_exec[df_exec['result'] == 'WIN'])
    n_losses = len(df_exec[df_exec['result'] == 'LOSS'])
    win_rate = (n_wins / n_total * 100.0) if n_total > 0 else 0
    total_net_pnl = balance - STARTING_BALANCE
    total_return_pct = (total_net_pnl / STARTING_BALANCE) * 100.0
    total_net_r = df_exec['r_mult'].sum()
    gross_wins = df_exec[df_exec['net_pnl'] > 0]['net_pnl'].sum()
    gross_losses = abs(df_exec[df_exec['net_pnl'] < 0]['net_pnl'].sum())
    profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else 99.0
    
    max_d_dd = df_exec['daily_dd_pct'].max()
    max_ov_dd = df_exec['overall_dd_pct'].max()
    
    return {
        'df_exec': df_exec,
        'df_weekly': df_weekly,
        'df_monthly': df_monthly,
        'df_pair_summary': df_pair_summary,
        'skipped_count': len(skipped_trades),
        'ending_balance': balance,
        'net_profit': total_net_pnl,
        'return_pct': total_return_pct,
        'total_trades': n_total,
        'wins': n_wins,
        'losses': n_losses,
        'win_rate': win_rate,
        'net_r': total_net_r,
        'profit_factor': profit_factor,
        'max_daily_dd_pct': max_d_dd,
        'max_overall_dd_pct': max_ov_dd,
        'account_failed': account_failed,
        'failure_time': failure_time,
        'failure_reason': failure_reason
    }

if __name__ == '__main__':
    res = run_single_trade_whitelisted_audit()
    print("="*80)
    print("STRICT SINGLE TRADE WHITELISTED AUDIT RESULTS")
    print("="*80)
    print(f"Starting Balance: $5,000.00")
    print(f"Ending Balance:   ${res['ending_balance']:,.2f}")
    print(f"Net Profit:       ${res['net_profit']:+,.2f}")
    print(f"Return:           {res['return_pct']:+.2f}%")
    print(f"Total Trades:     {res['total_trades']} (Skipped overlapping signals: {res['skipped_count']})")
    print(f"Win Rate:         {res['win_rate']:.1f}% ({res['wins']}W / {res['losses']}L)")
    print(f"Profit Factor:    {res['profit_factor']:.2f}")
    print(f"Net R:            {res['net_r']:+.2f} R")
    print(f"Max Daily DD:     {res['max_daily_dd_pct']:.2f}% (Limit: 3.00%)")
    print(f"Max Overall DD:   {res['max_overall_dd_pct']:.2f}% (Limit: 8.00%)")
    print(f"Account Failed:   {res['account_failed']}")
    if res['account_failed']:
        print(f"Failure Reason:   {res['failure_reason']}")
    print("\n--- PER-PAIR SUMMARY ---")
    print(res['df_pair_summary'].to_string(index=False))
    print("\n--- MONTHLY PERFORMANCE ---")
    print(res['df_monthly'].to_string(index=False))
    print("\n--- WEEKLY PERFORMANCE ---")
    print(res['df_weekly'].to_string(index=False))
