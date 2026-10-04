"""
High-Precision Pullback & Order Block Retest Engine (Recreating the >50% Win Rate Strategy)
Audits the exact institutional pullback + confirmation model on Gold (XAUUSD)
across 2 full years (24 separate monthly cohorts) to confirm how win rate reaches >= 50%
and delivers positive returns across monthly sets.
"""

import pickle
import math
import pandas as pd
import numpy as np

def run_precision_pullback_audit():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
        
    df = all_data['XAUUSD'].copy()
    if df['time_dt'].dt.tz is not None:
        df['time_dt'] = df['time_dt'].dt.tz_localize(None)
        
    df = df.sort_values('time_dt').reset_index(drop=True)
    
    # Parameters that achieved >50% WR
    donch_len = 8
    rr = 1.75
    min_sl = 15.0
    max_sl = 25.0
    sl_mult = 0.50
    fib_retrace = 0.382
    max_hunt = 8
    
    # Calculate indicators
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
    
    # 4H macro trend alignment
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
    dates = df['time_dt'].dt.strftime('%Y-%m').values
    
    # State tracking
    trades = []
    state = 0
    entry_price, sl_price, tp_price = 0.0, 0.0, 0.0
    entry_idx = 0
    hunting = 0
    hunt_level, hunt_ob_h, hunt_ob_l, hunt_fib_50, hunt_atr, hunt_idx = 0.0, 0.0, 0.0, 0.0, 0.0, 0
    lockout_until = 0
    consec_losses = 0
    last_exit_idx = -999
    
    start_idx = 100
    n = len(df)
    
    for i in range(start_idx, n):
        # 1. Manage active position
        if state != 0:
            hold = i - entry_idx
            if hold >= 1:
                exit_triggered = False
                exit_type = None
                exit_price = 0.0
                
                if state == 1:
                    # Long exit
                    if h[i] >= tp_price:
                        exit_triggered = True
                        exit_type = 'WIN'
                        exit_price = tp_price
                    elif l[i] <= sl_price:
                        exit_triggered = True
                        exit_type = 'LOSS'
                        exit_price = sl_price
                    elif hold >= 96: # 4 days max hold
                        exit_triggered = True
                        exit_price = c[i]
                        exit_type = 'WIN' if exit_price > entry_price else 'LOSS'
                elif state == -1:
                    # Short exit
                    if l[i] <= tp_price:
                        exit_triggered = True
                        exit_type = 'WIN'
                        exit_price = tp_price
                    elif h[i] >= sl_price:
                        exit_triggered = True
                        exit_type = 'LOSS'
                        exit_price = sl_price
                    elif hold >= 96:
                        exit_triggered = True
                        exit_price = c[i]
                        exit_type = 'WIN' if exit_price < entry_price else 'LOSS'
                        
                if exit_triggered:
                    sl_dist = abs(entry_price - sl_price)
                    price_diff = (exit_price - entry_price) if state == 1 else (entry_price - exit_price)
                    r_mult = price_diff / (sl_dist + 1e-9)
                    pips = price_diff * 10.0 # 0.10 per pip
                    
                    trades.append({
                        'entry_time': str(df['time_dt'].iloc[entry_idx]),
                        'exit_time': str(df['time_dt'].iloc[i]),
                        'month_cohort': df['time_dt'].iloc[entry_idx].strftime('%Y-%m'),
                        'type': 'LONG' if state == 1 else 'SHORT',
                        'entry': round(entry_price, 2),
                        'sl': round(sl_price, 2),
                        'tp': round(tp_price, 2),
                        'exit': round(exit_price, 2),
                        'result': exit_type,
                        'realized_r': round(r_mult, 2),
                        'realized_pips': round(pips, 1),
                        'hold_bars': hold
                    })
                    
                    state = 0
                    last_exit_idx = i
                    if exit_type == 'WIN':
                        consec_losses = 0
                    else:
                        consec_losses += 1
                        if consec_losses >= 2:
                            lockout_until = i + 36 # 36-hour circuit breaker
                            consec_losses = 0
                    continue
                    
        # Check circuit breaker and entry cooldown
        if i < lockout_until or (i - last_exit_idx) < 2:
            continue
            
        hr = hours[i]
        wday = weekdays[i]
        
        # Toxic Hours & Weekend Guard:
        # Exclude Sunday, Friday afternoon, and low-probability churn hours (0, 4, 15, 16, 19)
        if wday == 'Sunday':
            continue
        if (wday == 'Friday') and (hr >= 12):
            continue
        if hr in [0, 4, 15, 16, 19]:
            continue
            
        slope_thresh = 0.10 * atr[i]
        h1_slope_bull = e20_slope[i] >= slope_thresh
        h1_slope_bear = -e20_slope[i] >= slope_thresh
        
        trend_bull = (c[i] > e50[i]) and (e20[i] > e50[i]) and h1_slope_bull and h4_bull[i]
        trend_bear = (c[i] < e50[i]) and (e20[i] < e50[i]) and h1_slope_bear and h4_bear[i]
        
        long_setup = trend_bull and (c[i] > don_h[i]) and (c[i-1] <= don_h[i-1])
        short_setup = trend_bear and (c[i] < don_l[i]) and (c[i-1] >= don_l[i-1])
        
        # Pullback Hunting State Machine
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
            # Hunt timeout after 8 bars
            if (i - hunt_idx) > max_hunt:
                hunting = 0
            elif hunting == 1:
                # LONG RETEST & REJECTION
                retest = (l[i] <= hunt_level * 1.0005) or (l[i] <= e20[i]) or (l[i] <= hunt_fib_50) or (l[i] <= hunt_ob_h)
                rejection = (c[i] > o[i]) # Confirmed bullish bounce off support
                rsi_ok = (rsi[i] <= 75.0)
                if retest and rejection and rsi_ok:
                    raw_sl = min(hunt_ob_l, l[i]) - (hunt_atr * sl_mult)
                    sl_dist = min(max(c[i] - raw_sl, min_sl), max_sl)
                    cand_entry = c[i]
                    cand_sl = cand_entry - sl_dist
                    cand_tp = cand_entry + (sl_dist * rr)
                    
                    state = 1
                    hunting = 0
                    entry_price = cand_entry
                    entry_idx = i
                    sl_price = cand_sl
                    tp_price = cand_tp
            elif hunting == -1:
                # SHORT RETEST & REJECTION
                retest = (h[i] >= hunt_level * 0.9995) or (h[i] >= e20[i]) or (h[i] >= hunt_fib_50) or (h[i] >= hunt_ob_l)
                rejection = (c[i] < o[i]) # Confirmed bearish bounce off resistance
                rsi_ok = (rsi[i] >= 25.0)
                if retest and rejection and rsi_ok:
                    raw_sl = max(hunt_ob_h, h[i]) + (hunt_atr * sl_mult)
                    sl_dist = min(max(raw_sl - c[i], min_sl), max_sl)
                    cand_entry = c[i]
                    cand_sl = cand_entry + sl_dist
                    cand_tp = cand_entry - (sl_dist * rr)
                    
                    state = -1
                    hunting = 0
                    entry_price = cand_entry
                    entry_idx = i
                    sl_price = cand_sl
                    tp_price = cand_tp

    df_res = pd.DataFrame(trades)
    print("\n=========================================================================================")
    print("GOLD (XAUUSD) 2-YEAR MONTHLY AUDIT: PRECISION PULLBACK & CONFIRMATION ENGINE")
    print("=========================================================================================")
    print(f"Total Trades: {len(df_res)}")
    wins = len(df_res[df_res['result'] == 'WIN'])
    losses = len(df_res[df_res['result'] == 'LOSS'])
    wr = (wins / len(df_res)) * 100.0
    net_r = df_res['realized_r'].sum()
    net_pips = df_res['realized_pips'].sum()
    g_win_r = df_res[df_res['realized_r'] > 0]['realized_r'].sum()
    g_loss_r = abs(df_res[df_res['realized_r'] < 0]['realized_r'].sum())
    pf = g_win_r / g_loss_r if g_loss_r > 0 else 99.0
    
    print(f"Wins: {wins} | Losses: {losses} | WIN RATE: {wr:.1f}%")
    print(f"NET REALIZED R: {net_r:+6.2f} R")
    print(f"NET REALIZED PIPS: {net_pips:+8.1f} pips")
    print(f"PROFIT FACTOR: {pf:.2f}")
    
    # Month by month breakdown
    print("\n--- MONTH-BY-MONTH BREAKDOWN (24 MONTHS) ---")
    monthly = []
    for m in sorted(df_res['month_cohort'].unique()):
        sub = df_res[df_res['month_cohort'] == m]
        m_t = len(sub)
        m_w = len(sub[sub['result'] == 'WIN'])
        m_l = len(sub[sub['result'] == 'LOSS'])
        m_wr = (m_w / m_t) * 100.0
        m_r = sub['realized_r'].sum()
        m_pips = sub['realized_pips'].sum()
        gw = sub[sub['realized_r'] > 0]['realized_r'].sum()
        gl = abs(sub[sub['realized_r'] < 0]['realized_r'].sum())
        m_pf = gw / gl if gl > 0 else 99.0
        monthly.append({
            'Month': m,
            'Trades': m_t,
            'Wins': m_w,
            'Losses': m_l,
            'WinRate%': round(m_wr, 1),
            'Net_R': round(m_r, 2),
            'Net_Pips': round(m_pips, 1),
            'ProfitFactor': round(m_pf, 2)
        })
    df_m = pd.DataFrame(monthly)
    print(df_m.to_string(index=False))

if __name__ == '__main__':
    run_precision_pullback_audit()
