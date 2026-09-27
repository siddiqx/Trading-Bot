import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

with open('archives/data_cache_orb.pkl', 'rb') as f:
    data = pickle.load(f)

pair = 'USDJPY'
m15 = data[1][pair]['M15'].copy()
h1 = data[1][pair]['H1'].copy()
d1 = data[1][pair]['D1'].copy()

# Filter for September 2026
m15['time_dt'] = pd.to_datetime(m15['time'], unit='s')
h1['time_dt'] = pd.to_datetime(h1['time'], unit='s')
d1['time_dt'] = pd.to_datetime(d1['time'], unit='s').dt.floor('D')

# Indicators
d1['ema50'] = d1['close'].ewm(span=50, adjust=False).mean()
d1_bull_map = dict(zip(d1['time_dt'], d1['close'] > d1['ema50']))

h1['ema200'] = h1['close'].ewm(span=200, adjust=False).mean()
h1['ema50'] = h1['close'].ewm(span=50, adjust=False).mean()
h1['ema20'] = h1['close'].ewm(span=20, adjust=False).mean()
h1['ema20_slope'] = h1['ema20'] - h1['ema20'].shift(2)
h1['date_only'] = h1['time_dt'].dt.floor('D')
h1['d1_bull'] = h1['date_only'].map(d1_bull_map).fillna(False)

h1['h1_macro_bull'] = (h1['close'] > h1['ema200']) & (h1['ema20'] > h1['ema50']) & (h1['d1_bull']) & (h1['ema20_slope'] > 0)
h1['h1_macro_bear'] = (h1['close'] < h1['ema200']) & (h1['ema20'] < h1['ema50']) & (~h1['d1_bull']) & (h1['ema20_slope'] < 0)

m15['h1_time'] = m15['time_dt'].dt.floor('h') - pd.Timedelta(hours=1)
h1_bull_map = dict(zip(h1['time_dt'], h1['h1_macro_bull']))
h1_bear_map = dict(zip(h1['time_dt'], h1['h1_macro_bear']))
m15['h1_macro_bull'] = m15['h1_time'].map(h1_bull_map).fillna(False).values
m15['h1_macro_bear'] = m15['h1_time'].map(h1_bear_map).fillna(False).values

# Also check basic H1 bull/bear without strict D1 / slope
h1['h1_basic_bull'] = (h1['close'] > h1['ema200']) & (h1['ema20'] > h1['ema50'])
h1['h1_basic_bear'] = (h1['close'] < h1['ema200']) & (h1['ema20'] < h1['ema50'])
m15['h1_basic_bull'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['h1_basic_bull']))).fillna(False).values
m15['h1_basic_bear'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['h1_basic_bear']))).fillna(False).values

m15['e20'] = m15['close'].ewm(span=20, adjust=False).mean()
m15['e50'] = m15['close'].ewm(span=50, adjust=False).mean()
m15['local_bull'] = m15['e20'] > m15['e50']
m15['local_bear'] = m15['e20'] < m15['e50']

tr = np.maximum(m15['high'] - m15['low'], np.maximum(abs(m15['high'] - m15['close'].shift(1)), abs(m15['low'] - m15['close'].shift(1))))
m15['atr'] = tr.rolling(14).mean().bfill()
m15['atr_sma'] = m15['atr'].rolling(20).mean().bfill()
m15['vol_expansion'] = m15['atr'] >= m15['atr_sma']

m15['don_h'] = m15['high'].shift(1).rolling(28).max().bfill()
m15['don_l'] = m15['low'].shift(1).rolling(28).min().bfill()
m15['break_high'] = (m15['close'] > m15['don_h']) & (m15['close'].shift(1) <= m15['don_h'].shift(1))
m15['break_low'] = (m15['close'] < m15['don_l']) & (m15['close'].shift(1) >= m15['don_l'].shift(1))

m15['hour'] = m15['time_dt'].dt.hour
m15['in_07_15'] = (m15['hour'] >= 7) & (m15['hour'] <= 15)

# Inspect September 1 to September 15
sep = m15[(m15['time_dt'] >= '2026-09-01') & (m15['time_dt'] <= '2026-09-15')].copy()

print(f"Total 15m bars in Sept 1-15 for USDJPY: {len(sep)}")
print(f"Total Breakout Highs: {sep['break_high'].sum()}")
print(f"Total Breakout Lows:  {sep['break_low'].sum()}")

breakouts = sep[sep['break_high'] | sep['break_low']]
print(f"\nAll Breakouts in Sept 1-15 ({len(breakouts)} total):")
for idx, row in breakouts.iterrows():
    b_type = "HIGH" if row['break_high'] else "LOW"
    print(f"{row['time_dt']} | Break: {b_type:4s} | InSession(07-15): {row['in_07_15']} | H1_Macro: {row['h1_macro_bull'] if b_type=='HIGH' else row['h1_macro_bear']} | H1_Basic: {row['h1_basic_bull'] if b_type=='HIGH' else row['h1_basic_bear']} | Local_EMA: {row['local_bull'] if b_type=='HIGH' else row['local_bear']} | Vol_Exp: {row['vol_expansion']}")
