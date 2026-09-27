import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np
from scripts.test_strategies_deep import load_data, run_numpy_backtest

data = load_data()
res = run_numpy_backtest(data, strat_type="trend_retrace", rr=1.5, sl_mult=0.5, min_sl_pips=18.0, use_cb=False)

dfs = []
for p, df in res.items():
    if len(df) > 0:
        dfs.append(df)
all_df = pd.concat(dfs, ignore_index=True)

print(f"Total trades analyzed: {len(all_df)}")
print(f"Wins: {(all_df['res'] == 'WIN').sum()}, Losses: {(all_df['res'] == 'LOSS').sum()}")

# Feature analysis: Wins vs Losses
features = ['rsi', 'atr_pips', 'sl_pips', 'bars_waited', 'ema20_dist', 'ema50_dist', 'ema200_dist', 'hour', 'day_of_week', 'hold']

print("\n" + "="*60)
print("MEAN VALUES: WINS vs LOSSES")
print("="*60)
summary = all_df.groupby('res')[features].mean()
print(summary.T)

print("\n" + "="*60)
print("WIN RATE BY HOUR OF DAY (UTC)")
print("="*60)
hourly = all_df.groupby('hour').agg(
    trades=('res', 'count'),
    wins=('res', lambda x: (x == 'WIN').sum()),
    net_r=('R', 'sum')
)
hourly['win_rate'] = (hourly['wins'] / hourly['trades'] * 100).round(1)
print(hourly.to_string())

print("\n" + "="*60)
print("WIN RATE BY DAY OF WEEK (0=Mon, 4=Fri)")
print("="*60)
daily = all_df.groupby('day_of_week').agg(
    trades=('res', 'count'),
    wins=('res', lambda x: (x == 'WIN').sum()),
    net_r=('R', 'sum')
)
daily['win_rate'] = (daily['wins'] / daily['trades'] * 100).round(1)
print(daily.to_string())

print("\n" + "="*60)
print("WIN RATE BY BARS WAITED FOR RETRACEMENT (PULLBACK DEPTH)")
print("="*60)
wait_df = all_df.groupby('bars_waited').agg(
    trades=('res', 'count'),
    wins=('res', lambda x: (x == 'WIN').sum()),
    net_r=('R', 'sum')
)
wait_df['win_rate'] = (wait_df['wins'] / wait_df['trades'] * 100).round(1)
print(wait_df.to_string())

print("\n" + "="*60)
print("WIN RATE BY SL DISTANCE BINS")
print("="*60)
all_df['sl_bin'] = pd.qcut(all_df['sl_pips'], q=4, duplicates='drop')
sl_grouped = all_df.groupby('sl_bin', observed=False).agg(
    trades=('res', 'count'),
    wins=('res', lambda x: (x == 'WIN').sum()),
    net_r=('R', 'sum')
)
sl_grouped['win_rate'] = (sl_grouped['wins'] / sl_grouped['trades'] * 100).round(1)
print(sl_grouped.to_string())

print("\n" + "="*60)
print("WIN RATE BY EMA 200 DISTANCE (TREND STRENGTH)")
print("="*60)
all_df['ema200_bin'] = pd.qcut(all_df['ema200_dist'], q=4, duplicates='drop')
ema_grouped = all_df.groupby('ema200_bin', observed=False).agg(
    trades=('res', 'count'),
    wins=('res', lambda x: (x == 'WIN').sum()),
    net_r=('R', 'sum')
)
ema_grouped['win_rate'] = (ema_grouped['wins'] / ema_grouped['trades'] * 100).round(1)
print(ema_grouped.to_string())

