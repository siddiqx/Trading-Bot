import pickle, math
import pandas as pd
import numpy as np

def run_deep_speedup():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
        
    df_gold = all_data['XAUUSD'].copy()
    if df_gold['time_dt'].dt.tz is not None:
        df_gold['time_dt'] = df_gold['time_dt'].dt.tz_localize(None)
        
    df_usdcad = all_data['USDCAD'].copy()
    if df_usdcad['time_dt'].dt.tz is not None:
        df_usdcad['time_dt'] = df_usdcad['time_dt'].dt.tz_localize(None)

    START_DATE = '2026-03-15'
    WEEKS = 28.0

    def generate_trades(df, is_gold=True, donch_len=8, use_dynamic_session_donch=False):
        c_df = df.copy()
        cooldown = 1 if is_gold else 3
        max_hunt = 8
        fib_retrace = 0.382 if is_gold else 0.500
        sl_buffer = 0.35 if is_gold else 0.50
        min_sl = 18.0
        max_sl = 25.0
        rr = 1.75
        
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
        
        # Donchian channels:
        c_df['don_h8'] = c_df['high'].shift(1).rolling(8).max()
        c_df['don_l8'] = c_df['low'].shift(1).rolling(8).min()
        c_df['don_h6'] = c_df['high'].shift(1).rolling(6).max()
        c_df['don_l6'] = c_df['low'].shift(1).rolling(6).min()
        c_df['don_h20'] = c_df['high'].shift(1).rolling(20).max()
        c_df['don_l20'] = c_df['low'].shift(1).rolling(20).min()
        
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
        h4_bull = c_df['h4_bull'].values
        h4_bear = c_df['h4_bear'].values
        hours = c_df['time_dt'].dt.hour.values
        weekdays = c_df['time_dt'].dt.day_name().values
        times = c_df['time_dt'].values
        
        don_h8 = c_df['don_h8'].values
        don_l8 = c_df['don_l8'].values
        don_h6 = c_df['don_h6'].values
        don_l6 = c_df['don_l6'].values
        don_h20 = c_df['don_h20'].values
        don_l20 = c_df['don_l20'].values
        
        pip_mult = 1.0 if is_gold else 10000.0
        start_idx = c_df[c_df['time_dt'] >= START_DATE].index[0]
        
        trades = []
        state = 0
        entry_price, sl_price, tp_price, entry_idx = 0,0,0,0
        hunting = 0
        hunt_idx, hunt_level, hunt_ob_h, hunt_ob_l, hunt_fib, hunt_atr = 0,0,0,0,0,0
        lockout_until = 0
        consec_losses = 0
        last_exit_idx = -999
        
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
                            'pair': 'XAUUSD' if is_gold else 'USDCAD',
                            'priority': 0 if is_gold else 1,
                            'entry_time': times[entry_idx],
                            'exit_time': times[i],
                            'entry_dt': pd.to_datetime(times[entry_idx]),
                            'exit_dt': pd.to_datetime(times[i]),
                            'entry_bar': entry_idx,
                            'exit_bar': i,
                            'result': exit_type,
                            'r': rr if exit_type == 'WIN' else -1.0
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
            
            if is_gold:
                if use_dynamic_session_donch and hr in [7, 8, 9, 12, 13, 14]:
                    cur_don_h = don_h6[i]
                    cur_don_l = don_l6[i]
                    prev_don_h = don_h6[i-1]
                    prev_don_l = don_l6[i-1]
                else:
                    cur_don_h = don_h8[i]
                    cur_don_l = don_l8[i]
                    prev_don_h = don_h8[i-1]
                    prev_don_l = don_l8[i-1]
            else:
                cur_don_h = don_h20[i]
                cur_don_l = don_l20[i]
                prev_don_h = don_h20[i-1]
                prev_don_l = don_l20[i-1]
                
            long_setup = trend_bull and (c[i] > cur_don_h) and (c[i-1] <= prev_don_h) and in_active_hours
            short_setup = trend_bear and (c[i] < cur_don_l) and (c[i-1] >= prev_don_l) and in_active_hours
            
            if hunting == 0:
                if long_setup:
                    hunting = 1
                    hunt_idx = i
                    hunt_level = cur_don_h
                    hunt_ob_l = l[i-1] if c[i-1] < o[i-1] else l[i]
                    hunt_ob_h = h[i-1] if c[i-1] < o[i-1] else h[i]
                    hunt_fib = h[i] - fib_retrace * (h[i] - hunt_ob_l)
                    hunt_atr = atr[i]
                elif short_setup:
                    hunting = -1
                    hunt_idx = i
                    hunt_level = cur_don_l
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
        return trades

    # Generate baseline & variant candidate pools
    gold_trades_base = generate_trades(df_gold, is_gold=True, donch_len=8, use_dynamic_session_donch=False)
    gold_trades_session_fast = generate_trades(df_gold, is_gold=True, donch_len=8, use_dynamic_session_donch=True)
    usdcad_trades = generate_trades(df_usdcad, is_gold=False, donch_len=20)
    
    # Dual synergy locked pool
    dual_pool = gold_trades_base + usdcad_trades
    dual_df = pd.DataFrame(dual_pool).sort_values(by=['entry_dt', 'priority']).reset_index(drop=True)
    dual_locked = []
    cur_exit = pd.Timestamp.min
    for _, tr in dual_df.iterrows():
        if tr['entry_dt'] >= cur_exit:
            dual_locked.append(tr.to_dict())
            cur_exit = tr['exit_dt']

    # Speed & Timeline evaluation function
    def eval_speed_profile(trade_list, risk_p1=1.0, risk_p2=1.0, risk_funded=1.0, name=""):
        tdf = pd.DataFrame(trade_list)
        n_all = len(tdf)
        
        ACCOUNT = 5000.0
        MAX_DD = 400.0 # 8%
        
        p1_days, p2_days, tot_days = [], [], []
        p1_trades, p2_trades = [], []
        breaches = 0
        runs = 0
        
        for start_i in range(0, max(1, n_all - 20)):
            runs += 1
            # Phase 1: Target $400 (8%)
            cash_r1 = ACCOUNT * (risk_p1 / 100.0)
            p1_cum = 0.0
            p1_i = start_i
            p1_pass = False
            p1_peak = 0.0
            
            while p1_i < n_all:
                pnl = tdf.iloc[p1_i]['r'] * cash_r1
                p1_cum += pnl
                p1_peak = max(p1_peak, p1_cum)
                if (p1_peak - p1_cum) >= MAX_DD:
                    breaches += 1
                    break
                if p1_cum >= 400.0:
                    p1_pass = True
                    break
                p1_i += 1
                
            if not p1_pass:
                continue
                
            p1_d = (tdf.iloc[p1_i]['exit_dt'] - tdf.iloc[start_i]['entry_dt']).days
            p1_tr = p1_i - start_i + 1
            
            # Phase 2: Target $250 (5%)
            cash_r2 = ACCOUNT * (risk_p2 / 100.0)
            p2_start_i = p1_i + 1
            p2_cum = 0.0
            p2_i = p2_start_i
            p2_pass = False
            p2_peak = 0.0
            
            while p2_i < n_all:
                pnl = tdf.iloc[p2_i]['r'] * cash_r2
                p2_cum += pnl
                p2_peak = max(p2_peak, p2_cum)
                if (p2_peak - p2_cum) >= MAX_DD:
                    breaches += 1
                    break
                if p2_cum >= 250.0:
                    p2_pass = True
                    break
                p2_i += 1
                
            if not p2_pass:
                continue
                
            p2_d = (tdf.iloc[p2_i]['exit_dt'] - tdf.iloc[p2_start_i]['entry_dt']).days
            p2_tr = p2_i - p2_start_i + 1
            
            # Payout: 14 days minimum holding
            tot_d = p1_d + 1 + p2_d + 1 + 14
            
            p1_days.append(p1_d)
            p2_days.append(p2_d)
            tot_days.append(tot_d)
            p1_trades.append(p1_tr)
            p2_trades.append(p2_tr)
            
        pass_rate = (len(tot_days) / runs * 100.0) if runs > 0 else 0.0
        
        # Win rate and Profit factor of this trade set
        wins = (tdf['result'] == 'WIN').sum()
        wr = (wins / n_all) * 100.0
        win_r = (tdf[tdf['result'] == 'WIN']['r']).sum()
        loss_r = abs((tdf[tdf['result'] == 'LOSS']['r']).sum())
        pf = win_r / loss_r if loss_r > 0 else 99.0
        
        return {
            'Speedup Architecture': name,
            'Total Trades': n_all,
            'Win Rate': f"{wr:.1f}%",
            'Profit Factor': f"{pf:.2f}",
            'Phase 1 Days (Median)': f"{np.median(p1_days):.0f} days (~{np.median(p1_days)/7:.1f} wks)",
            'Phase 2 Days (Median)': f"{np.median(p2_days):.0f} days (~{np.median(p2_days)/7:.1f} wks)",
            'Total Days to Payout': f"{np.median(tot_days):.0f} days (~{np.median(tot_days)/30:.1f} mo)",
            'Fastest Payout': f"{np.min(tot_days):.0f} days",
            'Challenge Pass Rate': f"{pass_rate:.1f}%"
        }

    results = []
    # Benchmark
    results.append(eval_speed_profile(gold_trades_base, risk_p1=1.0, risk_p2=1.0, name="1. Current Benchmark (Gold Tuned @ 1.0% Risk)"))
    # Speedup Lever A: Dual Synergy
    results.append(eval_speed_profile(dual_locked, risk_p1=1.0, risk_p2=1.0, name="2. Dual Synergy (Gold + USDCAD @ 1.0% Risk)"))
    # Speedup Lever B: Dynamic Session Donchian
    results.append(eval_speed_profile(gold_trades_session_fast, risk_p1=1.0, risk_p2=1.0, name="3. Session-Accelerated Gold (6-bar London/NY @ 1.0% Risk)"))
    # Speedup Lever C: Strategic 1.25% Phase 1 Risk Sizing
    results.append(eval_speed_profile(gold_trades_base, risk_p1=1.25, risk_p2=1.0, name="4. Strategic Risk Sizing (Gold @ 1.25% P1, 1.0% P2)"))
    # Speedup Lever D: Strategic 1.50% Phase 1 Risk Sizing
    results.append(eval_speed_profile(gold_trades_base, risk_p1=1.50, risk_p2=1.0, name="5. Aggressive Risk Sizing (Gold @ 1.50% P1, 1.0% P2)"))
    # Speedup Lever E: Maximum Safe Synergy (Dual Synergy @ 1.25% P1, 1.0% P2)
    results.append(eval_speed_profile(dual_locked, risk_p1=1.25, risk_p2=1.0, name="6. Combined Acceleration (Dual Synergy @ 1.25% P1, 1.0% P2)"))

    print("=" * 125)
    print("SPEEDUP ARCHITECTURE AUDIT: HOW TO COMPRESS TIMELINE TO FIRST PAYOUT SAFELY")
    print("=" * 125)
    print(pd.DataFrame(results).to_string(index=False))

if __name__ == '__main__':
    run_deep_speedup()
