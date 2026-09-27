import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

def trace_pinescript_exact():
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
    
    # User's inputs from screenshot:
    # ICT-Fixed-MTF 1 10,000 1.75 0.5 18 60 3 160 4 2 48 60 20 28 200 50 0.35 20 1.1 14 68 32 0700-1530 test-secret-key-12345 LIVE
    # rr = 1.75
    # sl_mult = 0.5
    # min_sl = 18, max_sl = 60
    # cooldown = 4
    # max_hunting_bars = 4 (or 2?)
    # circuit breaker = 2 losses, 48 bars
    # htf_ema_len = 200, d1_ema_len = 50
    # min_body_ratio = 0.35, donchian_len = 20, m15_donchian_len = 28
    # vol_mult = 1.1, vol_ma_len = 14
    # rsi_max = 68, rsi_min = 32
    # session = '0700-1530'
    
    # HTF calculations (1H)
    h1['e200'] = h1['close'].ewm(span=200, adjust=False).mean()
    h1['e50']  = h1['close'].ewm(span=50, adjust=False).mean()
    h1['e20']  = h1['close'].ewm(span=20, adjust=False).mean()
    h1['e20_slope'] = h1['e20'] - h1['e20'].shift(2)
    h1['atr']  = (h1['high'] - h1['low']).rolling(14).mean()
    
    h1['macro_bull'] = (h1['close'] > h1['e200']) & (h1['e20'] > h1['e50']) & (h1['e20_slope'] > 0)
    h1['macro_bear'] = (h1['close'] < h1['e200']) & (h1['e20'] < h1['e50']) & (h1['e20_slope'] < 0)
    
    # D1 calculations
    d1['e50'] = d1['close'].ewm(span=50, adjust=False).mean()
    d1['bull'] = d1['close'] > d1['e50']
    d1['bear'] = d1['close'] < d1['e50']
    
    m15['h1_time'] = m15['time_dt'].dt.floor('h') - pd.Timedelta(hours=1)
    m15['d1_time'] = m15['time_dt'].dt.floor('D') - pd.Timedelta(days=1)
    
    m15['h1_macro_bull'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['macro_bull']))).fillna(False)
    m15['h1_macro_bear'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['macro_bear']))).fillna(False)
    m15['d1_bull'] = m15['d1_time'].map(dict(zip(d1['time_dt'], d1['bull']))).fillna(False)
    m15['d1_bear'] = m15['d1_time'].map(dict(zip(d1['time_dt'], d1['bear']))).fillna(False)
    
    # 15m indicators
    m15['e20'] = m15['close'].ewm(span=20, adjust=False).mean()
    m15['e50'] = m15['close'].ewm(span=50, adjust=False).mean()
    m15['atr'] = (m15['high'] - m15['low']).rolling(14).mean()
    m15['atr_sma'] = m15['atr'].rolling(20).mean()
    
    # RSI 14
    delta = m15['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    m15['rsi'] = (100 - (100 / (1 + rs))).bfill()
    
    # Donchian 28
    m15['don_h'] = m15['high'].shift(1).rolling(28).max()
    m15['don_l'] = m15['low'].shift(1).rolling(28).min()
    
    m15['cross_long'] = (m15['close'] > m15['don_h']) & (m15['close'].shift(1) <= m15['don_h'].shift(1))
    m15['cross_short'] = (m15['close'] < m15['don_l']) & (m15['close'].shift(1) >= m15['don_l'].shift(1))
    
    m15['rng'] = np.maximum(m15['high'] - m15['low'], 1e-6)
    m15['body_long'] = (m15['close'] - m15['low']) / m15['rng']
    m15['body_short'] = (m15['high'] - m15['close']) / m15['rng']
    
    m15['hour_min'] = m15['time_dt'].dt.hour * 100 + m15['time_dt'].dt.minute
    m15['in_session'] = (m15['hour_min'] >= 700) & (m15['hour_min'] <= 1530)
    
    # Filter USDJPY for September
    sep = m15[(m15['time_dt'] >= '2026-09-01') & (m15['time_dt'] <= '2026-09-15')].copy()
    
    print("Trace for USDJPY September 1 to 15:")
    for idx, row in sep.iterrows():
        t = row['time_dt']
        if row['cross_long'] or row['cross_short']:
            d = 'LONG' if row['cross_long'] else 'SHORT'
            h1_m = (row['h1_macro_bull'] and row['d1_bull']) if d == 'LONG' else (row['h1_macro_bear'] and row['d1_bear'])
            local_e = (row['e20'] > row['e50']) if d == 'LONG' else (row['e20'] < row['e50'])
            vol_exp = (row['atr'] >= row['atr_sma'])
            rsi_h = (row['rsi'] >= 40 and row['rsi'] <= 70) if d == 'LONG' else (row['rsi'] >= 30 and row['rsi'] <= 60)
            b_ratio = (row['body_long'] >= 0.35) if d == 'LONG' else (row['body_short'] >= 0.35)
            sess = row['in_session']
            
            passed = h1_m and local_e and vol_exp and rsi_h and b_ratio and sess
            print(f"{t} | {d:<5} | SETUP_PASS: {str(passed):<5} | Sess:{int(sess)} H1_Macro:{int(h1_m)} LocalEMA:{int(local_e)} ATR_Exp:{int(vol_exp)} RSI:{int(rsi_h)} Body:{int(b_ratio)}")

if __name__ == '__main__':
    trace_pinescript_exact()
