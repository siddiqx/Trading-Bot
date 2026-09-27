import pickle, pandas as pd, numpy as np
import sys, os
sys.path.insert(0, os.path.abspath('.'))
from scripts.deep_strategy_enhancement_audit import simulate_exact_gold

with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
    df = pickle.load(f)['XAUUSD']
if df['time_dt'].dt.tz is not None:
    df['time_dt'] = df['time_dt'].dt.tz_localize(None)

trades = simulate_exact_gold(df, fri_cutoff_hour=15, rr=1.75)
tdf = pd.DataFrame(trades)
n = len(tdf)
wr = (tdf['result'] == 'WIN').mean() * 100.0
win_r = tdf[tdf['result'] == 'WIN']['r'].sum()
loss_r = abs(tdf[tdf['result'] == 'LOSS']['r'].sum())
pf = win_r / loss_r
print(f"Total Trades: {n}, Win Rate: {wr:.1f}%, Profit Factor: {pf:.2f}")

# Evaluate 1.25% P1 ($62.50) / 1.0% P2 ($50.00)
p1_days, p2_days, tot_days = [], [], []
for start_i in range(0, n - 15):
    # P1 @ 1.25% ($62.50)
    p1_cum = 0.0
    p1_i = start_i
    p1_pass = False
    p1_peak = 0.0
    while p1_i < n:
        pnl = tdf.iloc[p1_i]['r'] * 62.50
        p1_cum += pnl
        p1_peak = max(p1_peak, p1_cum)
        if (p1_peak - p1_cum) >= 400.0:
            break
        if p1_cum >= 400.0:
            p1_pass = True
            break
        p1_i += 1
    if not p1_pass:
        continue
    p1_d = (tdf.iloc[p1_i]['exit_dt'] - tdf.iloc[start_i]['entry_dt']).days
    
    # P2 @ 1.0% ($50.00)
    p2_cum = 0.0
    p2_i = p1_i + 1
    p2_pass = False
    p2_peak = 0.0
    while p2_i < n:
        pnl = tdf.iloc[p2_i]['r'] * 50.00
        p2_cum += pnl
        p2_peak = max(p2_peak, p2_cum)
        if (p2_peak - p2_cum) >= 400.0:
            break
        if p2_cum >= 250.0:
            p2_pass = True
            break
        p2_i += 1
    if not p2_pass:
        continue
    p2_d = (tdf.iloc[p2_i]['exit_dt'] - tdf.iloc[p1_i + 1]['entry_dt']).days
    tot_d = p1_d + 1 + p2_d + 1 + 14
    p1_days.append(p1_d)
    p2_days.append(p2_d)
    tot_days.append(tot_d)

print(f"Phase 1 Days (Median): {np.median(p1_days):.0f} days (~{np.median(p1_days)/7:.1f} weeks)")
print(f"Phase 2 Days (Median): {np.median(p2_days):.0f} days (~{np.median(p2_days)/7:.1f} weeks)")
print(f"Total Payout Days (Median): {np.median(tot_days):.0f} days (~{np.median(tot_days)/30:.1f} months)")
print(f"Pass Rate: {len(tot_days) / (n - 15) * 100:.1f}%")

print("\n--- 2-YEAR HISTORICAL VALIDATION ---")
trades_2y = simulate_exact_gold(df, fri_cutoff_hour=15, rr=1.75, start_date=None)
tdf_2y = pd.DataFrame(trades_2y)
n_2y = len(tdf_2y)
wr_2y = (tdf_2y['result'] == 'WIN').mean() * 100.0
win_r2 = tdf_2y[tdf_2y['result'] == 'WIN']['r'].sum()
loss_r2 = abs(tdf_2y[tdf_2y['result'] == 'LOSS']['r'].sum())
pf_2y = win_r2 / loss_r2
print(f"2Y Total Trades: {n_2y}, Win Rate: {wr_2y:.1f}%, Profit Factor: {pf_2y:.2f}")

p1_2y, p2_2y, tot_2y = [], [], []
for start_i in range(0, n_2y - 15):
    p1_cum = 0.0
    p1_i = start_i
    p1_pass = False
    p1_peak = 0.0
    while p1_i < n_2y:
        pnl = tdf_2y.iloc[p1_i]['r'] * 62.50
        p1_cum += pnl
        p1_peak = max(p1_peak, p1_cum)
        if (p1_peak - p1_cum) >= 400.0: break
        if p1_cum >= 400.0: p1_pass = True; break
        p1_i += 1
    if not p1_pass: continue
    p1_d = (tdf_2y.iloc[p1_i]['exit_dt'] - tdf_2y.iloc[start_i]['entry_dt']).days
    
    p2_cum = 0.0
    p2_i = p1_i + 1
    p2_pass = False
    p2_peak = 0.0
    while p2_i < n_2y:
        pnl = tdf_2y.iloc[p2_i]['r'] * 50.00
        p2_cum += pnl
        p2_peak = max(p2_peak, p2_cum)
        if (p2_peak - p2_cum) >= 400.0: break
        if p2_cum >= 250.0: p2_pass = True; break
        p2_i += 1
    if not p2_pass: continue
    p2_d = (tdf_2y.iloc[p2_i]['exit_dt'] - tdf_2y.iloc[p1_i + 1]['entry_dt']).days
    tot_d = p1_d + 1 + p2_d + 1 + 14
    p1_2y.append(p1_d)
    p2_2y.append(p2_d)
    tot_2y.append(tot_d)

print(f"2Y Phase 1 Days (Median): {np.median(p1_2y):.0f} days (~{np.median(p1_2y)/7:.1f} weeks)")
print(f"2Y Phase 2 Days (Median): {np.median(p2_2y):.0f} days (~{np.median(p2_2y)/7:.1f} weeks)")
print(f"2Y Total Payout Days (Median): {np.median(tot_2y):.0f} days (~{np.median(tot_2y)/30:.1f} months)")
print(f"2Y Pass Rate: {len(tot_2y) / (n_2y - 15) * 100:.1f}%")
