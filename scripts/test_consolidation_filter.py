import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

def compute_adx(high, low, close, length=14):
    up = high - high.shift(1)
    down = low.shift(1) - low
    
    pos_dm = np.where((up > down) & (up > 0), up, 0.0)
    neg_dm = np.where((down > up) & (down > 0), down, 0.0)
    
    tr = np.maximum(high - low, np.maximum(np.abs(high - close.shift(1)), np.abs(low - close.shift(1))))
    
    tr_smooth = pd.Series(tr).ewm(alpha=1/length, adjust=False).mean()
    pos_smooth = pd.Series(pos_dm).ewm(alpha=1/length, adjust=False).mean()
    neg_smooth = pd.Series(neg_dm).ewm(alpha=1/length, adjust=False).mean()
    
    pdi = (pos_smooth / tr_smooth) * 100
    ndi = (neg_smooth / tr_smooth) * 100
    
    dx = (np.abs(pdi - ndi) / (pdi + ndi + 1e-9)) * 100
    adx = dx.ewm(alpha=1/length, adjust=False).mean()
    return adx, pdi, ndi

def run_consolidation_tests():
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        data = pickle.load(f)
    pairs_data = data[1]
    
    pairs = ['USDCAD', 'USDCHF', 'USDJPY', 'AUDUSD']
    
    # We want to test different 1H consolidation filters:
    # 1. Baseline (Current)
    # 2. 1H ADX >= 18, 20, 22
    # 3. 1H EMA Spread: abs(EMA 20 - EMA 50) >= threshold * 1H ATR
    # 4. 1H BB Squeeze: Bandwidth >= threshold
    
    configs = [
        {'name': 'Baseline (No HTF Consolidation Filter)', 'type': 'none'},
        {'name': '1H ADX >= 18', 'type': 'adx', 'thresh': 18},
        {'name': '1H ADX >= 20', 'type': 'adx', 'thresh': 20},
        {'name': '1H ADX >= 22', 'type': 'adx', 'thresh': 22},
        {'name': '1H EMA Spread >= 0.20 ATR', 'type': 'ema_spread', 'thresh': 0.20},
        {'name': '1H EMA Spread >= 0.30 ATR', 'type': 'ema_spread', 'thresh': 0.30},
        {'name': '1H ADX >= 20 + EMA Spread >= 0.20 ATR', 'type': 'combo', 'adx': 20, 'spread': 0.20},
    ]
    
    for cfg in configs:
        portfolio_trades = []
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
            
            # 1H Calculations
            h1['e20'] = h1['close'].ewm(span=20, adjust=False).mean()
            h1['e50'] = h1['close'].ewm(span=50, adjust=False).mean()
            h1['e20_slope'] = h1['e20'] - h1['e20'].shift(2)
            
            tr_h1 = np.maximum(h1['high'] - h1['low'], np.maximum(np.abs(h1['high'] - h1['close'].shift(1)), np.abs(h1['low'] - h1['close'].shift(1))))
            h1['atr'] = pd.Series(tr_h1).rolling(14).mean().bfill()
            
            adx, pdi, ndi = compute_adx(h1['high'], h1['low'], h1['close'], 14)
            h1['adx'] = adx
            h1['ema_spread_ratio'] = (h1['e20'] - h1['e50']).abs() / (h1['atr'] + 1e-9)
            
            # Consolidation flag on 1H
            if cfg['type'] == 'none':
                h1['not_consolidating'] = True
            elif cfg['type'] == 'adx':
                h1['not_consolidating'] = h1['adx'] >= cfg['thresh']
            elif cfg['type'] == 'ema_spread':
                h1['not_consolidating'] = h1['ema_spread_ratio'] >= cfg['thresh']
            elif cfg['type'] == 'combo':
                h1['not_consolidating'] = (h1['adx'] >= cfg['adx']) & (h1['ema_spread_ratio'] >= cfg['spread'])
                
            h1['macro_bull'] = (h1['close'] > h1['e50']) & (h1['e20'] > h1['e50']) & (h1['e20_slope'] > 0) & h1['not_consolidating']
            h1['macro_bear'] = (h1['close'] < h1['e50']) & (h1['e20'] < h1['e50']) & (h1['e20_slope'] < 0) & h1['not_consolidating']
            
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
            
            delta = pd.Series(close).diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            rs = gain.rolling(14).mean() / (loss.rolling(14).mean() + 1e-9)
            rsi = (100 - (100 / (1 + rs))).bfill().values
            
            # Donchian 32
            don_h = pd.Series(high).shift(1).rolling(32).max().bfill().values
            don_l = pd.Series(low).shift(1).rolling(32).min().bfill().values
            
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
            hunt_ob_h = 0.0
            hunt_ob_l = 0.0
            hunt_fib_50 = 0.0
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
                            portfolio_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'WIN', 'pips': (tp_price - entry_price)/pip_unit, 'R': rr})
                            state = 0
                            last_exit_idx = i
                            consec_losses = 0
                        elif l <= sl_price:
                            portfolio_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'LOSS', 'pips': (sl_price - entry_price)/pip_unit, 'R': -1.0})
                            state = 0
                            last_exit_idx = i
                            consec_losses += 1
                            if consec_losses >= 2:
                                lockout_until = i + 48
                                consec_losses = 0
                        elif (i - entry_idx) >= 160:
                            pips = (c - entry_price) / pip_unit
                            res = 'WIN' if pips > 0 else 'LOSS'
                            portfolio_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'pips': pips, 'R': pips/((entry_price-sl_price)/pip_unit)})
                            state = 0
                            last_exit_idx = i
                    elif state == -1:
                        if l <= tp_price:
                            portfolio_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'WIN', 'pips': (entry_price - tp_price)/pip_unit, 'R': rr})
                            state = 0
                            last_exit_idx = i
                            consec_losses = 0
                        elif h >= sl_price:
                            portfolio_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'LOSS', 'pips': (entry_price - sl_price)/pip_unit, 'R': -1.0})
                            state = 0
                            last_exit_idx = i
                            consec_losses += 1
                            if consec_losses >= 2:
                                lockout_until = i + 48
                                consec_losses = 0
                        elif (i - entry_idx) >= 160:
                            pips = (entry_price - c) / pip_unit
                            res = 'WIN' if pips > 0 else 'LOSS'
                            portfolio_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'pips': pips, 'R': pips/((sl_price-entry_price)/pip_unit)})
                            state = 0
                            last_exit_idx = i
                    continue
                    
                if i < lockout_until or (i - last_exit_idx) < 3:
                    continue
                    
                in_active_hours = (hr != 21)
                
                if hunting == 0:
                    long_setup = break_high[i] and h1_bull[i] and (m15_e20[i] > m15_e50[i]) and in_active_hours and (rsi[i] >= 35 and rsi[i] <= 80)
                    short_setup = break_low[i] and h1_bear[i] and (m15_e20[i] < m15_e50[i]) and in_active_hours and (rsi[i] <= 65 and rsi[i] >= 20)
                    
                    if long_setup:
                        hunting = 1
                        hunt_idx = i
                        hunt_level = don_h[i]
                        hunt_ob_l = low[i-1] if close[i-1] < open_[i-1] else low[i]
                        hunt_ob_h = high[i-1] if close[i-1] < open_[i-1] else high[i]
                        hunt_fib_50 = high[i] - 0.50 * (high[i] - hunt_ob_l)
                        hunt_atr = a
                    elif short_setup:
                        hunting = -1
                        hunt_idx = i
                        hunt_level = don_l[i]
                        hunt_ob_h = high[i-1] if close[i-1] > open_[i-1] else high[i]
                        hunt_ob_l = low[i-1] if close[i-1] > open_[i-1] else low[i]
                        hunt_fib_50 = low[i] + 0.50 * (hunt_ob_h - low[i])
                        hunt_atr = a
                else:
                    if (i - hunt_idx) > 8:
                        hunting = 0
                    elif hunting == 1:
                        retest = (l <= hunt_level * 1.0005) or (l <= m15_e20[i]) or (l <= hunt_fib_50) or (l <= hunt_ob_h)
                        rejection = (c > o)
                        if retest and rejection and (rsi[i] <= 78) and in_active_hours:
                            raw_sl = min(hunt_ob_l, l) - (hunt_atr * sl_mult)
                            sl_dist = max(c - raw_sl, min_sl_dist)
                            if sl_dist <= max_sl_dist:
                                state = 1
                                hunting = 0
                                entry_price = c
                                entry_idx = i
                                sl_price = entry_price - sl_dist
                                tp_price = entry_price + (sl_dist * rr)
                    elif hunting == -1:
                        retest = (h >= hunt_level * 0.9995) or (h >= m15_e20[i]) or (h >= hunt_fib_50) or (h >= hunt_ob_l)
                        rejection = (c < o)
                        if retest and rejection and (rsi[i] >= 22) and in_active_hours:
                            raw_sl = max(hunt_ob_h, h) + (hunt_atr * sl_mult)
                            sl_dist = max(raw_sl - c, min_sl_dist)
                            if sl_dist <= max_sl_dist:
                                state = -1
                                hunting = 0
                                entry_price = c
                                entry_idx = i
                                sl_price = entry_price + sl_dist
                                tp_price = entry_price - (sl_dist * rr)
                                
        df = pd.DataFrame(portfolio_trades)
        df['time'] = pd.to_datetime(df['time'])
        df_sep = df[df['time'] >= '2026-09-01']
        df_6m = df[df['time'] >= '2026-03-15']
        
        w6 = len(df_6m[df_6m['res']=='WIN'])
        wr6 = w6 / len(df_6m) * 100 if len(df_6m) > 0 else 0
        pips6 = df_6m['pips'].sum()
        gw6 = df_6m[df_6m['pips'] > 0]['pips'].sum()
        gl6 = abs(df_6m[df_6m['pips'] < 0]['pips'].sum())
        pf6 = gw6 / gl6 if gl6 > 0 else 0
        
        ws = len(df_sep[df_sep['res']=='WIN'])
        wrs = ws / len(df_sep) * 100 if len(df_sep) > 0 else 0
        pipss = df_sep['pips'].sum()
        
        print(f"[{cfg['name']:<42}] 6M: {len(df_6m):3d} tr | WR: {wr6:4.1f}% | PF: {pf6:4.2f} | Pips: {pips6:+7.1f} || Sept: {len(df_sep):2d} tr | WR: {wrs:4.1f}% | Pips: {pipss:+6.1f}")

if __name__ == '__main__':
    run_consolidation_tests()
