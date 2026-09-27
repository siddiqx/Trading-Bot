import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

def analyze_losing_trades_consolidation():
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        data = pickle.load(f)
    pairs_data = data[1]
    
    pair = 'USDJPY'
    m15 = pairs_data[pair]['M15'].copy()
    h1 = pairs_data[pair]['H1'].copy()
    
    m15['time_dt'] = pd.to_datetime(m15['time'], unit='s')
    h1['time_dt'] = pd.to_datetime(h1['time'], unit='s')
    
    # 1H Donchian High and Low (20 bars on 1H = 20 hours)
    h1['h1_don_h'] = h1['high'].shift(1).rolling(20).max()
    h1['h1_don_l'] = h1['low'].shift(1).rolling(20).min()
    h1['h1_don_width'] = h1['h1_don_h'] - h1['h1_don_l']
    
    # 1H ATR
    tr_h1 = np.maximum(h1['high'] - h1['low'], np.maximum(np.abs(h1['high'] - h1['close'].shift(1)), np.abs(h1['low'] - h1['close'].shift(1))))
    h1['h1_atr'] = pd.Series(tr_h1).rolling(14).mean().bfill()
    h1['width_atr_ratio'] = h1['h1_don_width'] / (h1['h1_atr'] + 1e-9)
    
    # 4H data (resampled from 1H)
    h1_indexed = h1.set_index('time_dt')
    h4 = h1_indexed.resample('4h').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).dropna().reset_index()
    h4['e20'] = h4['close'].ewm(span=20, adjust=False).mean()
    h4['e50'] = h4['close'].ewm(span=50, adjust=False).mean()
    h4['don_h'] = h4['high'].shift(1).rolling(10).max()
    h4['don_l'] = h4['low'].shift(1).rolling(10).min()
    
    # Map 1H and 4H to 15m
    m15['h1_time'] = m15['time_dt'].dt.floor('h') - pd.Timedelta(hours=1)
    m15['h4_time'] = m15['time_dt'].dt.floor('4h') - pd.Timedelta(hours=4)
    
    m15['h1_don_h'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['h1_don_h'])))
    m15['h1_don_l'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['h1_don_l'])))
    m15['h1_don_width'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['h1_don_width'])))
    m15['h1_atr'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['h1_atr'])))
    m15['width_atr_ratio'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['width_atr_ratio'])))
    
    # Let's inspect the September losing trades on USDJPY
    # Losses were:
    # Sep 2 05:45 (BUY @160.28)
    # Sep 3 19:30 (SELL @155.33)
    # Sep 8 04:45 (SELL @153.35)
    # Sep 9 09:45 (SELL @152.95)
    # Sep 11 02:00 (BUY @154.55)
    # Sep 14 17:15 (SELL @154.30)
    
    sample_times = [
        '2026-09-02 05:45:00',
        '2026-09-03 19:30:00',
        '2026-09-08 04:45:00',
        '2026-09-09 09:45:00',
        '2026-09-11 02:00:00',
        '2026-09-14 17:15:00'
    ]
    
    print("=== ANALYSIS OF LOSING TRADES IN SEPTEMBER (USDJPY) ===")
    for st in sample_times:
        row = m15[m15['time_dt'] == st]
        if len(row) > 0:
            r = row.iloc[0]
            c = r['close']
            h1_h = r['h1_don_h']
            h1_l = r['h1_don_l']
            w = r['h1_don_width']
            atr = r['h1_atr']
            ratio = r['width_atr_ratio']
            
            # Position of close relative to 1H range:
            # 0% = at 1H low, 100% = at 1H high
            pos_pct = (c - h1_l) / (h1_h - h1_l + 1e-9) * 100
            
            print(f"Time: {st} | Close: {c:.2f} | 1H Range: [{h1_l:.2f} - {h1_h:.2f}] (Width: {w:.2f}, {ratio:.1f}x ATR) | Pos in 1H Range: {pos_pct:.1f}%")

if __name__ == '__main__':
    analyze_losing_trades_consolidation()
