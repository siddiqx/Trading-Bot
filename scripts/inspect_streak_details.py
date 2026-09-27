import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

with open('archives/trade_patterns_analysis.pkl', 'rb') as f:
    df = pickle.load(f)

eur = df[df['pair'] == 'EURUSD'].sort_values('time')
streak = eur[(eur['time'] >= '2022-11-25') & (eur['time'] <= '2023-01-25')]
print("Trade details during EURUSD streak:")
print(streak[['time', 'type', 'res', 'R', 'pips', 'hour', 'rsi', 'dist_h1_e200_atr', 'sl_pips', 'hold_bars']].to_string())
