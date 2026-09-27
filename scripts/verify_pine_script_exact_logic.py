import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

def verify_pine_script_exact_logic():
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        data = pickle.load(f)
    pairs_data = data[1]
    
    pairs = ['USDCAD', 'USDCHF', 'USDJPY', 'AUDUSD']
    
    portfolio_trades = []
    
    for pair in pairs:
        m15 = pairs_data[pair]['M15'].copy()
        h1 = pairs_data[pair]['H1'].copy()
        
        pip_unit = 0.01 if 'JPY' in pair else 0.0001
        min_sl_dist = 18.0 * pip_unit
        max_sl_dist = 60.0 * pip_unit
        rr = 1.75
        sl_mult = 0.5
        
        m15['time_dt'] = pd.to_datetime(m15['time'], unit='s')
        h1['time_dt'] = pd.to_datetime(h1['time'], unit='s')
        
        # 1H Responsive Trend Engine
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
        
        # 15m RSI
        delta = pd.Series(close).diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = (100 - (100 / (1 + rs))).bfill().values
        
        # Donchian 36-bar
        don_h = pd.Series(high).shift(1).rolling(36).max().bfill().values
        don_l = pd.Series(low).shift(1).rolling(36).min().bfill().values
        
        rng = np.maximum(high - low, 1e-6)
        body_long = (close - low) / rng
        body_short = (high - close) / rng
        
        # Healthy Breakout (No rigid overbought/oversold cutoff)
        break_high = (close > don_h) & (np.roll(close, 1) <= np.roll(don_h, 1)) & (body_long >= 0.35) & (rsi >= 35.0) & (rsi <= 80.0)
        break_low = (close < don_l) & (np.roll(close, 1) >= np.roll(don_l, 1)) & (body_short >= 0.35) & (rsi <= 65.0) & (rsi >= 20.0)
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
        hunt_break_level = 0.0
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
                        portfolio_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'WIN', 'R': rr, 'pips': (tp_price - entry_price)/pip_unit})
                        state = 0
                        last_exit_idx = i
                        consec_losses = 0
                    elif l <= sl_price:
                        portfolio_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'LOSS', 'R': -1.0, 'pips': (sl_price - entry_price)/pip_unit})
                        state = 0
                        last_exit_idx = i
                        consec_losses += 1
                        if consec_losses >= 2:
                            lockout_until = i + 48 # Circuit breaker pause
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (c - entry_price) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        portfolio_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'R': pips / ((entry_price - sl_price)/pip_unit), 'pips': pips})
                        state = 0
                        last_exit_idx = i
                elif state == -1:
                    if l <= tp_price:
                        portfolio_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'WIN', 'R': rr, 'pips': (entry_price - tp_price)/pip_unit})
                        state = 0
                        last_exit_idx = i
                        consec_losses = 0
                    elif h >= sl_price:
                        portfolio_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'LOSS', 'R': -1.0, 'pips': (entry_price - sl_price)/pip_unit})
                        state = 0
                        last_exit_idx = i
                        consec_losses += 1
                        if consec_losses >= 2:
                            lockout_until = i + 48
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (entry_price - c) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        portfolio_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'R': pips / ((sl_price - entry_price)/pip_unit), 'pips': pips})
                        state = 0
                        last_exit_idx = i
                continue
            
            if i < lockout_until or (i - last_exit_idx) < 3:
                continue
                
            in_active_hours = (hr != 21) # avoid 21:00 UTC rollover
            
            if hunting == 0:
                long_setup = break_high[i] and h1_bull[i] and (m15_e20[i] > m15_e50[i]) and in_active_hours
                short_setup = break_low[i] and h1_bear[i] and (m15_e20[i] < m15_e50[i]) and in_active_hours
                
                if long_setup:
                    hunting = 1
                    hunt_idx = i
                    hunt_break_level = don_h[i]
                    hunt_ob_h = high[i-1] if close[i-1] < open_[i-1] else high[i]
                    hunt_ob_l = low[i-1] if close[i-1] < open_[i-1] else low[i]
                    hunt_atr = a
                    sw_l = min(hunt_ob_l, low[i])
                    sw_h = high[i]
                    hunt_fib_50 = sw_h - 0.50 * (sw_h - sw_l)
                elif short_setup:
                    hunting = -1
                    hunt_idx = i
                    hunt_break_level = don_l[i]
                    hunt_ob_h = high[i-1] if close[i-1] > open_[i-1] else high[i]
                    hunt_ob_l = low[i-1] if close[i-1] > open_[i-1] else low[i]
                    hunt_atr = a
                    sw_h = max(hunt_ob_h, high[i])
                    sw_l = low[i]
                    hunt_fib_50 = sw_l + 0.50 * (sw_h - sw_l)
            else:
                if (i - hunt_idx) > 8:
                    hunting = 0
                elif hunting == 1:
                    # Retest of breakout level OR touch of 15m EMA 20 OR Fib 50
                    retest = (l <= hunt_break_level * 1.0005) or (l <= m15_e20[i]) or (l <= hunt_fib_50) or (l <= hunt_ob_h)
                    rejection = (c > o)
                    rsi_ok = (rsi[i] <= 78.0)
                    if retest and rejection and rsi_ok and in_active_hours:
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
                    retest = (h >= hunt_break_level * 0.9995) or (h >= m15_e20[i]) or (h >= hunt_fib_50) or (h >= hunt_ob_l)
                    rejection = (c < o)
                    rsi_ok = (rsi[i] >= 22.0)
                    if retest and rejection and rsi_ok and in_active_hours:
                        raw_sl = max(hunt_ob_h, h) + (hunt_atr * sl_mult)
                        sl_dist = max(raw_sl - c, min_sl_dist)
                        if sl_dist <= max_sl_dist:
                            state = -1
                            hunting = 0
                            entry_price = c
                            entry_idx = i
                            sl_price = entry_price + sl_dist
                            tp_price = entry_price - (sl_dist * rr)
                            
    df_all = pd.DataFrame(portfolio_trades)
    df_all['time'] = pd.to_datetime(df_all['time'])
    df_all = df_all.sort_values('time').reset_index(drop=True)
    
    df_sep = df_all[df_all['time'] >= '2026-09-01'].copy()
    df_6m = df_all[df_all['time'] >= '2026-03-15'].copy()
    
    print("=== LAST 6 MONTHS PERFORMANCE ===")
    print(f"Total Trades: {len(df_6m)}")
    w6 = len(df_6m[df_6m['res'] == 'WIN'])
    l6 = len(df_6m[df_6m['res'] == 'LOSS'])
    wr6 = w6 / len(df_6m) * 100 if len(df_6m) > 0 else 0
    p6 = df_6m['pips'].sum()
    print(f"Win Rate: {wr6:.1f}% ({w6}W / {l6}L) | Net Pips: {p6:+.1f}")
    for pair, grp in df_6m.groupby('pair'):
        pw = len(grp[grp['res'] == 'WIN'])
        pl = len(grp[grp['res'] == 'LOSS'])
        pwr = pw / len(grp) * 100
        pp = grp['pips'].sum()
        print(f"  {pair:<7}: {len(grp):3d} trades ({pw:2d}W / {pl:2d}L) | WR: {pwr:4.1f}% | Net Pips: {pp:+7.1f}")
        
    print("\n=== SEPTEMBER 2026 RESULTS (PINE SCRIPT EXACT MATCH) ===")
    print(f"Total September Trades across Portfolio: {len(df_sep)}")
    for pair, grp in df_sep.groupby('pair'):
        w = len(grp[grp['res'] == 'WIN'])
        l = len(grp[grp['res'] == 'LOSS'])
        wr = w / len(grp) * 100
        p = grp['pips'].sum()
        print(f"  {pair:<7}: {len(grp):2d} trades ({w}W / {l}L) | WR: {wr:4.1f}% | Net Pips: {p:+6.1f}")
        
    print("\nUSDJPY September Trades:")
    uj_sep = df_sep[df_sep['pair'] == 'USDJPY']
    print(uj_sep[['time', 'res', 'pips', 'R']].to_string())

if __name__ == '__main__':
    verify_pine_script_exact_logic()
