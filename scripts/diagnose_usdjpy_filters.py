import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

def diagnose_usdjpy_filters():
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        data = pickle.load(f)
    pairs_data = data[1]
    
    pair = 'USDJPY'
    m15 = pairs_data[pair]['M15'].copy()
    h1 = pairs_data[pair]['H1'].copy()
    d1 = pairs_data[pair]['D1'].copy()
    
    m15['time_dt'] = pd.to_datetime(m15['time'], unit='s')
    h1['time_dt'] = pd.to_datetime(h1['time'], unit='s')
    d1['time_dt'] = pd.to_datetime(d1['time'], unit='s')
    
    # Restrict to September 1 to Sept 15 (available in cache)
    sep_m15 = m15[(m15['time_dt'] >= '2026-09-01') & (m15['time_dt'] <= '2026-09-15')].copy()
    print(f"Total 15m bars in Sept 1 - 15: {len(sep_m15)}")
    
    # 1. 20-bar Donchian breakouts on 15m
    don_h = m15['high'].shift(1).rolling(20).max()
    don_l = m15['low'].shift(1).rolling(20).min()
    
    cross_long = (m15['close'] > don_h) & (m15['close'].shift(1) <= don_h.shift(1))
    cross_short = (m15['close'] < don_l) & (m15['close'].shift(1) >= don_l.shift(1))
    
    m15['cross_long'] = cross_long
    m15['cross_short'] = cross_short
    sep_m15['cross_long'] = cross_long
    sep_m15['cross_short'] = cross_short
    
    num_cross_long = sep_m15['cross_long'].sum()
    num_cross_short = sep_m15['cross_short'].sum()
    print(f"Raw 15m 20-bar Breakouts: Long={num_cross_long}, Short={num_cross_short}, Total={num_cross_long + num_cross_short}")
    
    # Let's inspect each breakout candle in Sept
    breakouts = sep_m15[sep_m15['cross_long'] | sep_m15['cross_short']].copy()
    
    # Compute the filters
    # H1 E200, E20, E50
    h1['e200'] = h1['close'].ewm(span=200, adjust=False).mean()
    h1['e50'] = h1['close'].ewm(span=50, adjust=False).mean()
    h1['e20'] = h1['close'].ewm(span=20, adjust=False).mean()
    h1['h1_macro_bull'] = (h1['close'] > h1['e200']) & (h1['e20'] > h1['e50'])
    h1['h1_macro_bear'] = (h1['close'] < h1['e200']) & (h1['e20'] < h1['e50'])
    
    # D1 E50
    d1['e50'] = d1['close'].ewm(span=50, adjust=False).mean()
    d1['d1_bull'] = d1['close'] > d1['e50']
    d1['d1_bear'] = d1['close'] < d1['e50']
    
    # Map H1 & D1 to M15 with shift(1) equivalent
    m15['h1_time'] = m15['time_dt'].dt.floor('h') - pd.Timedelta(hours=1)
    m15['d1_time'] = m15['time_dt'].dt.floor('d') - pd.Timedelta(days=1)
    
    m15['h1_macro_bull'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['h1_macro_bull']))).fillna(False)
    m15['h1_macro_bear'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['h1_macro_bear']))).fillna(False)
    m15['d1_bull'] = m15['d1_time'].map(dict(zip(d1['time_dt'], d1['d1_bull']))).fillna(False)
    m15['d1_bear'] = m15['d1_time'].map(dict(zip(d1['time_dt'], d1['d1_bear']))).fillna(False)
    
    # Session filter: 0700-1530 UTC
    m15['hour_min'] = m15['time_dt'].dt.hour * 100 + m15['time_dt'].dt.minute
    m15['in_session'] = (m15['hour_min'] >= 700) & (m15['hour_min'] <= 1530)
    
    breakouts = m15[(m15['time_dt'] >= '2026-09-01') & (m15['time_dt'] <= '2026-09-15') & (m15['cross_long'] | m15['cross_short'])].copy()
    
    print("\n--- Breakdown of all 15m Breakouts in Sept 1-15 ---")
    for idx, row in breakouts.iterrows():
        t = row['time_dt']
        direction = 'LONG' if row['cross_long'] else 'SHORT'
        c = row['close']
        sess = row['in_session']
        h1_ok = row['h1_macro_bull'] if direction == 'LONG' else row['h1_macro_bear']
        d1_ok = row['d1_bull'] if direction == 'LONG' else row['d1_bear']
        
        print(f"Bar: {t} | {direction:<5} | Close: {c:.2f} | InSession(07-15:30): {sess:<5} | H1_Macro(E200+E20/50): {h1_ok:<5} | D1(E50): {d1_ok:<5}")

if __name__ == '__main__':
    diagnose_usdjpy_filters()
