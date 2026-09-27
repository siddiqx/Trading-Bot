import pickle, math
import pandas as pd
import numpy as np

def research_gold_mechanics():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
        
    df_raw = all_data['XAUUSD'].copy()
    if df_raw['time_dt'].dt.tz is not None:
        df_raw['time_dt'] = df_raw['time_dt'].dt.tz_localize(None)
        
    START_DATE = '2026-03-15'
    
    # Test breakeven trigger and session filter
    def run_sim(
        donch_len=12,
        use_be=False,
        be_trigger_r=1.0,
        rr=1.75,
        session_only=False # 07:00 - 18:00 UTC
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
        
        start_idx = df[df['time_dt'] >= START_DATE].index[0]
        
        for i in range(start_idx, len(df)):
            if state != 0:
                hold = i - entry_idx
                if hold >= 1:
                    sl_dist = abs(entry_price - sl_price)
                    
                    # Check breakeven move
                    if use_be and not be_activated:
                        if state == 1 and h[i] >= (entry_price + sl_dist * be_trigger_r):
                            sl_price = entry_price + 0.36 # Lock in costs
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
                            'result': exit_type,
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
                        
            if i < lockout_until or (i - last_exit_idx) < 3:
                continue
                
            hr = hours[i]
            wday = weekdays[i]
            is_fri_pm = (wday == 'Friday') and (hr >= 12)
            in_active_hours = (hr != 21) and not is_fri_pm
            if session_only:
                in_active_hours = in_active_hours and (hr >= 7 and hr <= 18)
                
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
                    hunt_fib = h[i] - 0.50 * (h[i] - hunt_ob_l)
                    hunt_atr = atr[i]
                elif short_setup:
                    hunting = -1
                    hunt_idx = i
                    hunt_level = don_l[i]
                    hunt_ob_h = h[i-1] if c[i-1] > o[i-1] else h[i]
                    hunt_ob_l = l[i-1] if c[i-1] > o[i-1] else l[i]
                    hunt_fib = l[i] + 0.50 * (hunt_ob_h - l[i])
                    hunt_atr = atr[i]
            else:
                if (i - hunt_idx) > 8:
                    hunting = 0
                elif hunting == 1:
                    retrace = (l[i] <= hunt_fib) or (l[i] <= hunt_ob_h) or (l[i] <= hunt_level * 1.0005) or (l[i] <= e20[i])
                    rejection = c[i] > o[i]
                    rsi_ok = rsi[i] <= 80.0
                    if retrace and rejection and rsi_ok and in_active_hours:
                        raw_sl = hunt_ob_l - (hunt_atr * 0.50)
                        calc_dist = abs(c[i] - raw_sl)
                        act_sl_dist = min(max(calc_dist, 18.0), 25.0)
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
                        act_sl_dist = min(max(calc_dist, 18.0), 25.0)
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
                            
        # Account performance
        bal = 5000.0
        peak_bal = 5000.0
        max_ov_dd = 0.0
        max_d_dd = 0.0
        pnl_list = []
        r_list = []
        
        for tr in trades:
            sl_d = tr['sl_dist']
            lots = max(0.01, round((bal * 0.01) / (sl_d * 100.0), 2))
            actual_risk = lots * 100.0 * sl_d
            gross = lots * 100.0 * tr['price_diff']
            costs = lots * 100.0 * 0.36
            net = gross - costs
            r_val = net / actual_risk if actual_risk > 0 else 0
            
            bal += net
            peak_bal = max(peak_bal, bal)
            ov_dd = (5000.0 - bal) / 5000.0
            max_ov_dd = max(max_ov_dd, ov_dd)
            
            pnl_list.append(net)
            r_list.append(r_val)
            
        n_tr = len(trades)
        wins = sum(1 for p in pnl_list if p > 0)
        losses = sum(1 for p in pnl_list if p < 0)
        bes = sum(1 for p in pnl_list if abs(p) < 1.0)
        wr = (wins / n_tr * 100.0) if n_tr > 0 else 0
        w_sum = sum(p for p in pnl_list if p > 0)
        l_sum = abs(sum(p for p in pnl_list if p < 0))
        pf = (w_sum / l_sum) if l_sum > 0 else 99.0
        net_profit = bal - 5000.0
        ret_pct = (net_profit / 5000.0) * 100.0
        net_r = sum(r_list)
        freq_wk = n_tr / 28.0
        
        return {
            'trades': n_tr,
            'freq_wk': round(freq_wk, 2),
            'wins': wins,
            'losses': losses,
            'bes': bes,
            'win_rate': round(wr, 1),
            'profit_factor': round(pf, 2),
            'net_profit': round(net_profit, 2),
            'return_pct': round(ret_pct, 2),
            'net_r': round(net_r, 2),
            'max_overall_dd': round(max_ov_dd * 100, 2)
        }

    tests = [
        ('1. Current Baseline (20-bar Donchian, 1.75 RR)', {'donch_len': 20, 'use_be': False}),
        ('2. 12-bar Donchian (London/NY Session Cycle)', {'donch_len': 12, 'use_be': False}),
        ('3. 12-bar Donchian + Breakeven at 1.0 R', {'donch_len': 12, 'use_be': True, 'be_trigger_r': 1.0}),
        ('4. 12-bar Donchian + Breakeven at 1.2 R', {'donch_len': 12, 'use_be': True, 'be_trigger_r': 1.2}),
        ('5. 10-bar Donchian (High Frequency)', {'donch_len': 10, 'use_be': False}),
        ('6. 12-bar Donchian + London/NY Session Only (07-18 UTC)', {'donch_len': 12, 'session_only': True}),
    ]
    
    out = []
    for label, p in tests:
        res = run_sim(**p)
        res['name'] = label
        out.append(res)
        
    df_out = pd.DataFrame(out)[['name', 'trades', 'freq_wk', 'wins', 'losses', 'win_rate', 'profit_factor', 'net_profit', 'return_pct', 'net_r', 'max_overall_dd']]
    print(df_out.to_string(index=False))

if __name__ == '__main__':
    research_gold_mechanics()
