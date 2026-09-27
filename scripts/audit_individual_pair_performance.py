import pickle, math
import pandas as pd
import numpy as np

def run_per_pair_audit():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
        
    pairs = ['XAUUSD', 'USDCAD', 'USDCHF', 'USDJPY', 'AUDUSD', 'EURUSD', 'GBPUSD', 'NZDUSD']
    
    def simulate_pair(pair, start_date, weeks):
        df = all_data[pair].copy()
        if df['time_dt'].dt.tz is not None:
            df['time_dt'] = df['time_dt'].dt.tz_localize(None)
            
        is_gold = 'XAU' in pair
        
        # Gold uses tuned parameters; all other pairs use standard 20-bar baseline
        donch_len = 8 if is_gold else 20
        cooldown = 1 if is_gold else 3
        max_hunt = 8
        fib_retrace = 0.382 if is_gold else 0.500
        sl_buffer = 0.35 if is_gold else 0.50
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
        
        pip_mult = 1.0 if is_gold else (100.0 if 'JPY' in pair else 10000.0)
        start_idx = df[df['time_dt'] >= start_date].index[0]
        
        trades = []
        state = 0
        entry_price, sl_price, tp_price, entry_idx = 0,0,0,0
        hunting = 0
        hunt_idx, hunt_level, hunt_ob_h, hunt_ob_l, hunt_fib, hunt_atr = 0,0,0,0,0,0
        lockout_until = 0
        consec_losses = 0
        last_exit_idx = -999
        
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
                            'result': exit_type,
                            'entry_price': entry_price,
                            'exit_price': exit_price,
                            'sl_dist': sl_dist,
                            'r': r_res,
                            'pnl': 50.0 * r_res # 1% of $5,000
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
            
            if is_gold and hr in [0, 4, 15, 16, 19]:
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
                        calc_pips = calc_dist * pip_mult
                        act_pips = min(max(calc_pips, min_sl), max_sl)
                        act_dist = act_pips / pip_mult
                        tent_sl = c[i] - act_dist
                        tent_tp = c[i] + (act_dist * rr)
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
                        calc_pips = calc_dist * pip_mult
                        act_pips = min(max(calc_pips, min_sl), max_sl)
                        act_dist = act_pips / pip_mult
                        tent_sl = c[i] + act_dist
                        tent_tp = c[i] - (act_dist * rr)
                        if l[i] > tent_tp:
                            state = -1
                            hunting = 0
                            entry_price = c[i]
                            entry_idx = i
                            sl_price = tent_sl
                            tp_price = tent_tp
                        else:
                            hunting = 0

        if len(trades) == 0:
            return {'Pair': pair, 'Trades': 0, 'Trades/Wk': 0, 'Win Rate': '0.0%', 'Profit Factor': '0.00', 'Net Profit': '$0.00', 'Return': '+0.0%', 'Net R': '+0.00 R', 'Max Daily DD': '0.0%', 'Max Total DD': '0.0%', 'Whitelist Status': 'Excluded'}
            
        tdf = pd.DataFrame(trades)
        tdf['exit_dt'] = pd.to_datetime(tdf['exit_time'])
        tdf['exit_date'] = tdf['exit_dt'].dt.date
        
        EQUITY = 5000.0
        n_trades = len(tdf)
        wins = len(tdf[tdf['result'] == 'WIN'])
        losses = len(tdf[tdf['result'] == 'LOSS'])
        wr = (wins / n_trades) * 100.0 if n_trades > 0 else 0.0
        
        win_sum = tdf[tdf['pnl'] > 0]['pnl'].sum()
        loss_sum = abs(tdf[tdf['pnl'] < 0]['pnl'].sum())
        pf = (win_sum / loss_sum) if loss_sum > 0 else 99.0
        
        net_prof = tdf['pnl'].sum()
        ret_pct = (net_prof / EQUITY) * 100.0
        net_r = tdf['r'].sum()
        
        daily_pnl = tdf.groupby('exit_date')['pnl'].sum()
        max_daily_loss = abs(daily_pnl.min()) if len(daily_pnl) > 0 and daily_pnl.min() < 0 else 0.0
        max_daily_dd = (max_daily_loss / EQUITY) * 100.0
        
        cum = tdf['pnl'].cumsum()
        peak = cum.cummax()
        dd = peak - cum
        max_dd = (dd.max() / EQUITY) * 100.0
        
        freq_wk = n_trades / weeks
        
        whitelisted = pair in ['XAUUSD', 'USDCAD', 'USDCHF', 'USDJPY', 'AUDUSD']
        
        return {
            'Pair': pair,
            'Role': 'Primary Engine (Tuned)' if pair == 'XAUUSD' else ('Whitelisted Momentum' if whitelisted else 'Excluded Chop Pair'),
            'Trades': n_trades,
            'Trades/Wk': round(freq_wk, 2),
            'Win Rate': f"{wr:.1f}%",
            'Profit Factor': f"{pf:.2f}",
            'Net Profit ($)': f"${net_prof:.2f}",
            'Return (%)': f"{ret_pct:+.1f}%",
            'Net R': f"{net_r:+.2f} R",
            'Max Daily DD': f"{max_daily_dd:.2f}%",
            'Max Total DD': f"{max_dd:.2f}%",
            'Verdict': 'INSTITUTIONAL EDGE' if pf >= 1.25 and wr >= 40.0 else ('PROFITABLE (CONSOLIDATING)' if pf >= 1.0 else 'NEGATIVE EXPECTANCY')
        }

    print("=" * 125)
    print("INDIVIDUAL PAIR PERFORMANCE AUDIT: RECENT 6 MONTHS (28 WEEKS: MAR 15 - SEP 25, 2026)")
    print("=" * 125)
    rows_6m = [simulate_pair(p, '2026-03-15', 28.0) for p in pairs]
    df_6m = pd.DataFrame(rows_6m)
    print(df_6m[['Pair', 'Role', 'Trades', 'Trades/Wk', 'Win Rate', 'Profit Factor', 'Net Profit ($)', 'Return (%)', 'Net R', 'Max Daily DD', 'Max Total DD', 'Verdict']].to_string(index=False))

    print("\n" + "=" * 125)
    print("INDIVIDUAL PAIR PERFORMANCE AUDIT: FULL 2-YEAR WALK-FORWARD (104 WEEKS: OCT 2024 - SEP 2026)")
    print("=" * 125)
    rows_2y = [simulate_pair(p, '2024-10-01', 104.0) for p in pairs]
    df_2y = pd.DataFrame(rows_2y)
    print(df_2y[['Pair', 'Role', 'Trades', 'Trades/Wk', 'Win Rate', 'Profit Factor', 'Net Profit ($)', 'Return (%)', 'Net R', 'Max Daily DD', 'Max Total DD', 'Verdict']].to_string(index=False))

if __name__ == '__main__':
    run_per_pair_audit()
