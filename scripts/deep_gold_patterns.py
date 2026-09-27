import pickle, math
import pandas as pd
import numpy as np

def analyze_patterns():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
        
    df_raw = all_data['XAUUSD'].copy()
    if df_raw['time_dt'].dt.tz is not None:
        df_raw['time_dt'] = df_raw['time_dt'].dt.tz_localize(None)
        
    START_2Y = '2024-10-01'
    
    # Run full simulation and save every trade record with detailed metadata
    def get_trades(donch_len=12, cooldown_bars=2, max_hunt=8, fib_retrace=0.382, rr=1.75, min_sl=18.0, max_sl=25.0):
        df = df_raw.copy()
        
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
        times = df['time_dt'].values
        
        trades = []
        state = 0
        entry_price, sl_price, tp_price = 0, 0, 0
        entry_idx = 0
        hunting = 0
        hunt_level, hunt_ob_h, hunt_ob_l, hunt_fib, hunt_atr, hunt_idx = 0,0,0,0,0,0
        lockout_until = 0
        consec_losses = 0
        last_exit_idx = -999
        
        start_idx = df[df['time_dt'] >= START_2Y].index[0]
        
        for i in range(start_idx, len(df)):
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
                        dir_m = 1.0 if state == 1 else -1.0
                        p_diff = (exit_price - entry_price) * dir_m
                        r_res = rr if exit_type == 'WIN' else -1.0
                        trades.append({
                            'entry_time': times[entry_idx],
                            'exit_time': times[i],
                            'entry_hour': hours[entry_idx],
                            'entry_wday': weekdays[entry_idx],
                            'direction': 'LONG' if state == 1 else 'SHORT',
                            'result': exit_type,
                            'entry_price': entry_price,
                            'exit_price': exit_price,
                            'sl_dist': sl_dist,
                            'r': r_res,
                            'pnl': 50.0 * r_res
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
                        
            if i < lockout_until or (i - last_exit_idx) < cooldown_bars:
                continue
                
            hr = hours[i]
            wday = weekdays[i]
            is_fri_pm = (wday == 'Friday') and (hr >= 12)
            in_active_hours = (hr != 21) and not is_fri_pm
            
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
                        raw_sl = hunt_ob_l - (hunt_atr * 0.50)
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
                        raw_sl = hunt_ob_h + (hunt_atr * 0.50)
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

        return pd.DataFrame(trades)

    tdf = get_trades()
    print("=" * 80)
    print("GOLD TRADE PERFORMANCE BY ENTRY HOUR (UTC)")
    print("=" * 80)
    hour_stats = tdf.groupby('entry_hour').agg(
        trades=('result', 'count'),
        wins=('result', lambda x: (x == 'WIN').sum()),
        losses=('result', lambda x: (x == 'LOSS').sum()),
        net_r=('r', 'sum'),
        net_pnl=('pnl', 'sum')
    )
    hour_stats['win_rate'] = (hour_stats['wins'] / hour_stats['trades'] * 100).round(1)
    hour_stats['profit_factor'] = (hour_stats['wins'] * 1.75 / (hour_stats['losses'] + 1e-9)).round(2)
    print(hour_stats[['trades', 'wins', 'losses', 'win_rate', 'profit_factor', 'net_r', 'net_pnl']].to_string())

    print("\n" + "=" * 80)
    print("GOLD TRADE PERFORMANCE BY DAY OF WEEK")
    print("=" * 80)
    wday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    wday_stats = tdf.groupby('entry_wday').agg(
        trades=('result', 'count'),
        wins=('result', lambda x: (x == 'WIN').sum()),
        losses=('result', lambda x: (x == 'LOSS').sum()),
        net_r=('r', 'sum'),
        net_pnl=('pnl', 'sum')
    ).reindex(wday_order)
    wday_stats['win_rate'] = (wday_stats['wins'] / wday_stats['trades'] * 100).round(1)
    wday_stats['profit_factor'] = (wday_stats['wins'] * 1.75 / (wday_stats['losses'] + 1e-9)).round(2)
    print(wday_stats[['trades', 'wins', 'losses', 'win_rate', 'profit_factor', 'net_r', 'net_pnl']].to_string())

if __name__ == '__main__':
    analyze_patterns()
