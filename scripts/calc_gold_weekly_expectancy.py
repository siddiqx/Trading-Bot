import pickle
import pandas as pd
import numpy as np

with open('archives/portfolio_simulation_output.pkl', 'rb') as f:
    out = pickle.load(f)

signals = out['pair_signals']['XAUUSD']

STARTING_BALANCE = 5000.0
RISK_PCT = 0.01

bal = STARTING_BALANCE
trades = []

for tr in signals:
    sl_dist = tr['sl_dist']
    dollar_risk = bal * RISK_PCT
    lots = max(0.01, round(dollar_risk / (sl_dist * 100.0), 2))
    actual_risk = lots * 100.0 * sl_dist
    p_diff = (tr['exit_price'] - tr['entry_price']) * (1.0 if tr['direction']=='LONG' else -1.0)
    gross = lots * 100.0 * p_diff
    cost = lots * 100.0 * 0.36
    net = gross - cost
    r_mult = net / actual_risk if actual_risk > 0 else 0
    
    bal += net
    
    trades.append({
        'pair': 'XAUUSD',
        'direction': tr['direction'],
        'entry_time': tr['entry_time'],
        'exit_time': tr['exit_time'],
        'result': tr['result'],
        'lots': lots,
        'risk_dollars': actual_risk,
        'gross_pnl': gross,
        'costs': cost,
        'net_pnl': net,
        'balance': bal,
        'r_mult': r_mult
    })

df = pd.DataFrame(trades)
df['exit_dt'] = pd.to_datetime(df['exit_time'])
df['week'] = df['exit_dt'].dt.to_period('W-SUN')

# Full calendar weeks from start to end
min_date = df['exit_dt'].min()
max_date = df['exit_dt'].max()
all_weeks = pd.period_range(start=min_date.to_period('W-SUN'), end=max_date.to_period('W-SUN'), freq='W-SUN')

weekly_data = []
run_bal = STARTING_BALANCE

for w in all_weeks:
    w_tr = df[df['week'] == w]
    w_start = run_bal
    w_pnl = w_tr['net_pnl'].sum() if len(w_tr) > 0 else 0.0
    run_bal += w_pnl
    w_end = run_bal
    w_ret = (w_pnl / w_start * 100.0) if w_start > 0 else 0.0
    w_wins = len(w_tr[w_tr['result'] == 'WIN'])
    w_losses = len(w_tr[w_tr['result'] == 'LOSS'])
    w_net_r = w_tr['r_mult'].sum() if len(w_tr) > 0 else 0.0
    
    weekly_data.append({
        'week': str(w),
        'start_bal': w_start,
        'trades': len(w_tr),
        'wins': w_wins,
        'losses': w_losses,
        'net_r': w_net_r,
        'net_pnl': w_pnl,
        'ending_bal': w_end,
        'return_pct': w_ret
    })

df_w = pd.DataFrame(weekly_data)

total_weeks = len(df_w)
active_weeks = df_w[df_w['trades'] > 0]
winning_weeks = df_w[df_w['net_pnl'] > 0]
losing_weeks = df_w[df_w['net_pnl'] < 0]
flat_weeks = df_w[df_w['trades'] == 0]

avg_weekly_pnl_all = df_w['net_pnl'].mean()
avg_weekly_ret_all = df_w['return_pct'].mean()

avg_weekly_pnl_active = active_weeks['net_pnl'].mean()
avg_weekly_ret_active = active_weeks['return_pct'].mean()

avg_win_week = winning_weeks['net_pnl'].mean()
avg_loss_week = losing_weeks['net_pnl'].mean()

print(f"Total Calendar Weeks:             {total_weeks} weeks")
print(f"Active Trading Weeks:             {len(active_weeks)} weeks ({(len(active_weeks)/total_weeks*100):.1f}%)")
print(f"Inactive / Flat Weeks:            {len(flat_weeks)} weeks")
print(f"Profitable Weeks:                 {len(winning_weeks)} weeks ({(len(winning_weeks)/len(active_weeks)*100):.1f}% of active weeks)")
print(f"Losing Weeks:                     {len(losing_weeks)} weeks ({(len(losing_weeks)/len(active_weeks)*100):.1f}% of active weeks)")
print(f"Total Net Profit (6 Months):      ${bal - STARTING_BALANCE:,.2f} ({(bal-STARTING_BALANCE)/STARTING_BALANCE*100:+.2f}%)")
print(f"Total Net R:                      {df['r_mult'].sum():+.2f} R")
print(f"Average Return Per Calendar Week: ${avg_weekly_pnl_all:+.2f} / week ({avg_weekly_ret_all:+.2f}% / week)")
print(f"Average Return Per Active Week:   ${avg_weekly_pnl_active:+.2f} / week ({avg_weekly_ret_active:+.2f}% / week)")
print(f"Average Winning Week Gain:        +${avg_win_week:.2f} (+{(avg_win_week/5000*100):.2f}%)")
print(f"Average Losing Week Loss:         ${avg_loss_week:.2f} ({(avg_loss_week/5000*100):.2f}%)")
print(f"Best Week:                        +${df_w['net_pnl'].max():.2f} (+{df_w['return_pct'].max():.2f}%)")
print(f"Worst Week:                       ${df_w['net_pnl'].min():.2f} ({df_w['return_pct'].min():.2f}%)")
print(f"Average Trade Frequency:          {len(df)/total_weeks:.1f} trades / week")

print("\n" + "="*80)
print("WEEK-BY-WEEK PERFORMANCE TABLE (GOLD SOLO $5,000 ACCOUNT)")
print("="*80)
for _, r in df_w.iterrows():
    if r['trades'] > 0:
        res_tag = "WIN" if r['net_pnl'] > 0 else "LOSS"
        print(f"{r['week']} | Trades: {r['trades']} ({r['wins']}W / {r['losses']}L) | Net P&L: ${r['net_pnl']:+7.2f} ({r['return_pct']:+5.2f}%) | Ending Bal: ${r['ending_bal']:,.2f} | {res_tag}")
    else:
        print(f"{r['week']} | Trades: 0 (No Setups)    | Net P&L:   $0.00 (+0.00%) | Ending Bal: ${r['ending_bal']:,.2f} | FLAT")
