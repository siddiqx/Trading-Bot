import pickle, math
import pandas as pd
import numpy as np

def test_gold_session_orb():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
        
    df = all_data['XAUUSD'].copy()
    if df['time_dt'].dt.tz is not None:
        df['time_dt'] = df['time_dt'].dt.tz_localize(None)
        
    START_DATE = '2026-03-15'
    
    # 4H macro trend
    df_idx = df.set_index('time_dt')
    df_4h = df_idx.resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna().reset_index()
    df_4h['e20'] = df_4h['close'].ewm(span=20, adjust=False).mean()
    df_4h['e50'] = df_4h['close'].ewm(span=50, adjust=False).mean()
    df_4h['ema_bull'] = df_4h['e20'] > df_4h['e50']
    df_4h['ema_bear'] = df_4h['e20'] < df_4h['e50']
    
    df['h4_time'] = df['time_dt'].dt.floor('4h') - pd.Timedelta(hours=4)
    df['h4_bull'] = df['h4_time'].map(dict(zip(df_4h['time_dt'], df_4h['ema_bull']))).fillna(True)
    df['h4_bear'] = df['h4_time'].map(dict(zip(df_4h['time_dt'], df_4h['ema_bear']))).fillna(True)
    
    # 1H indicators
    df['e20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['e50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['e20_slope'] = df['e20'] - df['e20'].shift(2)
    
    tr = np.maximum(df['high'] - df['low'], np.maximum(np.abs(df['high'] - df['close'].shift(1)), np.abs(df['low'] - df['close'].shift(1))))
    df['atr'] = pd.Series(tr).rolling(14).mean().bfill()
    
    df['don_h10'] = df['high'].shift(1).rolling(10).max()
    df['don_l10'] = df['low'].shift(1).rolling(10).min()
    
    df['hour'] = df['time_dt'].dt.hour
    df['wday'] = df['time_dt'].dt.day_name()
    
    c = df['close'].values
    h = df['high'].values
    l = df['low'].values
    o = df['open'].values
    e20 = df['e20'].values
    e50 = df['e50'].values
    e20_slope = df['e20_slope'].values
    atr = df['atr'].values
    don_h = df['don_h10'].values
    don_l = df['don_l10'].values
    h4_bull = df['h4_bull'].values
    h4_bear = df['h4_bear'].values
    hours = df['hour'].values
    weekdays = df['wday'].values
    times = df['time_dt'].values
    
    # Session Ranges:
    # Asian Range: 00:00 to 06:00 UTC (High/Low of Asian session)
    # London Range: 07:00 to 11:00 UTC
    # Breakout of Asian High/Low during London (07:00 - 11:00 UTC) with 4H Trend Confluence!
    # Breakout of London High/Low during New York (12:00 - 16:00 UTC) with 4H Trend Confluence!
    
    # Track Asian & London extremes
    asian_high = np.zeros(len(df))
    asian_low = np.zeros(len(df))
    london_high = np.zeros(len(df))
    london_low = np.zeros(len(df))
    
    cur_asian_h = 0.0
    cur_asian_l = 99999.0
    cur_london_h = 0.0
    cur_london_l = 99999.0
    cur_day = None
    
    for i in range(len(df)):
        dt = pd.to_datetime(times[i])
        d = dt.date()
        hr = hours[i]
        
        if d != cur_day:
            cur_day = d
            cur_asian_h = 0.0
            cur_asian_l = 99999.0
            cur_london_h = 0.0
            cur_london_l = 99999.0
            
        if hr >= 0 and hr <= 6:
            cur_asian_h = max(cur_asian_h, h[i])
            cur_asian_l = min(cur_asian_l, l[i])
            
        if hr >= 7 and hr <= 11:
            cur_london_h = max(cur_london_h, h[i])
            cur_london_l = min(cur_london_l, l[i])
            
        asian_high[i] = cur_asian_h
        asian_low[i] = cur_asian_l
        london_high[i] = cur_london_h
        london_low[i] = cur_london_l
        
    start_idx = df[df['time_dt'] >= START_DATE].index[0]
    
    trades = []
    state = 0
    entry_price, sl_price, tp_price, entry_idx = 0,0,0,0
    last_exit_idx = -999
    lockout_until = 0
    consec_losses = 0
    
    for i in range(start_idx, len(df)):
        if state != 0:
            hold = i - entry_idx
            if hold >= 1:
                exit_trig, exit_type, exit_price = False, None, 0.0
                if state == 1:
                    if h[i] >= tp_price and l[i] <= sl_price: exit_trig, exit_type, exit_price = True, 'LOSS', sl_price
                    elif h[i] >= tp_price: exit_trig, exit_type, exit_price = True, 'WIN', tp_price
                    elif l[i] <= sl_price: exit_trig, exit_type, exit_price = True, 'LOSS', sl_price
                    elif hold >= 48: exit_trig, exit_price, exit_type = True, c[i], ('WIN' if c[i]>entry_price else 'LOSS')
                elif state == -1:
                    if l[i] <= tp_price and h[i] >= sl_price: exit_trig, exit_type, exit_price = True, 'LOSS', sl_price
                    elif l[i] <= tp_price: exit_trig, exit_type, exit_price = True, 'WIN', tp_price
                    elif h[i] >= sl_price: exit_trig, exit_type, exit_price = True, 'LOSS', sl_price
                    elif hold >= 48: exit_trig, exit_price, exit_type = True, c[i], ('WIN' if c[i]<entry_price else 'LOSS')
                if exit_trig:
                    sl_d = abs(entry_price - sl_price)
                    p_diff = (exit_price - entry_price) * (1.0 if state==1 else -1.0)
                    trades.append({'res': exit_type, 'sl_dist': sl_d, 'p_diff': p_diff})
                    state = 0
                    last_exit_idx = i
                    if exit_type == 'WIN': consec_losses = 0
                    else:
                        consec_losses += 1
                        if consec_losses >= 2: lockout_until = i + 24; consec_losses = 0
                    continue
        if i < lockout_until or (i - last_exit_idx) < 1: continue
        hr = hours[i]
        wday = weekdays[i]
        if hr == 21 or (wday == 'Friday' and hr >= 12): continue
        
        # Check Breakouts:
        # 1. 10-bar Donchian Breakout
        # 2. London Breakout of Asian High/Low (between 07:00 and 11:00 UTC)
        # 3. NY Breakout of London High/Low (between 12:00 and 16:00 UTC)
        
        trend_bull = (c[i] > e50[i]) and (e20[i] > e50[i]) and h4_bull[i] and (e20_slope[i] >= 0.05 * atr[i])
        trend_bear = (c[i] < e50[i]) and (e20[i] < e50[i]) and h4_bear[i] and (-e20_slope[i] >= 0.05 * atr[i])
        
        # Donchian Break
        don_bull = (c[i] > don_h[i]) and (c[i-1] <= don_h[i-1]) and trend_bull
        don_bear = (c[i] < don_l[i]) and (c[i-1] >= don_l[i-1]) and trend_bear
        
        # Asian Break in London
        asian_bull = (hr >= 7 and hr <= 10) and (c[i] > asian_high[i-1]) and (c[i-1] <= asian_high[i-1]) and trend_bull
        asian_bear = (hr >= 7 and hr <= 10) and (c[i] < asian_low[i-1]) and (c[i-1] >= asian_low[i-1]) and trend_bear
        
        # London Break in NY
        ny_bull = (hr >= 12 and hr <= 15) and (c[i] > london_high[i-1]) and (c[i-1] <= london_high[i-1]) and trend_bull
        ny_bear = (hr >= 12 and hr <= 15) and (c[i] < london_low[i-1]) and (c[i-1] >= london_low[i-1]) and trend_bear
        
        trigger_long = don_bull or asian_bull or ny_bull
        trigger_short = don_bear or asian_bear or ny_bear
        
        if trigger_long:
            sl_dist = min(max(c[i] - (l[i] - 0.25 * atr[i]), 15.0), 25.0)
            tent_sl = c[i] - sl_dist
            tent_tp = c[i] + sl_dist * 1.75
            if h[i] < tent_tp:
                state, entry_price, sl_price, tp_price, entry_idx = 1, c[i], tent_sl, tent_tp, i
        elif trigger_short:
            sl_dist = min(max((h[i] + 0.25 * atr[i]) - c[i], 15.0), 25.0)
            tent_sl = c[i] + sl_dist
            tent_tp = c[i] - sl_dist * 1.75
            if l[i] > tent_tp:
                state, entry_price, sl_price, tp_price, entry_idx = -1, c[i], tent_sl, tent_tp, i
                
    # Account performance
    bal = 5000.0
    pnl_list = []
    r_list = []
    
    for tr in trades:
        sl_d = tr['sl_dist']
        lots = max(0.01, round((bal * 0.01) / (sl_d * 100.0), 2))
        actual_risk = lots * 100.0 * sl_d
        gross = lots * 100.0 * tr['p_diff']
        costs = lots * 100.0 * 0.36
        net = gross - costs
        r_val = net / actual_risk if actual_risk > 0 else 0
        bal += net
        pnl_list.append(net)
        r_list.append(r_val)
        
    n_tr = len(trades)
    wins = sum(1 for p in pnl_list if p > 0)
    wr = (wins / n_tr * 100.0) if n_tr > 0 else 0
    w_sum = sum(p for p in pnl_list if p > 0)
    l_sum = abs(sum(p for p in pnl_list if p < 0))
    pf = (w_sum / l_sum) if l_sum > 0 else 99.0
    
    print("="*80)
    print("GOLD MULTI-SESSION EXPANSION ENGINE (DONCHIAN + LONDON ORB + NY ORB)")
    print("="*80)
    print(f"Total Trades (28 Weeks): {n_tr}")
    print(f"Average Frequency:        {n_tr / 28.0:.2f} trades / week")
    print(f"Win Rate:                 {wr:.1f}% ({wins}W / {n_tr - wins}L)")
    print(f"Profit Factor:            {pf:.2f}")
    print(f"Net Profit on $5,000:     ${bal - 5000.0:+,.2f} ({(bal-5000)/5000*100:+.2f}%)")
    print(f"Net R:                    {sum(r_list):+.2f} R")

if __name__ == '__main__':
    test_gold_session_orb()
