import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

def test_signal_frequency_solution():
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        data = pickle.load(f)
    pairs_data = data[1]
    
    # We want to test on USDJPY specifically first, and then the whole portfolio
    pair = 'USDJPY'
    m15 = pairs_data[pair]['M15'].copy()
    h1 = pairs_data[pair]['H1'].copy()
    d1 = pairs_data[pair]['D1'].copy()
    
    pip_unit = 0.01
    min_sl_dist = 18.0 * pip_unit
    max_sl_dist = 60.0 * pip_unit
    rr = 1.75
    sl_mult = 0.5
    
    m15['time_dt'] = pd.to_datetime(m15['time'], unit='s')
    h1['time_dt'] = pd.to_datetime(h1['time'], unit='s')
    
    # 1H Fast Trend: EMA 20 vs EMA 50 (instead of waiting 25 days for EMA 200)
    h1['e20'] = h1['close'].ewm(span=20, adjust=False).mean()
    h1['e50'] = h1['close'].ewm(span=50, adjust=False).mean()
    h1['e20_slope'] = h1['e20'] - h1['e20'].shift(2)
    
    h1['fast_bull'] = (h1['close'] > h1['e50']) & (h1['e20'] > h1['e50']) & (h1['e20_slope'] > 0)
    h1['fast_bear'] = (h1['close'] < h1['e50']) & (h1['e20'] < h1['e50']) & (h1['e20_slope'] < 0)
    
    m15['h1_time'] = m15['time_dt'].dt.floor('h') - pd.Timedelta(hours=1)
    m15['h1_bull'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['fast_bull']))).fillna(False).values
    m15['h1_bear'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['fast_bear']))).fillna(False).values
    
    close = m15['close'].values
    open_ = m15['open'].values
    high = m15['high'].values
    low = m15['low'].values
    hours = m15['time_dt'].dt.hour.values
    n = len(close)
    
    m15_e20 = m15['close'].ewm(span=20, adjust=False).mean().values
    m15_e50 = m15['close'].ewm(span=50, adjust=False).mean().values
    
    tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    atr14 = pd.Series(tr).rolling(14).mean().bfill().values
    
    # 20-bar Donchian breakout
    don_h = pd.Series(high).shift(1).rolling(20).max().bfill().values
    don_l = pd.Series(low).shift(1).rolling(20).min().bfill().values
    break_high = (close > don_h) & (np.roll(close, 1) <= np.roll(don_h, 1))
    break_low = (close < don_l) & (np.roll(close, 1) >= np.roll(don_l, 1))
    break_high[0] = False
    break_low[0] = False
    
    h1_bull = m15['h1_bull'].values
    h1_bear = m15['h1_bear'].values
    
    state = 0
    entry_price = 0.0
    sl_price = 0.0
    tp_price = 0.0
    entry_idx = 0
    hunting = 0
    hunt_idx = 0
    hunt_level = 0.0
    hunt_atr = 0.0
    trades = []
    
    for i in range(200, n):
        c = close[i]
        h = high[i]
        l = low[i]
        o = open_[i]
        a = atr14[i]
        hr = hours[i]
        
        if state != 0:
            if state == 1:
                if h >= tp_price:
                    trades.append({'time': m15['time_dt'].iloc[entry_idx], 'res': 'WIN', 'R': rr, 'pips': (tp_price - entry_price)/pip_unit})
                    state = 0
                elif l <= sl_price:
                    trades.append({'time': m15['time_dt'].iloc[entry_idx], 'res': 'LOSS', 'R': -1.0, 'pips': (sl_price - entry_price)/pip_unit})
                    state = 0
                elif (i - entry_idx) >= 160:
                    pips = (c - entry_price) / pip_unit
                    res = 'WIN' if pips > 0 else 'LOSS'
                    trades.append({'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'R': pips / ((entry_price - sl_price)/pip_unit), 'pips': pips})
                    state = 0
            elif state == -1:
                if l <= tp_price:
                    trades.append({'time': m15['time_dt'].iloc[entry_idx], 'res': 'WIN', 'R': rr, 'pips': (entry_price - tp_price)/pip_unit})
                    state = 0
                elif h >= sl_price:
                    trades.append({'time': m15['time_dt'].iloc[entry_idx], 'res': 'LOSS', 'R': -1.0, 'pips': (entry_price - sl_price)/pip_unit})
                    state = 0
                elif (i - entry_idx) >= 160:
                    pips = (entry_price - c) / pip_unit
                    res = 'WIN' if pips > 0 else 'LOSS'
                    trades.append({'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'R': pips / ((sl_price - entry_price)/pip_unit), 'pips': pips})
                    state = 0
            continue
            
        # Avoid rollover spread spike hour 21 UTC only
        in_active_hours = (hr != 21)
        
        if hunting == 0:
            long_setup = break_high[i] and h1_bull[i] and (m15_e20[i] > m15_e50[i]) and in_active_hours
            short_setup = break_low[i] and h1_bear[i] and (m15_e20[i] < m15_e50[i]) and in_active_hours
            
            if long_setup:
                hunting = 1
                hunt_idx = i
                hunt_level = don_h[i] # Breakout level
                hunt_atr = a
            elif short_setup:
                hunting = -1
                hunt_idx = i
                hunt_level = don_l[i]
                hunt_atr = a
        else:
            if (i - hunt_idx) > 6:
                hunting = 0
            elif hunting == 1:
                # Retest of broken breakout level OR touch of 15m EMA 20
                retest = (l <= hunt_level) or (l <= m15_e20[i])
                rejection = (c > o)
                if retest and rejection and in_active_hours:
                    raw_sl = min(hunt_level, l) - (hunt_atr * sl_mult)
                    sl_dist = max(c - raw_sl, min_sl_dist)
                    if sl_dist <= max_sl_dist:
                        state = 1
                        hunting = 0
                        entry_price = c
                        entry_idx = i
                        sl_price = entry_price - sl_dist
                        tp_price = entry_price + (sl_dist * rr)
            elif hunting == -1:
                retest = (h >= hunt_level) or (h >= m15_e20[i])
                rejection = (c < o)
                if retest and rejection and in_active_hours:
                    raw_sl = max(hunt_level, h) + (hunt_atr * sl_mult)
                    sl_dist = max(raw_sl - c, min_sl_dist)
                    if sl_dist <= max_sl_dist:
                        state = -1
                        hunting = 0
                        entry_price = c
                        entry_idx = i
                        sl_price = entry_price + sl_dist
                        tp_price = entry_price - (sl_dist * rr)
                        
    df_t = pd.DataFrame(trades)
    df_t['time'] = pd.to_datetime(df_t['time'])
    sep_trades = df_t[df_t['time'] >= '2026-09-01'].copy()
    
    print(f"USDJPY Total Trades in Entire Dataset: {len(df_t)}")
    print(f"USDJPY Trades in September 2026: {len(sep_trades)}")
    print(sep_trades[['time', 'res', 'pips', 'R']].to_string())

test_signal_frequency_solution()
