import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

def test_donchian_lengths():
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        data = pickle.load(f)
    pairs_data = data[1]
    pairs = ['USDCAD', 'USDCHF', 'USDJPY', 'AUDUSD']
    
    for d_len in [20, 28, 36, 48]:
        trades = []
        for pair in pairs:
            if pair not in pairs_data:
                continue
            m15 = pairs_data[pair]['M15'].copy()
            h1 = pairs_data[pair]['H1'].copy()
            pip_unit = 0.01 if 'JPY' in pair else 0.0001
            min_sl_dist = 18.0 * pip_unit
            max_sl_dist = 60.0 * pip_unit
            rr = 1.75
            sl_mult = 0.5
            
            m15['time_dt'] = pd.to_datetime(m15['time'], unit='s')
            h1['time_dt'] = pd.to_datetime(h1['time'], unit='s')
            
            h1['e20'] = h1['close'].ewm(span=20, adjust=False).mean()
            h1['e50'] = h1['close'].ewm(span=50, adjust=False).mean()
            h1['e20_slope'] = h1['e20'] - h1['e20'].shift(2)
            h1['macro_bull'] = (h1['close'] > h1['e50']) & (h1['e20'] > h1['e50']) & (h1['e20_slope'] > 0)
            h1['macro_bear'] = (h1['close'] < h1['e50']) & (h1['e20'] < h1['e50']) & (h1['e20_slope'] < 0)
            
            m15['h1_time'] = m15['time_dt'].dt.floor('h') - pd.Timedelta(hours=1)
            m15['h1_bull'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['macro_bull']))).fillna(False).values
            m15['h1_bear'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['macro_bear']))).fillna(False).values
            
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
            
            # Donchian
            don_h = pd.Series(high).shift(1).rolling(d_len).max().bfill().values
            don_l = pd.Series(low).shift(1).rolling(d_len).min().bfill().values
            
            rng = np.maximum(high - low, 1e-6)
            body_long = (close - low) / rng
            body_short = (high - close) / rng
            
            break_high = (close > don_h) & (np.roll(close, 1) <= np.roll(don_h, 1)) & (body_long >= 0.35)
            break_low = (close < don_l) & (np.roll(close, 1) >= np.roll(don_l, 1)) & (body_short >= 0.35)
            break_high[0] = False
            break_low[0] = False
            
            h1_bull = m15['h1_bull']
            h1_bear = m15['h1_bear']
            
            state = 0
            entry_price = 0.0
            sl_price = 0.0
            tp_price = 0.0
            entry_idx = 0
            hunting = 0
            hunt_idx = 0
            hunt_level = 0.0
            hunt_atr = 0.0
            last_exit_idx = -999
            consec_losses = 0
            lockout_until = 0
            
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
                            trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'WIN', 'pips': (tp_price - entry_price)/pip_unit})
                            state = 0
                            last_exit_idx = i
                            consec_losses = 0
                        elif l <= sl_price:
                            trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'LOSS', 'pips': (sl_price - entry_price)/pip_unit})
                            state = 0
                            last_exit_idx = i
                            consec_losses += 1
                            if consec_losses >= 2:
                                lockout_until = i + 48
                                consec_losses = 0
                        elif (i - entry_idx) >= 160:
                            pips = (c - entry_price) / pip_unit
                            res = 'WIN' if pips > 0 else 'LOSS'
                            trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'pips': pips})
                            state = 0
                            last_exit_idx = i
                    elif state == -1:
                        if l <= tp_price:
                            trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'WIN', 'pips': (entry_price - tp_price)/pip_unit})
                            state = 0
                            last_exit_idx = i
                            consec_losses = 0
                        elif h >= sl_price:
                            trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'LOSS', 'pips': (entry_price - sl_price)/pip_unit})
                            state = 0
                            last_exit_idx = i
                            consec_losses += 1
                            if consec_losses >= 2:
                                lockout_until = i + 48
                                consec_losses = 0
                        elif (i - entry_idx) >= 160:
                            pips = (entry_price - c) / pip_unit
                            res = 'WIN' if pips > 0 else 'LOSS'
                            trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'pips': pips})
                            state = 0
                            last_exit_idx = i
                    continue
                
                if i < lockout_until or (i - last_exit_idx) < 3:
                    continue
                    
                in_active_hours = (hr != 21)
                
                if hunting == 0:
                    long_setup = break_high[i] and h1_bull[i] and (m15_e20[i] > m15_e50[i]) and in_active_hours
                    short_setup = break_low[i] and h1_bear[i] and (m15_e20[i] < m15_e50[i]) and in_active_hours
                    
                    if long_setup:
                        hunting = 1
                        hunt_idx = i
                        hunt_level = don_h[i]
                        hunt_atr = a
                    elif short_setup:
                        hunting = -1
                        hunt_idx = i
                        hunt_level = don_l[i]
                        hunt_atr = a
                else:
                    if (i - hunt_idx) > 8:
                        hunting = 0
                    elif hunting == 1:
                        retest = (l <= hunt_level * 1.0005) or (l <= m15_e20[i])
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
                        retest = (h >= hunt_level * 0.9995) or (h >= m15_e20[i])
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
                                
        df = pd.DataFrame(trades)
        df['time'] = pd.to_datetime(df['time'])
        df_sep = df[df['time'] >= '2026-09-01']
        df_6m = df[df['time'] >= '2026-03-15']
        
        w_6m = len(df_6m[df_6m['res']=='WIN'])
        wr_6m = w_6m / len(df_6m) * 100 if len(df_6m) > 0 else 0
        pips_6m = df_6m['pips'].sum()
        
        w_sep = len(df_sep[df_sep['res']=='WIN'])
        wr_sep = w_sep / len(df_sep) * 100 if len(df_sep) > 0 else 0
        pips_sep = df_sep['pips'].sum()
        
        print(f"Donchian {d_len:2d}: 6M={len(df_6m):3d} trades, WR={wr_6m:4.1f}%, Pips={pips_6m:+7.1f} | Sept={len(df_sep):2d} trades, WR={wr_sep:4.1f}%, Pips={pips_sep:+6.1f}")

if __name__ == '__main__':
    test_donchian_lengths()
