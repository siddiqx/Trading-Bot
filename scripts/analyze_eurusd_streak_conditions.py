import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

with open('archives/data_cache_orb.pkl', 'rb') as f:
    data = pickle.load(f)
eur_h1 = data[1]['EURUSD']['H1'].copy()
eur_m15 = data[1]['EURUSD']['M15'].copy()

eur_h1['time_dt'] = pd.to_datetime(eur_h1['time'], unit='s')
eur_m15['time_dt'] = pd.to_datetime(eur_m15['time'], unit='s')

period_h1 = eur_h1[(eur_h1['time_dt'] >= '2022-11-20') & (eur_h1['time_dt'] <= '2023-01-30')]
print("EURUSD Nov 2022 - Jan 2023 Summary:")
print(f"H1 Start Price: {period_h1.iloc[0]['close']}, Max: {period_h1['high'].max()}, Min: {period_h1['low'].min()}, End: {period_h1.iloc[-1]['close']}")

# Check what signals were fired
from scripts.test_pattern_improvements import run_simulation
trades = run_simulation(use_session_filter=True, min_atr_ratio=1.0, require_m15_ema=True, max_hunt_bars=4, use_circuit_breaker=False)
eur = trades[trades['pair'] == 'EURUSD'].sort_values('time')
period_trades = eur[(eur['time'] >= '2022-11-20') & (eur['time'] <= '2023-01-30')]

# Check if they were LONG or SHORT
print("\nTrades during streak:")
print(period_trades[['time', 'res', 'pips', 'R']])
