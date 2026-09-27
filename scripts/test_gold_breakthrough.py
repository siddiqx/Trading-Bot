import pickle, math
import pandas as pd
import numpy as np

def run_breakthrough_research():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
        
    df_raw = all_data['XAUUSD'].copy()
    if df_raw['time_dt'].dt.tz is not None:
        df_raw['time_dt'] = df_raw['time_dt'].dt.tz_localize(None)
        
    START_2Y = '2024-10-01'
    START_6M = '2026-03-15'
    
    # We test multiple setup generators specifically engineered for Gold
    def simulate_gold_advanced(
        start_date=START_2Y,
        setup_types=['DONCHIAN'], # Options: 'DONCHIAN', 'IMPULSE_PULLBACK', 'SESSION_MOMENTUM'
        donch_len=8,
        cooldown_bars=1,
        max_hunt=8,
        fib_retrace=0.382,
        rr=1.75,
        min_sl=15.0,
        max_sl=25.0,
        filter_toxic_hours=True # Filter hours 0, 4, 15, 16, 19
    ):
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
        entry_price, sl_price, tp_price, entry_idx = 0,0,0,0
        hunting = 0
        hunt_idx, hunt_level, hunt_ob_h, hunt_ob_l, hunt_fib, hunt_atr = 0,0,0,0,0,0
        hunt_type = None
        last_exit_idx = -999
        lockout_until = 0
        consec_losses = 0
        
        start_idx = df[df['time_dt'] >= start_date].index[0]
        
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
            
            # Active hours filter
            in_active_hours = (hr != 21) and not is_fri_pm
            if filter_toxic_hours:
                # Based on deep pattern analysis, hours 4, 15, 16, 19, 0 are statistically negative on Gold
                if hr in [0, 4, 15, 16, 19]:
                    in_active_hours = False
                    
            slope_thresh = 0.10 * atr[i]
            h1_slope_bull = e20_slope[i] >= slope_thresh
            h1_slope_bear = -e20_slope[i] >= slope_thresh
            
            trend_bull = (c[i] > e50[i]) and (e20[i] > e50[i]) and h1_slope_bull and h4_bull[i]
            trend_bear = (c[i] < e50[i]) and (e20[i] < e50[i]) and h1_slope_bear and h4_bear[i]
            
            # SETUP 1: DONCHIAN BREAKOUT
            donch_long_setup = ('DONCHIAN' in setup_types) and trend_bull and (c[i] > don_h[i]) and (c[i-1] <= don_h[i-1]) and in_active_hours
            donch_short_setup = ('DONCHIAN' in setup_types) and trend_bear and (c[i] < don_l[i]) and (c[i-1] >= don_l[i-1]) and in_active_hours
            
            # SETUP 2: INSTITUTIONAL IMPULSE CONTINUATION (Pullback to EMA20 after high-velocity impulse candle)
            # Conditions:
            # 1. Strong trend alignment (1H + 4H)
            # 2. Previous 3 bars had a massive expansion impulse (range >= 1.25 ATR)
            # 3. Current bar pulls back into EMA20 and prints a strong rejection candle with body > 40%
            rng = h[i] - l[i]
            body_ratio_bull = (c[i] - l[i]) / (rng + 1e-9)
            body_ratio_bear = (h[i] - c[i]) / (rng + 1e-9)
            has_prior_impulse_bull = any((h[i-k] - l[i-k]) >= 1.20 * atr[i-k] and c[i-k] > o[i-k] for k in range(1, 4))
            has_prior_impulse_bear = any((h[i-k] - l[i-k]) >= 1.20 * atr[i-k] and c[i-k] < o[i-k] for k in range(1, 4))
            
            impulse_long = ('IMPULSE_PULLBACK' in setup_types) and trend_bull and in_active_hours and has_prior_impulse_bull and (l[i] <= e20[i]) and (c[i] > e20[i]) and (c[i] > o[i]) and (body_ratio_bull >= 0.40) and (rsi[i] >= 40.0 and rsi[i] <= 70.0)
            impulse_short = ('IMPULSE_PULLBACK' in setup_types) and trend_bear and in_active_hours and has_prior_impulse_bear and (h[i] >= e20[i]) and (c[i] < e20[i]) and (c[i] < o[i]) and (body_ratio_bear >= 0.40) and (rsi[i] <= 60.0 and rsi[i] >= 30.0)

            # SETUP 3: LONDON / NY SESSION MOMENTUM EXPANSION (08:00 UTC or 13:00 UTC Breakout)
            # In London (08:00) or NY (13:00), strong directional close breaking prior 4-bar extreme
            is_session_open_bar = hr in [8, 9, 13, 14]
            prior_4h_high = np.max(h[max(0, i-4):i])
            prior_4h_low = np.min(l[max(0, i-4):i])
            session_long = ('SESSION_MOMENTUM' in setup_types) and is_session_open_bar and trend_bull and in_active_hours and (c[i] > prior_4h_high) and (c[i] > o[i]) and (rng >= 1.10 * atr[i])
            session_short = ('SESSION_MOMENTUM' in setup_types) and is_session_open_bar and trend_bear and in_active_hours and (c[i] < prior_4h_low) and (c[i] < o[i]) and (rng >= 1.10 * atr[i])

            if hunting == 0:
                if donch_long_setup:
                    hunting = 1
                    hunt_type = 'DONCHIAN'
                    hunt_idx = i
                    hunt_level = don_h[i]
                    hunt_ob_l = l[i-1] if c[i-1] < o[i-1] else l[i]
                    hunt_ob_h = h[i-1] if c[i-1] < o[i-1] else h[i]
                    hunt_fib = h[i] - fib_retrace * (h[i] - hunt_ob_l)
                    hunt_atr = atr[i]
                elif donch_short_setup:
                    hunting = -1
                    hunt_type = 'DONCHIAN'
                    hunt_idx = i
                    hunt_level = don_l[i]
                    hunt_ob_h = h[i-1] if c[i-1] > o[i-1] else h[i]
                    hunt_ob_l = l[i-1] if c[i-1] > o[i-1] else l[i]
                    hunt_fib = l[i] + fib_retrace * (hunt_ob_h - l[i])
                    hunt_atr = atr[i]
                elif impulse_long or session_long:
                    # Direct execution on confirmed impulse candle close!
                    raw_sl = min(l[i], e20[i]) - (atr[i] * 0.35)
                    calc_dist = abs(c[i] - raw_sl)
                    act_sl_dist = min(max(calc_dist, min_sl), max_sl)
                    tent_sl = c[i] - act_sl_dist
                    tent_tp = c[i] + (act_sl_dist * rr)
                    if h[i] < tent_tp:
                        state = 1
                        entry_price = c[i]
                        entry_idx = i
                        sl_price = tent_sl
                        tp_price = tent_tp
                elif impulse_short or session_short:
                    raw_sl = max(h[i], e20[i]) + (atr[i] * 0.35)
                    calc_dist = abs(raw_sl - c[i])
                    act_sl_dist = min(max(calc_dist, min_sl), max_sl)
                    tent_sl = c[i] + act_sl_dist
                    tent_tp = c[i] - (act_sl_dist * rr)
                    if l[i] > tent_tp:
                        state = -1
                        entry_price = c[i]
                        entry_idx = i
                        sl_price = tent_sl
                        tp_price = tent_tp
            else:
                # Hunting logic for Donchian
                if (i - hunt_idx) > max_hunt:
                    hunting = 0
                elif hunting == 1:
                    retrace = (l[i] <= hunt_fib) or (l[i] <= hunt_ob_h) or (l[i] <= hunt_level * 1.0005) or (l[i] <= e20[i])
                    rejection = c[i] > o[i]
                    rsi_ok = rsi[i] <= 80.0
                    if retrace and rejection and rsi_ok and in_active_hours:
                        raw_sl = hunt_ob_l - (hunt_atr * 0.35)
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
                        raw_sl = hunt_ob_h + (hunt_atr * 0.35)
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

        if len(trades) == 0:
            return {'trades': 0, 'freq_wk': 0, 'win_rate': 0, 'profit_factor': 0, 'net_profit': 0, 'return_pct': 0, 'net_r': 0, 'max_daily_dd': 0, 'max_overall_dd': 0}
            
        tdf = pd.DataFrame(trades)
        tdf['exit_dt'] = pd.to_datetime(tdf['exit_time'])
        tdf['exit_date'] = tdf['exit_dt'].dt.date
        
        EQUITY = 5000.0
        RISK_CASH = 50.0
        
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
        wr = (wins / n_trades) * 100.0 if n_trades > 0 else 0.0
        
        win_sum = tdf[tdf['pnl'] > 0]['pnl'].sum()
        loss_sum = abs(tdf[tdf['pnl'] < 0]['pnl'].sum())
        pf = (win_sum / loss_sum) if loss_sum > 0 else 99.0
        
        net_prof = tdf['pnl'].sum()
        ret_pct = (net_prof / EQUITY) * 100.0
        net_r = tdf['r'].sum()
        
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

    return simulate_gold_advanced

if __name__ == '__main__':
    sim = run_breakthrough_research()
    
    print("=" * 115)
    print("RESEARCH MATRIX 1: LAST 6 MONTHS (28 WEEKS) EVALUATION OF FREQUENCY ENHANCEMENTS")
    print("=" * 115)
    models_6m = [
        ("Baseline (20-bar Donchian)", ['DONCHIAN'], 20, 3, False),
        ("Donchian 10 (Fast)", ['DONCHIAN'], 10, 1, False),
        ("Donchian 8 (Fast)", ['DONCHIAN'], 8, 1, False),
        ("Donchian 8 + Filter Toxic Hours (0,4,15,16,19)", ['DONCHIAN'], 8, 1, True),
        ("Donchian 10 + Impulse Pullback", ['DONCHIAN', 'IMPULSE_PULLBACK'], 10, 1, False),
        ("Donchian 8 + Impulse Pullback", ['DONCHIAN', 'IMPULSE_PULLBACK'], 8, 1, False),
        ("Donchian 8 + Session Momentum", ['DONCHIAN', 'SESSION_MOMENTUM'], 8, 1, False),
        ("Donchian 8 + Impulse + Session Momentum", ['DONCHIAN', 'IMPULSE_PULLBACK', 'SESSION_MOMENTUM'], 8, 1, False),
        ("Donchian 8 + Impulse + Session + Toxic Filter", ['DONCHIAN', 'IMPULSE_PULLBACK', 'SESSION_MOMENTUM'], 8, 1, True),
    ]
    rows_6m = []
    for name, s_types, d_len, cd, tox in models_6m:
        r = sim(start_date='2026-03-15', setup_types=s_types, donch_len=d_len, cooldown_bars=cd, filter_toxic_hours=tox)
        r['model'] = name
        rows_6m.append(r)
    print(pd.DataFrame(rows_6m)[['model', 'trades', 'freq_wk', 'win_rate', 'profit_factor', 'net_profit', 'return_pct', 'net_r', 'max_daily_dd', 'max_overall_dd']].to_string(index=False))

    print("\n" + "=" * 115)
    print("RESEARCH MATRIX 2: FULL 2-YEAR (104 WEEKS) WALK-FORWARD VALIDATION")
    print("=" * 115)
    rows_2y = []
    for name, s_types, d_len, cd, tox in models_6m:
        r = sim(start_date='2024-10-01', setup_types=s_types, donch_len=d_len, cooldown_bars=cd, filter_toxic_hours=tox)
        r['model'] = name
        rows_2y.append(r)
    print(pd.DataFrame(rows_2y)[['model', 'trades', 'freq_wk', 'win_rate', 'profit_factor', 'net_profit', 'return_pct', 'net_r', 'max_daily_dd', 'max_overall_dd']].to_string(index=False))
