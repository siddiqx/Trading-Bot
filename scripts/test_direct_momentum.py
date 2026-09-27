import pickle, math
import pandas as pd
import numpy as np

def test_direct_momentum():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
        
    df = all_data['XAUUSD'].copy()
    if df['time_dt'].dt.tz is not None:
        df['time_dt'] = df['time_dt'].dt.tz_localize(None)
        
    START_DATE = '2026-03-15'
    
    # We test:
    # Model 1: Current Tuned (8-bar Donchian, wait for 38.2% fib pullback, then enter)
    # Model 2: Fast Fib (23.6% shallow pullback - catches fast runners instantly)
    # Model 3: Direct Velocity Entry (If breakout candle has strong body >= 0.55 and range >= 1.25 ATR, enter at close without waiting for pullback)
    # Model 4: Hybrid (Enter 50% on direct breakout close, 50% on pullback)
    
    def simulate_variant(entry_mode='PULLBACK', fib=0.382, max_hunt=8):
        c_df = df.copy()
        
        c_df['e20'] = c_df['close'].ewm(span=20, adjust=False).mean()
        c_df['e50'] = c_df['close'].ewm(span=50, adjust=False).mean()
        c_df['e20_slope'] = c_df['e20'] - c_df['e20'].shift(2)
        
        tr = np.maximum(c_df['high'] - c_df['low'], np.maximum(np.abs(c_df['high'] - c_df['close'].shift(1)), np.abs(c_df['low'] - c_df['close'].shift(1))))
        c_df['atr'] = pd.Series(tr).rolling(14).mean().bfill()
        
        delta = c_df['close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        rs = gain.rolling(14).mean() / (loss.rolling(14).mean() + 1e-9)
        c_df['rsi'] = (100 - (100 / (1 + rs))).bfill()
        
        c_df['don_h'] = c_df['high'].shift(1).rolling(8).max()
        c_df['don_l'] = c_df['low'].shift(1).rolling(8).min()
        
        df_idx = c_df.set_index('time_dt')
        df_4h = df_idx.resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna().reset_index()
        df_4h['e20'] = df_4h['close'].ewm(span=20, adjust=False).mean()
        df_4h['e50'] = df_4h['close'].ewm(span=50, adjust=False).mean()
        df_4h['ema_bull'] = df_4h['e20'] > df_4h['e50']
        df_4h['ema_bear'] = df_4h['e20'] < df_4h['e50']
        
        c_df['h4_time'] = c_df['time_dt'].dt.floor('4h') - pd.Timedelta(hours=4)
        c_df['h4_bull'] = c_df['h4_time'].map(dict(zip(df_4h['time_dt'], df_4h['ema_bull']))).fillna(True)
        c_df['h4_bear'] = c_df['h4_time'].map(dict(zip(df_4h['time_dt'], df_4h['ema_bear']))).fillna(True)
        
        c = c_df['close'].values
        h = c_df['high'].values
        l = c_df['low'].values
        o = c_df['open'].values
        e20 = c_df['e20'].values
        e50 = c_df['e50'].values
        e20_slope = c_df['e20_slope'].values
        atr = c_df['atr'].values
        rsi = c_df['rsi'].values
        don_h = c_df['don_h'].values
        don_l = c_df['don_l'].values
        h4_bull = c_df['h4_bull'].values
        h4_bear = c_df['h4_bear'].values
        hours = c_df['time_dt'].dt.hour.values
        weekdays = c_df['time_dt'].dt.day_name().values
        times = c_df['time_dt'].values
        
        start_idx = c_df[c_df['time_dt'] >= START_DATE].index[0]
        
        trades = []
        state = 0
        entry_price, sl_price, tp_price, entry_idx = 0,0,0,0
        hunting = 0
        hunt_idx, hunt_level, hunt_ob_h, hunt_ob_l, hunt_fib, hunt_atr = 0,0,0,0,0,0
        lockout_until = 0
        consec_losses = 0
        last_exit_idx = -999
        
        rr = 1.75
        min_sl = 18.0
        max_sl = 25.0
        sl_buffer = 0.35
        
        for i in range(start_idx, len(c_df)):
            if state != 0:
                hold = i - entry_idx
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
                        trades.append({
                            'entry_time': times[entry_idx],
                            'exit_time': times[i],
                            'entry_dt': pd.to_datetime(times[entry_idx]),
                            'exit_dt': pd.to_datetime(times[i]),
                            'hold_bars': hold,
                            'result': exit_type,
                            'r': rr if exit_type == 'WIN' else -1.0,
                            'pnl': 50.0 * (rr if exit_type == 'WIN' else -1.0)
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

            if i < lockout_until or (i - last_exit_idx) < 1:
                continue
                
            hr = hours[i]
            wday = weekdays[i]
            is_fri_pm = (wday == 'Friday') and (hr >= 12)
            in_active_hours = (hr != 21) and not is_fri_pm
            if hr in [0, 4, 15, 16, 19]:
                in_active_hours = False
                
            slope_thresh = 0.10 * atr[i]
            h1_slope_bull = e20_slope[i] >= slope_thresh
            h1_slope_bear = -e20_slope[i] >= slope_thresh
            
            trend_bull = (c[i] > e50[i]) and (e20[i] > e50[i]) and h1_slope_bull and h4_bull[i]
            trend_bear = (c[i] < e50[i]) and (e20[i] < e50[i]) and h1_slope_bear and h4_bear[i]
            
            long_setup = trend_bull and (c[i] > don_h[i]) and (c[i-1] <= don_h[i-1]) and in_active_hours
            short_setup = trend_bear and (c[i] < don_l[i]) and (c[i-1] >= don_l[i-1]) and in_active_hours
            
            candle_rng = h[i] - l[i]
            body_bull = (c[i] - o[i]) / (candle_rng + 1e-9)
            body_bear = (o[i] - c[i]) / (candle_rng + 1e-9)
            
            if entry_mode == 'DIRECT_VELOCITY':
                # Direct entry on strong breakout candle close if body >= 0.50 and range >= 1.1 ATR
                if long_setup and body_bull >= 0.50 and candle_rng >= 1.10 * atr[i]:
                    raw_sl = l[i] - (atr[i] * sl_buffer)
                    calc_dist = abs(c[i] - raw_sl)
                    act_sl_dist = min(max(calc_dist, min_sl), max_sl)
                    state = 1
                    entry_price = c[i]
                    entry_idx = i
                    sl_price = c[i] - act_sl_dist
                    tp_price = c[i] + (act_sl_dist * rr)
                    continue
                elif short_setup and body_bear >= 0.50 and candle_rng >= 1.10 * atr[i]:
                    raw_sl = h[i] + (atr[i] * sl_buffer)
                    calc_dist = abs(raw_sl - c[i])
                    act_sl_dist = min(max(calc_dist, min_sl), max_sl)
                    state = -1
                    entry_price = c[i]
                    entry_idx = i
                    sl_price = c[i] + act_sl_dist
                    tp_price = c[i] - (act_sl_dist * rr)
                    continue

            if hunting == 0:
                if long_setup:
                    hunting = 1
                    hunt_idx = i
                    hunt_level = don_h[i]
                    hunt_ob_l = l[i-1] if c[i-1] < o[i-1] else l[i]
                    hunt_ob_h = h[i-1] if c[i-1] < o[i-1] else h[i]
                    hunt_fib = h[i] - fib * (h[i] - hunt_ob_l)
                    hunt_atr = atr[i]
                elif short_setup:
                    hunting = -1
                    hunt_idx = i
                    hunt_level = don_l[i]
                    hunt_ob_h = h[i-1] if c[i-1] > o[i-1] else h[i]
                    hunt_ob_l = l[i-1] if c[i-1] > o[i-1] else l[i]
                    hunt_fib = l[i] + fib * (hunt_ob_h - l[i])
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
                        if h[i] < tent_tp:
                            state = 1
                            hunting = 0
                            entry_price = c[i]
                            entry_idx = i
                            sl_price = tent_sl
                            tp_price = tent_tp
                        else:
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
                            hunting = 0
        return trades

    print("=" * 110)
    print("ENTRY MECHANIC VARIANT AUDIT (RECENT 6 MONTHS: 28 WEEKS)")
    print("=" * 110)
    
    variants = [
        ("1. Benchmark (38.2% Fib Pullback, Max Hunt 8)", 'PULLBACK', 0.382, 8),
        ("2. Ultra-Shallow Fib (23.6% Fib, Max Hunt 8)", 'PULLBACK', 0.236, 8),
        ("3. Fast Hunt Window (38.2% Fib, Max Hunt 4)", 'PULLBACK', 0.382, 4),
        ("4. Extended Hunt Window (38.2% Fib, Max Hunt 12)", 'PULLBACK', 0.382, 12),
        ("5. Direct Velocity Entry (Breakout Close + Body >= 0.50)", 'DIRECT_VELOCITY', 0.382, 8),
    ]
    
    rows = []
    for name, mode, fib_val, mh in variants:
        tr_list = simulate_variant(entry_mode=mode, fib=fib_val, max_hunt=mh)
        tdf = pd.DataFrame(tr_list)
        n = len(tdf)
        wins = (tdf['result'] == 'WIN').sum()
        wr = (wins / n * 100.0) if n > 0 else 0.0
        win_r = (tdf[tdf['result'] == 'WIN']['r']).sum()
        loss_r = abs((tdf[tdf['result'] == 'LOSS']['r']).sum())
        pf = win_r / loss_r if loss_r > 0 else 99.0
        net_prof = tdf['pnl'].sum()
        
        # Calculate days to +8% ($400)
        p1_days = []
        for s in range(0, max(1, n - 15)):
            cum = 0.0
            for k in range(s, n):
                cum += tdf.iloc[k]['pnl']
                if cum >= 400.0:
                    p1_days.append((tdf.iloc[k]['exit_dt'] - tdf.iloc[s]['entry_dt']).days)
                    break
        med_p1 = np.median(p1_days) if len(p1_days) > 0 else 999
        
        rows.append({
            'Strategy Variant': name,
            'Trades': n,
            'Freq/Wk': round(n / 28.0, 2),
            'Win Rate': f"{wr:.1f}%",
            'Profit Factor': f"{pf:.2f}",
            'Net Profit ($)': f"${net_prof:.2f}",
            'Phase 1 Days (Median)': f"{med_p1:.0f} days (~{med_p1/7:.1f} wks)"
        })
        
    print(pd.DataFrame(rows).to_string(index=False))

if __name__ == '__main__':
    test_direct_momentum()
