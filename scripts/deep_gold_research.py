import pickle, math
import pandas as pd
import numpy as np

def run_deep_research():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
        
    df_raw = all_data['XAUUSD'].copy()
    if df_raw['time_dt'].dt.tz is not None:
        df_raw['time_dt'] = df_raw['time_dt'].dt.tz_localize(None)
        
    START_2Y = '2024-10-01'
    START_6M = '2026-03-15'
    
    def simulate_gold(
        start_date=START_2Y,
        donch_len=20,
        cooldown_bars=3,
        max_hunt=8,
        fib_retrace=0.50,
        min_sl=18.0,
        max_sl=25.0,
        rr=1.75,
        use_4h=True,
        use_slope=True,
        slope_mult=0.10,
        session_filter=None, # None or (7, 18)
        use_be=False,
        be_trigger_r=1.0
    ):
        df = df_raw.copy()
        
        # 1H indicators
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
        be_activated = False
        
        start_idx = df[df['time_dt'] >= start_date].index[0]
        
        for i in range(start_idx, len(df)):
            if state != 0:
                hold = i - entry_idx
                if hold >= 1:
                    sl_dist = abs(entry_price - sl_price)
                    
                    if use_be and not be_activated:
                        if state == 1 and h[i] >= (entry_price + sl_dist * be_trigger_r):
                            sl_price = entry_price + 0.36
                            be_activated = True
                        elif state == -1 and l[i] <= (entry_price - sl_dist * be_trigger_r):
                            sl_price = entry_price - 0.36
                            be_activated = True
                            
                    exit_trig = False
                    exit_type = None
                    exit_price = 0.0
                    
                    if state == 1:
                        if h[i] >= tp_price and l[i] <= sl_price:
                            exit_trig = True
                            exit_type = 'BE' if be_activated else 'LOSS'
                            exit_price = sl_price
                        elif h[i] >= tp_price:
                            exit_trig = True
                            exit_type = 'WIN'
                            exit_price = tp_price
                        elif l[i] <= sl_price:
                            exit_trig = True
                            exit_type = 'BE' if be_activated else 'LOSS'
                            exit_price = sl_price
                        elif hold >= 160:
                            exit_trig = True
                            exit_price = c[i]
                            exit_type = 'WIN' if exit_price > entry_price else 'LOSS'
                    elif state == -1:
                        if l[i] <= tp_price and h[i] >= sl_price:
                            exit_trig = True
                            exit_type = 'BE' if be_activated else 'LOSS'
                            exit_price = sl_price
                        elif l[i] <= tp_price:
                            exit_trig = True
                            exit_type = 'WIN'
                            exit_price = tp_price
                        elif h[i] >= sl_price:
                            exit_trig = True
                            exit_type = 'BE' if be_activated else 'LOSS'
                            exit_price = sl_price
                        elif hold >= 160:
                            exit_trig = True
                            exit_price = c[i]
                            exit_type = 'WIN' if exit_price < entry_price else 'LOSS'
                            
                    if exit_trig:
                        dir_m = 1.0 if state == 1 else -1.0
                        p_diff = (exit_price - entry_price) * dir_m
                        trades.append({
                            'entry_time': times[entry_idx],
                            'exit_time': times[i],
                            'result': exit_type,
                            'entry_price': entry_price,
                            'exit_price': exit_price,
                            'sl_dist': sl_dist,
                            'price_diff': p_diff
                        })
                        state = 0
                        last_exit_idx = i
                        be_activated = False
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
            if session_filter is not None:
                in_active_hours = in_active_hours and (hr >= session_filter[0] and hr <= session_filter[1])
                
            slope_thresh = slope_mult * atr[i]
            h1_slope_bull = not use_slope or (e20_slope[i] >= slope_thresh)
            h1_slope_bear = not use_slope or (-e20_slope[i] >= slope_thresh)
            
            trend_bull = (c[i] > e50[i]) and (e20[i] > e50[i]) and h1_slope_bull and (not use_4h or h4_bull[i])
            trend_bear = (c[i] < e50[i]) and (e20[i] < e50[i]) and h1_slope_bear and (not use_4h or h4_bear[i])
            
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
                            be_activated = False
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
                            be_activated = False
                        else:
                            hunting = 0

        if len(trades) == 0:
            return {'trades': 0, 'freq_wk': 0, 'win_rate': 0, 'profit_factor': 0, 'net_profit': 0, 'return_pct': 0, 'net_r': 0, 'max_daily_dd': 0, 'max_overall_dd': 0}
            
        tdf = pd.DataFrame(trades)
        tdf['exit_dt'] = pd.to_datetime(tdf['exit_time'])
        tdf['exit_date'] = tdf['exit_dt'].dt.date
        
        # Prop firm evaluation with $5,000 account and 1% risk ($50 per trade)
        EQUITY = 5000.0
        RISK_CASH = 50.0
        
        pnl = []
        r_mult = []
        for _, row in tdf.iterrows():
            if row['result'] == 'WIN':
                pnl.append(RISK_CASH * rr)
                r_mult.append(rr)
            elif row['result'] == 'LOSS':
                pnl.append(-RISK_CASH)
                r_mult.append(-1.0)
            elif row['result'] == 'BE':
                pnl.append(0.0)
                r_mult.append(0.0)
                
        tdf['pnl'] = pnl
        tdf['r'] = r_mult
        
        # Calculate daily drawdown and total drawdown
        daily_pnl = tdf.groupby('exit_date')['pnl'].sum()
        max_daily_loss = abs(daily_pnl.min()) if len(daily_pnl) > 0 and daily_pnl.min() < 0 else 0.0
        max_daily_dd_pct = (max_daily_loss / EQUITY) * 100.0
        
        cum_pnl = tdf['pnl'].cumsum()
        peak = cum_pnl.cummax()
        dd = peak - cum_pnl
        max_dd_val = dd.max() if len(dd) > 0 else 0.0
        max_overall_dd_pct = (max_dd_val / EQUITY) * 100.0
        
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
        
        # Calculate weeks
        total_days = (df['time_dt'].max() - pd.to_datetime(start_date)).days
        weeks = total_days / 7.0
        freq_wk = n_trades / weeks if weeks > 0 else 0.0
        
        return {
            'trades': n_trades,
            'freq_wk': round(freq_wk, 2),
            'win_rate': round(wr, 1),
            'profit_factor': round(pf, 2),
            'net_profit': round(net_prof, 2),
            'return_pct': round(ret_pct, 2),
            'net_r': round(net_r, 2),
            'max_daily_dd': round(max_daily_dd_pct, 2),
            'max_overall_dd': round(max_overall_dd_pct, 2)
        }
        
    return simulate_gold

if __name__ == '__main__':
    sim = run_deep_research()
    
    print("=" * 110)
    print("GOLD EXPERIMENT 1: FULL 2-YEAR (104 WEEKS) ROBUSTNESS OF DONCHIAN LOOKBACK")
    print("=" * 110)
    rows_2y = []
    for d_len in [6, 8, 10, 12, 14, 16, 18, 20, 24]:
        res = sim(start_date='2024-10-01', donch_len=d_len)
        res['donch_len'] = d_len
        rows_2y.append(res)
    print(pd.DataFrame(rows_2y)[['donch_len', 'trades', 'freq_wk', 'win_rate', 'profit_factor', 'net_profit', 'return_pct', 'net_r', 'max_daily_dd', 'max_overall_dd']].to_string(index=False))

    print("\n" + "=" * 110)
    print("GOLD EXPERIMENT 2: COOLDOWN REDUCTION SWEEP (2-YEARS, DONCHIAN=10)")
    print("=" * 110)
    rows_cd = []
    for cd in [1, 2, 3, 4]:
        res = sim(start_date='2024-10-01', donch_len=10, cooldown_bars=cd)
        res['cooldown_bars'] = cd
        rows_cd.append(res)
    print(pd.DataFrame(rows_cd)[['cooldown_bars', 'trades', 'freq_wk', 'win_rate', 'profit_factor', 'net_profit', 'return_pct', 'net_r', 'max_daily_dd', 'max_overall_dd']].to_string(index=False))

    print("\n" + "=" * 110)
    print("GOLD EXPERIMENT 3: RETRACEMENT SENSITIVITY & FIBONACCI DEPTH (2-YEARS, DONCHIAN=10, CD=1)")
    print("=" * 110)
    rows_fib = []
    for fib in [0.236, 0.382, 0.500, 0.618]:
        for m_hunt in [4, 6, 8, 10, 12]:
            res = sim(start_date='2024-10-01', donch_len=10, cooldown_bars=1, fib_retrace=fib, max_hunt=m_hunt)
            res['fib_retrace'] = fib
            res['max_hunt'] = m_hunt
            rows_fib.append(res)
    print(pd.DataFrame(rows_fib)[['fib_retrace', 'max_hunt', 'trades', 'freq_wk', 'win_rate', 'profit_factor', 'net_profit', 'return_pct', 'net_r', 'max_daily_dd', 'max_overall_dd']].to_string(index=False))

    print("\n" + "=" * 110)
    print("GOLD EXPERIMENT 4: RISK/REWARD RATIO & STOP LOSS BOUNDS (2-YEARS)")
    print("=" * 110)
    rows_rr = []
    for rr_val in [1.50, 1.60, 1.75, 2.00]:
        for sl_bounds in [(15.0, 25.0), (18.0, 25.0), (18.0, 30.0)]:
            res = sim(start_date='2024-10-01', donch_len=10, cooldown_bars=1, fib_retrace=0.382, max_hunt=10, rr=rr_val, min_sl=sl_bounds[0], max_sl=sl_bounds[1])
            res['rr'] = rr_val
            res['min_sl'] = sl_bounds[0]
            res['max_sl'] = sl_bounds[1]
            rows_rr.append(res)
    print(pd.DataFrame(rows_rr)[['rr', 'min_sl', 'max_sl', 'trades', 'freq_wk', 'win_rate', 'profit_factor', 'net_profit', 'return_pct', 'net_r', 'max_daily_dd', 'max_overall_dd']].to_string(index=False))
