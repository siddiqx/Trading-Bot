"""
Test loss-cooldown and pullback protection:
Compare:
1. Standard 1-bar cooldown on both win and loss (Benchmark)
2. Asymmetric Cooldown: 1 bar after WIN, 4 bars (hours) after LOSS (allows pullbacks to finish)
3. Asymmetric Cooldown: 1 bar after WIN, 6 bars (hours) after LOSS
4. Fresh Breakout Requirement after LOSS (requires close > highest(high[1], 8) of new swing)
"""

import pickle
import pandas as pd
import numpy as np

def run_loss_cooldown_test():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
    df = all_data['XAUUSD'].copy()
    if df['time_dt'].dt.tz is not None:
        df['time_dt'] = df['time_dt'].dt.tz_localize(None)

    def simulate_custom_cooldown(loss_cooldown=1, win_cooldown=1, start_date='2026-03-15'):
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
        
        if start_date:
            start_idx = c_df[c_df['time_dt'] >= start_date].index[0]
        else:
            start_idx = 100
            
        trades = []
        state = 0
        entry_price, orig_sl, sl_price, tp_price, entry_idx = 0.0, 0.0, 0.0, 0.0, 0
        hunting = 0
        hunt_idx, hunt_level, hunt_ob_h, hunt_ob_l, hunt_fib, hunt_atr = 0, 0.0, 0.0, 0.0, 0.0, 0.0
        lockout_until = 0
        consec_losses = 0
        last_exit_idx = -999
        last_exit_was_loss = False
        
        min_sl = 18.0
        max_sl = 25.0
        sl_buffer = 0.35
        rr = 1.75
        fib = 0.382
        max_hunt = 8
        
        for i in range(start_idx, len(c_df)):
            if state != 0:
                hold = i - entry_idx
                if hold >= 1:
                    init_sl_dist = abs(entry_price - orig_sl)
                    exit_trig = False
                    exit_p = 0.0
                    
                    if state == 1:
                        if h[i] >= tp_price:
                            exit_trig = True
                            exit_p = tp_price
                            res_type = 'WIN'
                        elif l[i] <= sl_price:
                            exit_trig = True
                            exit_p = sl_price
                            res_type = 'LOSS'
                        elif hold >= 160:
                            exit_trig = True
                            exit_p = c[i]
                            res_type = 'WIN' if exit_p >= entry_price else 'LOSS'
                    elif state == -1:
                        if l[i] <= tp_price:
                            exit_trig = True
                            exit_p = tp_price
                            res_type = 'WIN'
                        elif h[i] >= sl_price:
                            exit_trig = True
                            exit_p = sl_price
                            res_type = 'LOSS'
                        elif hold >= 160:
                            exit_trig = True
                            exit_p = c[i]
                            res_type = 'WIN' if exit_p <= entry_price else 'LOSS'
                            
                    if exit_trig:
                        r_res = rr if res_type == 'WIN' else -1.0
                        trades.append({
                            'entry_time': times[entry_idx],
                            'exit_time': times[i],
                            'entry_dt': pd.to_datetime(times[entry_idx]),
                            'exit_dt': pd.to_datetime(times[i]),
                            'hold_bars': hold,
                            'result': res_type,
                            'r': r_res,
                            'pnl': 50.0 * r_res
                        })
                        state = 0
                        last_exit_idx = i
                        if res_type == 'WIN':
                            consec_losses = 0
                            last_exit_was_loss = False
                        else:
                            consec_losses += 1
                            last_exit_was_loss = True
                            if consec_losses >= 2:
                                lockout_until = i + 48
                                consec_losses = 0
                        continue

            active_cd = loss_cooldown if last_exit_was_loss else win_cooldown
            if i < lockout_until or (i - last_exit_idx) < active_cd:
                continue
                
            hr = hours[i]
            wday = weekdays[i]
            is_fri_pm = (wday == 'Friday') and (hr >= 15)
            in_active_hours = (hr != 21) and not is_fri_pm and (hr not in [0, 4, 15, 16, 19])
            
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
                            orig_sl = tent_sl
                            sl_price = tent_sl
                            tp_price = tent_tp
                            entry_idx = i
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
                            orig_sl = tent_sl
                            sl_price = tent_sl
                            tp_price = tent_tp
                            entry_idx = i
                        else:
                            hunting = 0
        return trades

    # Evaluate variants
    variants = [
        (1, 1, "1. Standard Cooldown (1h after Win, 1h after Loss)"),
        (3, 1, "2. Asymmetric Cooldown (1h after Win, 3h after Loss)"),
        (4, 1, "3. Asymmetric Cooldown (1h after Win, 4h after Loss)"),
        (6, 1, "4. Extended Cooldown (1h after Win, 6h after Loss)"),
    ]

    print("=" * 115)
    print("EMPIRICAL TEST: ASYMMETRIC POST-LOSS COOLDOWN (PREVENTING RE-ENTRY INTO PULLBACK NOISE)")
    print("=" * 115)
    
    rows = []
    for l_cd, w_cd, lbl in variants:
        t_6m = simulate_custom_cooldown(loss_cooldown=l_cd, win_cooldown=w_cd, start_date='2026-03-15')
        tdf_6m = pd.DataFrame(t_6m)
        n_6m = len(tdf_6m)
        wr_6m = (tdf_6m['result'] == 'WIN').mean() * 100.0
        pf_6m = tdf_6m[tdf_6m['result'] == 'WIN']['r'].sum() / abs(tdf_6m[tdf_6m['result'] == 'LOSS']['r'].sum())
        
        # Max loss streak
        res = tdf_6m['result'].tolist()
        max_strk = 0
        c_strk = 0
        for r in res:
            if r == 'LOSS':
                c_strk += 1
                max_strk = max(max_strk, c_strk)
            else:
                c_strk = 0
                
        # 2Y test
        t_2y = simulate_custom_cooldown(loss_cooldown=l_cd, win_cooldown=w_cd, start_date=None)
        tdf_2y = pd.DataFrame(t_2y)
        n_2y = len(tdf_2y)
        wr_2y = (tdf_2y['result'] == 'WIN').mean() * 100.0
        pf_2y = tdf_2y[tdf_2y['result'] == 'WIN']['r'].sum() / abs(tdf_2y[tdf_2y['result'] == 'LOSS']['r'].sum())
        
        rows.append({
            'Configuration': lbl,
            '6M Trades': n_6m,
            '6M Win Rate': f"{wr_6m:.1f}%",
            '6M Profit Factor': f"{pf_6m:.2f}",
            '6M Max Loss Streak': max_strk,
            '2Y Trades': n_2y,
            '2Y Win Rate': f"{wr_2y:.1f}%",
            '2Y Profit Factor': f"{pf_2y:.2f}"
        })
        
    print(pd.DataFrame(rows).to_string(index=False))

if __name__ == '__main__':
    run_loss_cooldown_test()
