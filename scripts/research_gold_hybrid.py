import pickle, math
import pandas as pd
import numpy as np

def research_gold_frequency_expansion():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
        
    df_raw = all_data['XAUUSD'].copy()
    if df_raw['time_dt'].dt.tz is not None:
        df_raw['time_dt'] = df_raw['time_dt'].dt.tz_localize(None)
        
    START_DATE = '2026-03-15'
    
    # We test 4 architectural enhancements specifically for Gold:
    # Model 1: Baseline (1H 20-bar Donchian) -> ~1.6 tr/wk
    # Model 2: 12-bar Session Donchian -> ~1.9 tr/wk
    # Model 3: Trend Continuation Pullback (Adding EMA 20 bounce setups during strong 1H+4H trends)
    # Model 4: Session Breakout Engine (Opening Range Breakout for London 07:00 UTC & NY 12:00 UTC)
    # Model 5: Combined Hybrid (12-bar Donchian Breakout + EMA Trend Re-entry)
    
    # Let's write the engine for Model 3 & Model 5
    def simulate_gold_hybrid(
        donch_len=12,
        allow_trend_pullbacks=True,
        min_sl=18.0,
        max_sl=25.0,
        rr=1.75
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
        
        start_idx = df[df['time_dt'] >= START_DATE].index[0]
        
        for i in range(start_idx, len(df)):
            if state != 0:
                hold = i - entry_idx
                if hold >= 1:
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
                        sl_dist = abs(entry_price - sl_price)
                        p_diff = (exit_price - entry_price) * (1.0 if state == 1 else -1.0)
                        trades.append({
                            'direction': 'LONG' if state == 1 else 'SHORT',
                            'entry_time': times[entry_idx],
                            'exit_time': times[i],
                            'entry_price': entry_price,
                            'exit_price': exit_price,
                            'result': exit_type,
                            'sl_dist': sl_dist,
                            'price_diff': p_diff,
                            'hold_bars': hold
                        })
                        state = 0
                        last_exit_idx = i
                        if exit_type == 'WIN':
                            consec_losses = 0
                        else:
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
            
            slope_thresh = 0.10 * atr[i]
            h1_slope_bull = e20_slope[i] >= slope_thresh
            h1_slope_bear = -e20_slope[i] >= slope_thresh
            
            trend_bull = (c[i] > e50[i]) and (e20[i] > e50[i]) and h1_slope_bull and h4_bull[i]
            trend_bear = (c[i] < e50[i]) and (e20[i] < e50[i]) and h1_slope_bear and h4_bear[i]
            
            # Setup 1: Donchian Breakout
            long_break = trend_bull and (c[i] > don_h[i]) and (c[i-1] <= don_h[i-1]) and in_active_hours
            short_break = trend_bear and (c[i] < don_l[i]) and (c[i-1] >= don_l[i-1]) and in_active_hours
            
            # Setup 2: Trend Continuation Pullback (When strong trend is established, price touches EMA 20 and rejects)
            long_pullback = False
            short_pullback = False
            if allow_trend_pullbacks and (hunting == 0):
                # Price touches EMA 20 from above during confirmed strong bull trend
                touch_e20_bull = (l[i] <= e20[i]) and (c[i] > e20[i]) and (c[i] > o[i]) # Bullish rejection
                strong_trend_bull = trend_bull and (e20[i] > e50[i] + 0.5 * atr[i]) and (rsi[i] >= 45 and rsi[i] <= 70)
                long_pullback = touch_e20_bull and strong_trend_bull and in_active_hours
                
                # Price touches EMA 20 from below during confirmed strong bear trend
                touch_e20_bear = (h[i] >= e20[i]) and (c[i] < e20[i]) and (c[i] < o[i]) # Bearish rejection
                strong_trend_bear = trend_bear and (e50[i] > e20[i] + 0.5 * atr[i]) and (rsi[i] >= 30 and rsi[i] <= 55)
                short_pullback = touch_e20_bear and strong_trend_bear and in_active_hours
                
            if hunting == 0:
                if long_break:
                    hunting = 1
                    hunt_idx = i
                    hunt_level = don_h[i]
                    hunt_ob_l = l[i-1] if c[i-1] < o[i-1] else l[i]
                    hunt_ob_h = h[i-1] if c[i-1] < o[i-1] else h[i]
                    hunt_fib = h[i] - 0.50 * (h[i] - hunt_ob_l)
                    hunt_atr = atr[i]
                elif short_break:
                    hunting = -1
                    hunt_idx = i
                    hunt_level = don_l[i]
                    hunt_ob_h = h[i-1] if c[i-1] > o[i-1] else h[i]
                    hunt_ob_l = l[i-1] if c[i-1] > o[i-1] else l[i]
                    hunt_fib = l[i] + 0.50 * (hunt_ob_h - l[i])
                    hunt_atr = atr[i]
                elif long_pullback:
                    # Immediate entry on confirmed EMA 20 rejection in strong trend
                    act_sl = min(max(c[i] - (l[i] - 0.25 * atr[i]), min_sl), max_sl)
                    tent_sl = c[i] - act_sl
                    tent_tp = c[i] + act_sl * rr
                    if h[i] < tent_tp:
                        state = 1
                        entry_price, sl_price, tp_price, entry_idx = c[i], tent_sl, tent_tp, i
                elif short_pullback:
                    act_sl = min(max((h[i] + 0.25 * atr[i]) - c[i], min_sl), max_sl)
                    tent_sl = c[i] + act_sl
                    tent_tp = c[i] - act_sl * rr
                    if l[i] > tent_tp:
                        state = -1
                        entry_price, sl_price, tp_price, entry_idx = c[i], tent_sl, tent_tp, i
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
                            
        # Account performance
        bal = 5000.0
        peak_bal = 5000.0
        max_ov_dd = 0.0
        max_d_dd = 0.0
        pnl_list = []
        r_list = []
        cur_d = None
        d_start = 5000.0
        
        for tr in trades:
            b_dt = pd.to_datetime(tr['exit_time']).date()
            if b_dt != cur_d:
                cur_d = b_dt
                d_start = bal
                
            sl_d = tr['sl_dist']
            lots = max(0.01, round((bal * 0.01) / (sl_d * 100.0), 2))
            actual_risk = lots * 100.0 * sl_d
            gross = lots * 100.0 * tr['price_diff']
            costs = lots * 100.0 * 0.36
            net = gross - costs
            r_val = net / actual_risk if actual_risk > 0 else 0
            
            bal += net
            peak_bal = max(peak_bal, bal)
            
            d_dd = (d_start - bal) / d_start if d_start > 0 else 0
            max_d_dd = max(max_d_dd, d_dd)
            ov_dd = (5000.0 - bal) / 5000.0
            max_ov_dd = max(max_ov_dd, ov_dd)
            
            pnl_list.append(net)
            r_list.append(r_val)
            
        n_tr = len(trades)
        wins = sum(1 for p in pnl_list if p > 0)
        losses = sum(1 for p in pnl_list if p <= 0)
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
            'win_rate': round(wr, 1),
            'profit_factor': round(pf, 2),
            'net_profit': round(net_profit, 2),
            'return_pct': round(ret_pct, 2),
            'net_r': round(net_r, 2),
            'max_daily_dd': round(max_d_dd * 100, 2),
            'max_overall_dd': round(max_ov_dd * 100, 2)
        }

    configs = [
        ('1. Current Baseline (20-bar Donchian only)', {'donch_len': 20, 'allow_trend_pullbacks': False}),
        ('2. 12-bar Donchian only', {'donch_len': 12, 'allow_trend_pullbacks': False}),
        ('3. 10-bar Donchian only', {'donch_len': 10, 'allow_trend_pullbacks': False}),
        ('4. Hybrid A: 20-bar Donchian + EMA 20 Pullback Re-entry', {'donch_len': 20, 'allow_trend_pullbacks': True}),
        ('5. Hybrid B: 12-bar Donchian + EMA 20 Pullback Re-entry', {'donch_len': 12, 'allow_trend_pullbacks': True}),
        ('6. Hybrid C: 10-bar Donchian + EMA 20 Pullback Re-entry', {'donch_len': 10, 'allow_trend_pullbacks': True}),
        ('7. Hybrid B with 1.65 R:R Target', {'donch_len': 12, 'allow_trend_pullbacks': True, 'rr': 1.65}),
    ]
    
    rows = []
    for label, cfg in configs:
        res = simulate_gold_hybrid(**cfg)
        res['configuration'] = label
        rows.append(res)
        
    df_comp = pd.DataFrame(rows)[['configuration', 'trades', 'freq_wk', 'win_rate', 'profit_factor', 'net_profit', 'return_pct', 'net_r', 'max_daily_dd', 'max_overall_dd']]
    print(df_comp.to_string(index=False))

if __name__ == '__main__':
    research_gold_frequency_expansion()
