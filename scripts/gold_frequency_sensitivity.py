"""
Gold Frequency vs Win Rate & Profitability Sensitivity Matrix
"""

import pickle
import pandas as pd
import numpy as np

def test_gold_params(donch_len, max_hunt, lockout_h, spacing, min_sl=15.0, max_sl=25.0):
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        data_cache = pickle.load(f)
        
    df = data_cache['XAUUSD'].copy()
    if df['time_dt'].dt.tz is not None:
        df['time_dt'] = df['time_dt'].dt.tz_localize(None)
    df = df.sort_values('time_dt').reset_index(drop=True)
    
    pip = 0.10
    sl_mult = 0.50
    rr = 1.75
    
    df['e20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['e50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['e20_slope'] = df['e20'] - df['e20'].shift(2)
    
    tr = np.maximum(df['high'] - df['low'], np.maximum(np.abs(df['high'] - df['close'].shift(1)), np.abs(df['low'] - df['close'].shift(1))))
    df['atr'] = pd.Series(tr).rolling(14).mean().bfill()
    
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / (loss.rolling(14).mean() + 1e-9)
    df['rsi'] = (100 - (100 / (1 + rs))).bfill()
    
    df['don_h'] = df['high'].shift(1).rolling(donch_len).max()
    df['don_l'] = df['low'].shift(1).rolling(donch_len).min()
    
    df_idx = df.set_index('time_dt')
    df_4h = df_idx.resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna().reset_index()
    df_4h['e20'] = df_4h['close'].ewm(span=20, adjust=False).mean()
    df_4h['e50'] = df_4h['close'].ewm(span=50, adjust=False).mean()
    df_4h['ema_bull'] = df_4h['e20'] > df_4h['e50']
    df_4h['ema_bear'] = df_4h['e20'] < df_4h['e50']
    
    df['h4_time'] = df['time_dt'].dt.floor('4h') - pd.Timedelta(hours=4)
    df['h4_bull'] = df['h4_time'].map(dict(zip(df_4h['time_dt'], df_4h['ema_bull']))).fillna(True)
    df['h4_bear'] = df['h4_time'].map(dict(zip(df_4h['time_dt'], df_4h['ema_bear']))).fillna(True)
    
    c = df['close'].values
    h = df['high'].values
    l = df['low'].values
    o = df['open'].values
    e20 = df['e20'].values
    e50 = df['e50'].values
    e20_slope = df['e20_slope'].values
    atr = df['atr'].values
    rsi = df['rsi'].values
    don_h = df['don_h'].values
    don_l = df['don_l'].values
    h4_bull = df['h4_bull'].values
    h4_bear = df['h4_bear'].values
    hours = df['time_dt'].dt.hour.values
    weekdays = df['time_dt'].dt.day_name().values
    
    trades = []
    state = 0
    entry_price, sl_price, tp_price = 0.0, 0.0, 0.0
    entry_idx = 0
    hunting = 0
    hunt_level, hunt_ob_h, hunt_ob_l, hunt_fib_50, hunt_atr, hunt_idx = 0.0, 0.0, 0.0, 0.0, 0.0, 0
    lockout_until = 0
    consec_losses = 0
    last_exit_idx = -999
    partial_taken = False
    partial_r_banked = 0.0
    initial_sl_dist = 0.0
    
    start_idx = 100
    n = len(df)
    
    for i in range(start_idx, n):
        if state != 0:
            hold = i - entry_idx
            if hold >= 1:
                init_sl_dist = initial_sl_dist
                
                if not partial_taken:
                    if state == 1 and (h[i] - entry_price) >= init_sl_dist:
                        partial_taken = True
                        partial_r_banked = 0.50
                        sl_price = entry_price + (1.0 * pip)
                    elif state == -1 and (entry_price - l[i]) >= init_sl_dist:
                        partial_taken = True
                        partial_r_banked = 0.50
                        sl_price = entry_price - (1.0 * pip)
                        
                exit_triggered = False
                exit_price = 0.0
                
                if state == 1:
                    if h[i] >= tp_price:
                        exit_triggered = True
                        exit_price = tp_price
                    elif l[i] <= sl_price:
                        exit_triggered = True
                        exit_price = sl_price
                    elif hold >= 72 and c[i] < e20[i]:
                        exit_triggered = True
                        exit_price = c[i]
                elif state == -1:
                    if l[i] <= tp_price:
                        exit_triggered = True
                        exit_price = tp_price
                    elif h[i] >= sl_price:
                        exit_triggered = True
                        exit_price = sl_price
                    elif hold >= 72 and c[i] > e20[i]:
                        exit_triggered = True
                        exit_price = c[i]
                        
                if exit_triggered:
                    dir_mult = 1 if state == 1 else -1
                    price_diff = (exit_price - entry_price) * dir_mult
                    rem_r = price_diff / (init_sl_dist + 1e-9)
                    
                    if partial_taken:
                        final_r = partial_r_banked + (rem_r * 0.50)
                        final_pips = ((1.0 * init_sl_dist / pip) * 0.50) + ((price_diff / pip) * 0.50)
                    else:
                        final_r = rem_r
                        final_pips = price_diff / pip
                        
                    outcome = 'WIN' if final_r > 0.05 else ('LOSS' if final_r < -0.05 else 'BREAKEVEN')
                    
                    trades.append({
                        'entry_time': df['time_dt'].iloc[entry_idx],
                        'month_cohort': df['time_dt'].iloc[entry_idx].strftime('%Y-%m'),
                        'result': outcome,
                        'realized_r': round(final_r, 2),
                        'realized_pips': round(final_pips, 1)
                    })
                    
                    state = 0
                    last_exit_idx = i
                    partial_taken = False
                    partial_r_banked = 0.0
                    
                    if outcome == 'WIN':
                        consec_losses = 0
                    else:
                        consec_losses += 1
                        if consec_losses >= 2:
                            lockout_until = i + lockout_h
                            consec_losses = 0
                    continue
                    
        if i < lockout_until or (i - last_exit_idx) < spacing:
            continue
            
        hr = hours[i]
        wday = weekdays[i]
        if wday == 'Sunday':
            continue
        if wday == 'Friday' and hr >= 12:
            continue
        if hr in [0, 4, 15, 16, 19]:
            continue
            
        slope_thresh = 0.08 * atr[i]
        h1_slope_bull = e20_slope[i] >= slope_thresh
        h1_slope_bear = -e20_slope[i] >= slope_thresh
        
        trend_bull = (c[i] > e50[i]) and (e20[i] > e50[i]) and h1_slope_bull and h4_bull[i]
        trend_bear = (c[i] < e50[i]) and (e20[i] < e50[i]) and h1_slope_bear and h4_bear[i]
        
        long_setup = trend_bull and (c[i] > don_h[i]) and (c[i-1] <= don_h[i-1])
        short_setup = trend_bear and (c[i] < don_l[i]) and (c[i-1] >= don_l[i-1])
        
        if hunting == 0:
            if long_setup:
                hunting = 1
                hunt_idx = i
                hunt_level = don_h[i]
                hunt_ob_l = l[i-1] if c[i-1] < o[i-1] else l[i]
                hunt_ob_h = h[i-1] if c[i-1] < o[i-1] else h[i]
                hunt_fib_50 = h[i] - 0.50 * (h[i] - hunt_ob_l)
                hunt_atr = atr[i]
            elif short_setup:
                hunting = -1
                hunt_idx = i
                hunt_level = don_l[i]
                hunt_ob_h = h[i-1] if c[i-1] > o[i-1] else h[i]
                hunt_ob_l = l[i-1] if c[i-1] > o[i-1] else l[i]
                hunt_fib_50 = l[i] + 0.50 * (hunt_ob_h - l[i])
                hunt_atr = atr[i]
        else:
            if (i - hunt_idx) > max_hunt:
                hunting = 0
            elif hunting == 1:
                retest = (l[i] <= hunt_level * 1.0005) or (l[i] <= e20[i]) or (l[i] <= hunt_fib_50) or (l[i] <= hunt_ob_h)
                rejection = (c[i] > o[i])
                rsi_ok = (rsi[i] <= 75.0)
                if retest and rejection and rsi_ok:
                    raw_sl = min(hunt_ob_l, l[i]) - (hunt_atr * sl_mult)
                    sl_pts = min(max((c[i] - raw_sl)/pip, min_sl), max_sl)
                    sl_dist = sl_pts * pip
                    
                    state = 1
                    hunting = 0
                    entry_price = c[i]
                    entry_idx = i
                    initial_sl_dist = sl_dist
                    sl_price = entry_price - sl_dist
                    tp_price = entry_price + (sl_dist * rr)
                    partial_taken = False
                    partial_r_banked = 0.0
            elif hunting == -1:
                retest = (h[i] >= hunt_level * 0.9995) or (h[i] >= e20[i]) or (h[i] >= hunt_fib_50) or (h[i] >= hunt_ob_l)
                rejection = (c[i] < o[i])
                rsi_ok = (rsi[i] >= 25.0)
                if retest and rejection and rsi_ok:
                    raw_sl = max(hunt_ob_h, h[i]) + (hunt_atr * sl_mult)
                    sl_pts = min(max((raw_sl - c[i])/pip, min_sl), max_sl)
                    sl_dist = sl_pts * pip
                    
                    state = -1
                    hunting = 0
                    entry_price = c[i]
                    entry_idx = i
                    initial_sl_dist = sl_dist
                    sl_price = entry_price + sl_dist
                    tp_price = entry_price - (sl_dist * rr)
                    partial_taken = False
                    partial_r_banked = 0.0
                    
    df_t = pd.DataFrame(trades)
    tot = len(df_t)
    wins = len(df_t[df_t['result'] == 'WIN'])
    wr = (wins / tot) * 100.0 if tot > 0 else 0
    net_r = df_t['realized_r'].sum()
    gw = df_t[df_t['realized_r'] > 0]['realized_r'].sum()
    gl = abs(df_t[df_t['realized_r'] < 0]['realized_r'].sum())
    pf = gw / (gl + 1e-9)
    m_grp = df_t.groupby('month_cohort')['realized_r'].sum()
    pos_m = len(m_grp[m_grp > 0])
    
    return {
        'donch': donch_len,
        'hunt': max_hunt,
        'lockout': lockout_h,
        'spacing': spacing,
        'trades': tot,
        'freq_wk': tot / 103.0,
        'win_rate': wr,
        'net_r': net_r,
        'pf': pf,
        'pos_m': pos_m
    }

if __name__ == '__main__':
    grid = [
        (8, 8, 24, 2),   # Baseline
        (8, 10, 24, 2),
        (8, 12, 24, 2),
        (8, 12, 12, 1),
        (6, 8, 24, 2),
        (6, 12, 12, 1),
        (10, 8, 24, 2),
        (10, 12, 12, 1),
        (8, 14, 12, 1)
    ]
    
    print(f"{'Donch':>5} | {'Hunt':>4} | {'Lockout':>7} | {'Spacing':>7} | {'Trades':>6} | {'Freq/Wk':>7} | {'Win Rate':>8} | {'Net R':>8} | {'PF':>5} | {'Pos Months':>10}")
    print("-" * 85)
    for g in grid:
        r = test_gold_params(*g)
        print(f"{r['donch']:>5} | {r['hunt']:>4} | {r['lockout']:>5}h | {r['spacing']:>7} | {r['trades']:>6} | {r['freq_wk']:>6.2f}/w | {r['win_rate']:>7.1f}% | {r['net_r']:>+7.2f}R | {r['pf']:>5.2f} | {r['pos_m']:>7}/24")
