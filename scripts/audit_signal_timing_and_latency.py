import pickle, math
import pandas as pd
import numpy as np

def audit_signal_timing():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
        
    df = all_data['XAUUSD'].copy()
    if df['time_dt'].dt.tz is not None:
        df['time_dt'] = df['time_dt'].dt.tz_localize(None)
        
    START_DATE = '2024-10-01'
    
    # Run the exact tuned Gold strategy
    donch_len = 8
    cooldown = 1
    max_hunt = 8
    fib_retrace = 0.382
    sl_buffer = 0.35
    min_sl = 18.0
    max_sl = 25.0
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
    
    # 4H macro trend using strictly closed 4H candles
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
    times = df['time_dt'].values
    
    start_idx = df[df['time_dt'] >= START_DATE].index[0]
    
    trades = []
    state = 0
    entry_price, sl_price, tp_price, entry_idx = 0,0,0,0
    hunting = 0
    hunt_idx, hunt_level, hunt_ob_h, hunt_ob_l, hunt_fib, hunt_atr = 0,0,0,0,0,0
    last_exit_idx = -999
    lockout_until = 0
    consec_losses = 0
    
    same_bar_exits = 0
    
    for i in range(start_idx, len(df)):
        if state != 0:
            hold = i - entry_idx
            # EXIT CHECK ONLY ON FUTURE SUBSEQUENT BARS (hold >= 1)
            if hold >= 1:
                sl_dist = abs(entry_price - sl_price)
                exit_trig = False
                exit_type = None
                exit_price = 0.0
                
                if state == 1:
                    if h[i] >= tp_price and l[i] <= sl_price:
                        exit_trig = True
                        exit_type = 'LOSS'
                        exit_price = sl_price
                    elif h[i] >= tp_price:
                        exit_trig = True
                        exit_type = 'WIN'
                        exit_price = tp_price
                    elif l[i] <= sl_price:
                        exit_trig = True
                        exit_type = 'LOSS'
                        exit_price = sl_price
                    elif hold >= 160:
                        exit_trig = True
                        exit_price = c[i]
                        exit_type = 'WIN' if exit_price > entry_price else 'LOSS'
                elif state == -1:
                    if l[i] <= tp_price and h[i] >= sl_price:
                        exit_trig = True
                        exit_type = 'LOSS'
                        exit_price = sl_price
                    elif l[i] <= tp_price:
                        exit_trig = True
                        exit_type = 'WIN'
                        exit_price = tp_price
                    elif h[i] >= sl_price:
                        exit_trig = True
                        exit_type = 'LOSS'
                        exit_price = sl_price
                    elif hold >= 160:
                        exit_trig = True
                        exit_price = c[i]
                        exit_type = 'WIN' if exit_price < entry_price else 'LOSS'
                        
                if exit_trig:
                    dir_m = 1.0 if state == 1 else -1.0
                    
                    # Track Maximum Favorable Excursion (MFE) and Maximum Adverse Excursion (MAE)
                    sub_h = h[entry_idx+1:i+1]
                    sub_l = l[entry_idx+1:i+1]
                    if state == 1:
                        max_favorable = np.max(sub_h) - entry_price
                        max_adverse = entry_price - np.min(sub_l)
                    else:
                        max_favorable = entry_price - np.min(sub_l)
                        max_adverse = np.max(sub_h) - entry_price
                        
                    trades.append({
                        'entry_time': times[entry_idx],
                        'exit_time': times[i],
                        'entry_bar': entry_idx,
                        'exit_bar': i,
                        'hold_bars': hold,
                        'direction': 'LONG' if state == 1 else 'SHORT',
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'sl_price': sl_price,
                        'tp_price': tp_price,
                        'sl_dist': sl_dist,
                        'result': exit_type,
                        'r': rr if exit_type == 'WIN' else -1.0,
                        'pnl': 50.0 * (rr if exit_type == 'WIN' else -1.0),
                        'mfe_r': max_favorable / sl_dist,
                        'mae_r': max_adverse / sl_dist
                    })
                    state = 0
                    last_exit_idx = i
                    if exit_type == 'WIN':
                        consec_losses = 0
                    elif exit_type == 'LOSS':
                        consec_losses += 1
                        if consec_losses >= 2:
                            lockout_until = i + 48
                            consec_losses = 0
                    continue

        if i < lockout_until or (i - last_exit_idx) < cooldown:
            continue
            
        hr = hours[i]
        wday = weekdays[i]
        is_fri_pm = (wday == 'Friday') and (hr >= 12)
        in_active_hours = (hr != 21) and not is_fri_pm
        
        # Gold manipulation hours filter
        if hr in [0, 4, 15, 16, 19]:
            in_active_hours = False
            
        slope_thresh = 0.10 * atr[i]
        h1_slope_bull = e20_slope[i] >= slope_thresh
        h1_slope_bear = -e20_slope[i] >= slope_thresh
        
        trend_bull = (c[i] > e50[i]) and (e20[i] > e50[i]) and h1_slope_bull and h4_bull[i]
        trend_bear = (c[i] < e50[i]) and (e20[i] < e50[i]) and h1_slope_bear and h4_bear[i]
        
        long_setup = trend_bull and (c[i] > don_h[i]) and (c[i-1] <= don_h[i-1]) and in_active_hours
        short_setup = trend_bear and (c[i] < don_l[i]) and (c[i-1] >= don_l[i-1]) and in_active_hours
        
        if hunting == 0:
            if long_setup:
                hunting = 1
                hunt_idx = i
                hunt_level = don_h[i]
                hunt_ob_l = l[i-1] if c[i-1] < o[i-1] else l[i]
                hunt_ob_h = h[i-1] if c[i-1] < o[i-1] else h[i]
                hunt_fib = h[i] - fib_retrace * (h[i] - hunt_ob_l)
                hunt_atr = atr[i]
            elif short_setup:
                hunting = -1
                hunt_idx = i
                hunt_level = don_l[i]
                hunt_ob_h = h[i-1] if c[i-1] > o[i-1] else h[i]
                hunt_ob_l = l[i-1] if c[i-1] > o[i-1] else l[i]
                hunt_fib = l[i] + fib_retrace * (hunt_ob_h - l[i])
                hunt_atr = atr[i]
        else:
            if (i - hunt_idx) > max_hunt:
                hunting = 0
            elif hunting == 1:
                retrace = (l[i] <= hunt_fib) or (l[i] <= hunt_ob_h) or (l[i] <= hunt_level * 1.0005) or (l[i] <= e20[i])
                rejection = c[i] > o[i]
                rsi_ok = rsi[i] <= 80.0
                if retrace and rejection and rsi_ok and in_active_hours:
                    raw_sl = hunt_ob_l - (hunt_atr * sl_buffer)
                    calc_dist = abs(c[i] - raw_sl)
                    act_sl_dist = min(max(calc_dist, min_sl), max_sl)
                    tent_sl = c[i] - act_sl_dist
                    tent_tp = c[i] + (act_sl_dist * rr)
                    # VERIFY CANDLE WAS NOT EXHAUSTED BEFORE CLOSE
                    if h[i] < tent_tp:
                        state = 1
                        hunting = 0
                        entry_price = c[i]
                        entry_idx = i
                        sl_price = tent_sl
                        tp_price = tent_tp
                    else:
                        same_bar_exits += 1
                        hunting = 0
            elif hunting == -1:
                retrace = (h[i] >= hunt_fib) or (h[i] >= hunt_ob_l) or (h[i] >= hunt_level * 0.9995) or (h[i] >= e20[i])
                rejection = c[i] < o[i]
                rsi_ok = rsi[i] >= 20.0
                if retrace and rejection and rsi_ok and in_active_hours:
                    raw_sl = hunt_ob_h + (hunt_atr * sl_buffer)
                    calc_dist = abs(raw_sl - c[i])
                    act_sl_dist = min(max(calc_dist, min_sl), max_sl)
                    tent_sl = c[i] + act_sl_dist
                    tent_tp = c[i] - (act_sl_dist * rr)
                    if l[i] > tent_tp:
                        state = -1
                        hunting = 0
                        entry_price = c[i]
                        entry_idx = i
                        sl_price = tent_sl
                        tp_price = tent_tp
                    else:
                        same_bar_exits += 1
                        hunting = 0

    tdf = pd.DataFrame(trades)
    print("=" * 80)
    print("AUDIT: SIGNAL TEMPORAL CAUSALITY & EXECUTION LATENCY VERIFICATION")
    print("=" * 80)
    print(f"Total Trades Evaluated:             {len(tdf)}")
    print(f"Same-Bar Exits (Lookahead Bias):    0 (100% of trades concluded on subsequent bars)")
    print(f"Same-Bar Exhaustion Traps Blocked:  {same_bar_exits} signals correctly rejected (prevented after-the-fact labels)")
    print(f"Minimum Holding Period:             {tdf['hold_bars'].min()} bar ({tdf['hold_bars'].min()} hour)")
    print(f"Median Holding Period:              {tdf['hold_bars'].median():.1f} bars ({tdf['hold_bars'].median():.1f} hours)")
    print(f"Average Holding Period:             {tdf['hold_bars'].mean():.1f} bars ({tdf['hold_bars'].mean():.1f} hours)")
    print(f"Maximum Holding Period:             {tdf['hold_bars'].max()} bars ({tdf['hold_bars'].max()} hours)")

    print("\n" + "=" * 80)
    print("HOLDING TIME DISTRIBUTION (HOURS TO HIT TP OR SL AFTER ENTRY)")
    print("=" * 80)
    bins = [0, 1, 2, 4, 8, 16, 32, 64, 160]
    tdf['hold_bin'] = pd.cut(tdf['hold_bars'], bins=bins)
    hold_dist = tdf.groupby('hold_bin', observed=False).agg(
        trades=('result', 'count'),
        wins=('result', lambda x: (x == 'WIN').sum()),
        losses=('result', lambda x: (x == 'LOSS').sum()),
    )
    hold_dist['win_rate'] = (hold_dist['wins'] / hold_dist['trades'] * 100).round(1)
    print(hold_dist.to_string())

    print("\n" + "=" * 80)
    print("SAMPLE AUDIT: RECENT 10 TRADES CHRONOLOGICAL TRACE")
    print("=" * 80)
    sample = tdf.tail(10)[['entry_time', 'exit_time', 'direction', 'entry_price', 'exit_price', 'hold_bars', 'result', 'mfe_r', 'mae_r']]
    print(sample.to_string(index=False))

if __name__ == '__main__':
    audit_signal_timing()
