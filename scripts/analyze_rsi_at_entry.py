import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

with open('archives/trade_patterns_analysis.pkl', 'rb') as f:
    df = pickle.load(f)

print("Win rate and Net R by RSI at entry for LONG trades:")
longs = df[df['type'] == 'LONG'].copy()
longs['rsi_bin'] = pd.cut(longs['rsi'], bins=[0, 40, 50, 60, 65, 70, 75, 100])
print(longs.groupby('rsi_bin').agg(
    trades=('res', 'count'),
    win_rate=('res', lambda x: (x == 'WIN').mean() * 100),
    net_R=('R', 'sum')
).to_string())

print("\nWin rate and Net R by RSI at entry for SHORT trades:")
shorts = df[df['type'] == 'SHORT'].copy()
shorts['rsi_bin'] = pd.cut(shorts['rsi'], bins=[0, 25, 30, 35, 40, 50, 60, 100])
print(shorts.groupby('rsi_bin').agg(
    trades=('res', 'count'),
    win_rate=('res', lambda x: (x == 'WIN').mean() * 100),
    net_R=('R', 'sum')
).to_string())
