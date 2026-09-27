import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

def run_portfolio_benchmark():
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        data = pickle.load(f)
    pairs_data = data[1]
    
    # Portfolio whitelist
    pairs = ['USDJPY', 'USDCAD', 'USDCHF', 'AUDUSD', 'EURUSD', 'GBPUSD']
    
    rr = 1.75
    sl_mult = 0.5
    
    portfolio_trades = []
    
    for pair in pairs:
        if pair not in pairs_data:
            continue
        m15 = pairs_data[pair]['M15'].copy()
        h1 = pairs_data[pair]['H1'].copy()
        
        pip_unit = 0.01 if 'JPY' in pair else 0.0001
        min_sl_dist = 18.0 * pip_unit
        max_sl_dist = 60.0 * pip_unit
        
        m15['time_dt'] = pd.to_datetime(m15['time'], unit='s')
        h1['time_dt'] = pd.to_datetime(h1['time'], unit='s')
        
        # Responsive 1H Trend (EMA 20 vs EMA 50)
        h1['e20'] = h1['close'].ewm(span=20, adjust=False).mean()
        h1['e50'] = h1['close'].ewm(span=50, adjust=False).mean()
        h1['e20_slope'] = h1['e20'] - h1['e20'].shift(2)
        
        h1['bull'] = (h1['close'] > h1['e50']) & (h1['e20'] > h1['e50']) & (h1['e20_slope'] > 0)
        h1['bear'] = (h1['close'] < h1['e50']) & (h1['e20'] < h1['e50']) & (h1['e20_slope'] < 0)
        
        m15['h1_time'] = m15['time_dt'].dt.floor('h') - pd.Timedelta(hours=1)
        m15['h1_bull'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['bull']))).fillna(False).values
        m15['h1_bear'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['bear']))).fillna(False).values
        
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
        
        # 20-bar Donchian
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
        
        # Circuit breaker: max consecutive losses
        consec_losses = 0
        pause_until = 0
        
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
                        consec_losses = 0
                    elif l <= sl_price:
                        portfolio_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'LOSS', 'R': -1.0, 'pips': (sl_price - entry_price)/pip_unit})
                        state = 0
                        consec_losses += 1
                        if consec_losses >= 3:
                            pause_until = i + 24 # 6 hours cooldown
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (c - entry_price) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        portfolio_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'R': pips / ((entry_price - sl_price)/pip_unit), 'pips': pips})
                        state = 0
                elif state == -1:
                    if l <= tp_price:
                        portfolio_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'WIN', 'R': rr, 'pips': (entry_price - tp_price)/pip_unit})
                        state = 0
                        consec_losses = 0
                    elif h >= sl_price:
                        portfolio_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'LOSS', 'R': -1.0, 'pips': (entry_price - sl_price)/pip_unit})
                        state = 0
                        consec_losses += 1
                        if consec_losses >= 3:
                            pause_until = i + 24
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (entry_price - c) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        portfolio_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'R': pips / ((sl_price - entry_price)/pip_unit), 'pips': pips})
                        state = 0
                continue
            
            if i < pause_until:
                continue
                
            in_active_hours = (hr != 21) # avoid spread rollover
            
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
                if (i - hunt_idx) > 6:
                    hunting = 0
                elif hunting == 1:
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
                            
    df_all = pd.DataFrame(portfolio_trades)
    df_all['time'] = pd.to_datetime(df_all['time'])
    df_all = df_all.sort_values('time').reset_index(drop=True)
    
    # Analyze 6-month performance (March 15, 2026 to Sep 15, 2026)
    df_6m = df_all[df_all['time'] >= '2026-03-15'].copy()
    
    print("=== PORTFOLIO PERFORMANCE (Last 6 Months: March - Sept 2026) ===")
    print(f"Total Trades: {len(df_6m)}")
    wins = len(df_6m[df_6m['res'] == 'WIN'])
    losses = len(df_6m[df_6m['res'] == 'LOSS'])
    winrate = wins / len(df_6m) * 100 if len(df_6m) > 0 else 0
    total_pips = df_6m['pips'].sum()
    total_r = df_6m['R'].sum()
    gross_win_pips = df_6m[df_6m['pips'] > 0]['pips'].sum()
    gross_loss_pips = abs(df_6m[df_6m['pips'] < 0]['pips'].sum())
    pf = gross_win_pips / gross_loss_pips if gross_loss_pips > 0 else 0
    
    print(f"Wins: {wins}, Losses: {losses}, Win Rate: {winrate:.1f}%")
    print(f"Total Net Pips: {total_pips:.1f} pips")
    print(f"Total Net R: {total_r:.2f} R")
    print(f"Profit Factor: {pf:.2f}")
    
    print("\n--- By Pair Breakdown (Last 6 Months) ---")
    for pair, group in df_6m.groupby('pair'):
        p_wins = len(group[group['res'] == 'WIN'])
        p_losses = len(group[group['res'] == 'LOSS'])
        p_wr = p_wins / len(group) * 100 if len(group) > 0 else 0
        p_pips = group['pips'].sum()
        p_gw = group[group['pips'] > 0]['pips'].sum()
        p_gl = abs(group[group['pips'] < 0]['pips'].sum())
        p_pf = p_gw / p_gl if p_gl > 0 else 0
        print(f"{pair}: {len(group)} trades | WR: {p_wr:.1f}% | Pips: {p_pips:+7.1f} | PF: {p_pf:.2f}")

    print("\n--- Trades in September 2026 across Pairs ---")
    df_sep = df_all[df_all['time'] >= '2026-09-01']
    print(f"Total September Trades: {len(df_sep)}")
    for pair, group in df_sep.groupby('pair'):
        print(f"  {pair}: {len(group)} trades, {group['pips'].sum():+5.1f} pips")

if __name__ == '__main__':
    run_portfolio_benchmark()
