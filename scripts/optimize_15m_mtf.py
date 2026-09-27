import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np
from scripts.test_strategies_deep import print_summary

def load_all_m15_and_h1():
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        data = pickle.load(f)
    return data[1]

def test_15m_variations(pairs_data, donch_len=32, require_session=True, require_m15_ema=True, 
                        min_sl_pips=16.0, sl_mult=0.5, rr=1.5):
    results = {}
    
    for pair, tfs in pairs_data.items():
        m15 = tfs['M15'].copy()
        h1 = tfs['H1'].copy()
        d1 = tfs['D1'].copy()
        
        is_jpy = "JPY" in pair
        pip_unit = 0.01 if is_jpy else 0.0001
        min_sl_dist = min_sl_pips * pip_unit
        max_sl_dist = 50.0 * pip_unit
        
        # 1. D1 Macro trend
        d1['ema50'] = d1['close'].ewm(span=50, adjust=False).mean()
        d1['time_dt'] = pd.to_datetime(d1['time'], unit='s').dt.floor('D')
        
        # 2. H1 Trend alignment
        h1['time_dt'] = pd.to_datetime(h1['time'], unit='s')
        h1['ema200'] = h1['close'].ewm(span=200, adjust=False).mean()
        h1['ema50'] = h1['close'].ewm(span=50, adjust=False).mean()
        h1['ema20'] = h1['close'].ewm(span=20, adjust=False).mean()
        
        h1['date_only'] = h1['time_dt'].dt.floor('D')
        d1_bull_map = dict(zip(d1['time_dt'], d1['close'] > d1['ema50']))
        h1['d1_bull'] = h1['date_only'].map(d1_bull_map).fillna(False)
        
        # Full 1H alignment
        h1['h1_bull'] = (h1['close'] > h1['ema200']) & (h1['ema20'] > h1['ema50']) & (h1['d1_bull'])
        h1['h1_bear'] = (h1['close'] < h1['ema200']) & (h1['ema20'] < h1['ema50']) & (~h1['d1_bull'])
        
        m15['time_dt'] = pd.to_datetime(m15['time'], unit='s')
        m15['h1_time'] = m15['time_dt'].dt.floor('h') - pd.Timedelta(hours=1)
        
        h1_bull_map = dict(zip(h1['time_dt'], h1['h1_bull']))
        h1_bear_map = dict(zip(h1['time_dt'], h1['h1_bear']))
        
        m15['h1_bull'] = m15['h1_time'].map(h1_bull_map).fillna(False).values
        m15['h1_bear'] = m15['h1_time'].map(h1_bear_map).fillna(False).values
        
        close = m15['close'].values
        open_ = m15['open'].values
        high = m15['high'].values
        low = m15['low'].values
        hours = m15['time_dt'].dt.hour.values
        n = len(close)
        
        # M15 EMAs
        m15_ema20 = m15['close'].ewm(span=20, adjust=False).mean().values
        m15_ema50 = m15['close'].ewm(span=50, adjust=False).mean().values
        
        # M15 ATR
        tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
        tr[0] = high[0] - low[0]
        atr = pd.Series(tr).rolling(14).mean().bfill().values
        
        # M15 Donchian
        don_h = pd.Series(high).shift(1).rolling(donch_len).max().bfill().values
        don_l = pd.Series(low).shift(1).rolling(donch_len).min().bfill().values
        
        break_high = (close > don_h) & (np.roll(close, 1) <= np.roll(don_h, 1))
        break_low = (close < don_l) & (np.roll(close, 1) >= np.roll(don_l, 1))
        break_high[0] = False
        break_low[0] = False
        
        delta = pd.Series(close).diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi = (100 - (100 / (1 + rs))).bfill().values
        
        prev_is_bear = np.roll(close, 1) < np.roll(open_, 1)
        prev_is_bull = np.roll(close, 1) > np.roll(open_, 1)
        ob_bull_l = np.where(prev_is_bear, np.roll(low, 1), low)
        ob_bear_h = np.where(prev_is_bull, np.roll(high, 1), high)
        
        h1_bull = m15['h1_bull'].values
        h1_bear = m15['h1_bear'].values
        
        trades = []
        state = 0
        entry_price = 0.0
        sl_price = 0.0
        tp_price = 0.0
        entry_idx = 0
        hunting = 0
        hunt_idx = 0
        hunt_ob_l = 0.0
        hunt_ob_h = 0.0
        hunt_fib50 = 0.0
        hunt_atr = 0.0
        
        consec_losses = 0
        pause_until_idx = -999
        
        for i in range(200, n):
            c = close[i]
            h = high[i]
            l = low[i]
            o = open_[i]
            a = atr[i]
            hr = hours[i]
            
            if state != 0:
                if state == 1:
                    if h >= tp_price:
                        trades.append({'pair': pair, 'exit_idx': i, 'res': 'WIN', 'pips': (tp_price - entry_price) / pip_unit, 'R': rr, 'hold': i - entry_idx})
                        state = 0
                        consec_losses = 0
                    elif l <= sl_price:
                        trades.append({'pair': pair, 'exit_idx': i, 'res': 'LOSS', 'pips': (sl_price - entry_price) / pip_unit, 'R': -1.0, 'hold': i - entry_idx})
                        state = 0
                        consec_losses += 1
                        if consec_losses >= 2:
                            pause_until_idx = i + 32 # 32 bars on 15m = 8 hours pause on 2 consecutive losses
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (c - entry_price) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        r_mult = pips / ((entry_price - sl_price) / pip_unit)
                        trades.append({'pair': pair, 'exit_idx': i, 'res': res, 'pips': pips, 'R': r_mult, 'hold': i - entry_idx})
                        state = 0
                        if res == 'LOSS':
                            consec_losses += 1
                            if consec_losses >= 2:
                                pause_until_idx = i + 32
                                consec_losses = 0
                        else:
                            consec_losses = 0
                elif state == -1:
                    if l <= tp_price:
                        trades.append({'pair': pair, 'exit_idx': i, 'res': 'WIN', 'pips': (entry_price - tp_price) / pip_unit, 'R': rr, 'hold': i - entry_idx})
                        state = 0
                        consec_losses = 0
                    elif h >= sl_price:
                        trades.append({'pair': pair, 'exit_idx': i, 'res': 'LOSS', 'pips': (entry_price - sl_price) / pip_unit, 'R': -1.0, 'hold': i - entry_idx})
                        state = 0
                        consec_losses += 1
                        if consec_losses >= 2:
                            pause_until_idx = i + 32
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (entry_price - c) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        r_mult = pips / ((sl_price - entry_price) / pip_unit)
                        trades.append({'pair': pair, 'exit_idx': i, 'res': res, 'pips': pips, 'R': r_mult, 'hold': i - entry_idx})
                        state = 0
                        if res == 'LOSS':
                            consec_losses += 1
                            if consec_losses >= 2:
                                pause_until_idx = i + 32
                                consec_losses = 0
                        else:
                            consec_losses = 0
                continue
                
            if i < pause_until_idx:
                continue
                
            in_active_session = (hr >= 7 and hr <= 17) if require_session else True
            
            if hunting == 0:
                m15_bull = (m15_ema20[i] > m15_ema50[i]) if require_m15_ema else True
                m15_bear = (m15_ema20[i] < m15_ema50[i]) if require_m15_ema else True
                
                long_setup = break_high[i] and h1_bull[i] and m15_bull and (rsi[i] >= 40 and rsi[i] <= 70) and in_active_session
                short_setup = break_low[i] and h1_bear[i] and m15_bear and (rsi[i] >= 30 and rsi[i] <= 60) and in_active_session
                
                if long_setup:
                    hunting = 1
                    hunt_idx = i
                    hunt_ob_l = ob_bull_l[i]
                    hunt_ob_h = high[i]
                    hunt_fib50 = hunt_ob_h - 0.5 * (hunt_ob_h - hunt_ob_l)
                    hunt_atr = a
                elif short_setup:
                    hunting = -1
                    hunt_idx = i
                    hunt_ob_h = ob_bear_h[i]
                    hunt_ob_l = low[i]
                    hunt_fib50 = hunt_ob_l + 0.5 * (hunt_ob_h - hunt_ob_l)
                    hunt_atr = a
            else:
                if (i - hunt_idx) > 8: # 2 hours wait
                    hunting = 0
                elif hr == 21:
                    pass
                elif hunting == 1:
                    retrace = (l <= hunt_fib50) or (l <= hunt_ob_h)
                    rejection = c > o
                    if retrace and rejection and in_active_session:
                        raw_sl = hunt_ob_l - (hunt_atr * sl_mult)
                        sl_dist = max(c - raw_sl, min_sl_dist)
                        if sl_dist <= max_sl_dist:
                            state = 1
                            hunting = 0
                            entry_price = c
                            entry_idx = i
                            sl_price = entry_price - sl_dist
                            tp_price = entry_price + (sl_dist * rr)
                elif hunting == -1:
                    retrace = (h >= hunt_fib50) or (h >= hunt_ob_l)
                    rejection = c < o
                    if retrace and rejection and in_active_session:
                        raw_sl = hunt_ob_h + (hunt_atr * sl_mult)
                        sl_dist = max(raw_sl - c, min_sl_dist)
                        if sl_dist <= max_sl_dist:
                            state = -1
                            hunting = 0
                            entry_price = c
                            entry_idx = i
                            sl_price = entry_price + sl_dist
                            tp_price = entry_price - (sl_dist * rr)
                            
        results[pair] = pd.DataFrame(trades)
        
    return results

if __name__ == '__main__':
    data = load_all_m15_and_h1()
    
    print("\n--- CONFIG 1: 15m Lookback 32 (8h) + London/NY Session Filter (07-17 UTC) + 1H Trend ---")
    res1 = test_15m_variations(data, donch_len=32, require_session=True, require_m15_ema=True, min_sl_pips=16.0)
    print_summary(res1, "15m Lookback 32 + London/NY Session + 1H Trend")
    
    print("\n--- CONFIG 2: 15m Lookback 40 (10h) + London/NY Session Filter (07-17 UTC) + 1H Trend ---")
    res2 = test_15m_variations(data, donch_len=40, require_session=True, require_m15_ema=True, min_sl_pips=16.0)
    print_summary(res2, "15m Lookback 40 + London/NY Session + 1H Trend")
