"""
DEEP STRATEGY ENHANCEMENT AUDIT:
Testing strategy-level optimizations to safely accelerate prop firm challenge completion.
Measures:
1. Circuit Breaker Calibration (48h vs 24h vs 3 losses)
2. Friday Trading Window (Block hr>=12 vs Block hr>=15)
3. Risk-Reward Ratio (1.50 vs 1.65 vs 1.75 vs 2.0)
4. Breakeven Migration (+1.0R to BE vs Pure Fixed TP/SL)
5. Multi-Trade Cooldown (0-bar vs 1-bar)
6. Donchian Sensitivity (7-bar vs 8-bar vs 9-bar)
"""

import pickle
import pandas as pd
import numpy as np

def load_data():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
    df = all_data['XAUUSD'].copy()
    if df['time_dt'].dt.tz is not None:
        df['time_dt'] = df['time_dt'].dt.tz_localize(None)
    return df

def simulate_exact_gold(
    df,
    donch_len=8,
    fib=0.382,
    max_hunt=8,
    cooldown=1,
    rr=1.75,
    sl_buffer=0.35,
    min_sl=18.0,
    max_sl=25.0,
    cb_losses=2,
    cb_pause_hours=48,
    fri_cutoff_hour=12,
    toxic_hours=[0, 4, 15, 16, 19],
    be_r=None,
    start_date='2026-03-15'
):
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
    
    c_df['don_h'] = c_df['high'].shift(1).rolling(donch_len).max()
    c_df['don_l'] = c_df['low'].shift(1).rolling(donch_len).min()
    
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
    
    for i in range(start_idx, len(c_df)):
        if state != 0:
            hold = i - entry_idx
            if hold >= 1:
                init_sl_dist = abs(entry_price - orig_sl)
                # Check BE
                if be_r is not None:
                    if state == 1 and (h[i-1] - entry_price) >= (init_sl_dist * be_r):
                        sl_price = max(sl_price, entry_price)
                    elif state == -1 and (entry_price - l[i-1]) >= (init_sl_dist * be_r):
                        sl_price = min(sl_price, entry_price)
                        
                exit_trig = False
                exit_type = None
                exit_p = 0.0
                
                if state == 1:
                    if h[i] >= tp_price and l[i] <= sl_price:
                        exit_trig = True
                        exit_p = sl_price
                        exit_type = 'WIN' if exit_p >= entry_price else 'LOSS'
                    elif h[i] >= tp_price:
                        exit_trig = True
                        exit_p = tp_price
                        exit_type = 'WIN'
                    elif l[i] <= sl_price:
                        exit_trig = True
                        exit_p = sl_price
                        exit_type = 'BE' if abs(exit_p - entry_price) < 0.01 else ('WIN' if exit_p > entry_price else 'LOSS')
                    elif hold >= 160:
                        exit_trig = True
                        exit_p = c[i]
                        exit_type = 'WIN' if exit_p >= entry_price else 'LOSS'
                elif state == -1:
                    if l[i] <= tp_price and h[i] >= sl_price:
                        exit_trig = True
                        exit_p = sl_price
                        exit_type = 'WIN' if exit_p <= entry_price else 'LOSS'
                    elif l[i] <= tp_price:
                        exit_trig = True
                        exit_p = tp_price
                        exit_type = 'WIN'
                    elif h[i] >= sl_price:
                        exit_trig = True
                        exit_p = sl_price
                        exit_type = 'BE' if abs(exit_p - entry_price) < 0.01 else ('WIN' if exit_p < entry_price else 'LOSS')
                    elif hold >= 160:
                        exit_trig = True
                        exit_p = c[i]
                        exit_type = 'WIN' if exit_p <= entry_price else 'LOSS'
                        
                if exit_trig:
                    if exit_type == 'WIN':
                        r_res = rr if exit_p == tp_price else ((exit_p - entry_price) / init_sl_dist if state == 1 else (entry_price - exit_p) / init_sl_dist)
                    elif exit_type == 'BE':
                        r_res = 0.0
                    else:
                        r_res = -1.0
                        
                    trades.append({
                        'entry_time': times[entry_idx],
                        'exit_time': times[i],
                        'entry_dt': pd.to_datetime(times[entry_idx]),
                        'exit_dt': pd.to_datetime(times[i]),
                        'hold_bars': hold,
                        'result': 'WIN' if r_res > 0 else ('LOSS' if r_res < 0 else 'BE'),
                        'r': r_res,
                        'pnl': 50.0 * r_res
                    })
                    state = 0
                    last_exit_idx = i
                    if r_res > 0:
                        consec_losses = 0
                    elif r_res < 0:
                        consec_losses += 1
                        if consec_losses >= cb_losses:
                            lockout_until = i + cb_pause_hours
                            consec_losses = 0
                    continue

        if i < lockout_until or (i - last_exit_idx) < cooldown:
            continue
            
        hr = hours[i]
        wday = weekdays[i]
        is_fri_pm = (wday == 'Friday') and (hr >= fri_cutoff_hour)
        in_active_hours = (hr != 21) and not is_fri_pm and (hr not in toxic_hours)
        
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

def eval_simulation_metrics(trades, risk_pct=1.0, account_size=5000.0, max_dd_pct=8.0):
    if len(trades) < 15:
        return None
    tdf = pd.DataFrame(trades)
    n = len(tdf)
    cash_r = account_size * (risk_pct / 100.0)
    max_dd = account_size * (max_dd_pct / 100.0)
    
    p1_days = []
    p2_days = []
    tot_days = []
    p1_trades = []
    p2_trades = []
    breaches = 0
    runs = 0
    
    step = 1 if n < 100 else 2
    for start_i in range(0, n - 15, step):
        runs += 1
        # Phase 1: Target $400
        p1_cum = 0.0
        p1_i = start_i
        p1_pass = False
        p1_peak = 0.0
        
        while p1_i < n:
            pnl = tdf.iloc[p1_i]['r'] * cash_r
            p1_cum += pnl
            p1_peak = max(p1_peak, p1_cum)
            if (p1_peak - p1_cum) >= max_dd:
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
        
        # Phase 2: Target $250
        p2_start_i = p1_i + 1
        p2_cum = 0.0
        p2_i = p2_start_i
        p2_pass = False
        p2_peak = 0.0
        
        while p2_i < n:
            pnl = tdf.iloc[p2_i]['r'] * cash_r
            p2_cum += pnl
            p2_peak = max(p2_peak, p2_cum)
            if (p2_peak - p2_cum) >= max_dd:
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
        
        tot_d = p1_d + 1 + p2_d + 1 + 14
        
        p1_days.append(p1_d)
        p2_days.append(p2_d)
        tot_days.append(tot_d)
        p1_trades.append(p1_tr)
        p2_trades.append(p2_tr)
        
    pass_rate = (len(tot_days) / runs * 100.0) if runs > 0 else 0.0
    wins = (tdf['result'] == 'WIN').sum()
    wr = (wins / n) * 100.0
    win_r = tdf[tdf['result'] == 'WIN']['r'].sum()
    loss_r = abs(tdf[tdf['result'] == 'LOSS']['r'].sum())
    pf = win_r / loss_r if loss_r > 0 else 99.0
    
    # Calculate Max Equity Drawdown across the entire backtest sequence
    equity = 0.0
    peak = 0.0
    max_drawdown_dollars = 0.0
    for r in tdf['r']:
        equity += r * cash_r
        peak = max(peak, equity)
        dd = peak - equity
        if dd > max_drawdown_dollars:
            max_drawdown_dollars = dd
            
    max_dd_pct_recorded = (max_drawdown_dollars / account_size) * 100.0
    
    return {
        'total_trades': n,
        'wr': wr,
        'pf': pf,
        'max_dd_dollars': max_drawdown_dollars,
        'max_dd_pct': max_dd_pct_recorded,
        'p1_days_med': np.median(p1_days) if p1_days else 999,
        'p2_days_med': np.median(p2_days) if p2_days else 999,
        'tot_days_med': np.median(tot_days) if tot_days else 999,
        'p1_tr_med': np.median(p1_trades) if p1_trades else 999,
        'pass_rate': pass_rate
    }

def run_investigation():
    df = load_data()
    
    print("=" * 120)
    print("STRATEGY LEVER AUDIT: COMPARISON OF CANDIDATE STRATEGY IMPROVEMENTS (RECENT 6 MONTHS: 28 WEEKS)")
    print("=" * 120)
    
    scenarios = [
        ("1. Benchmark (Current Active Strategy)", {}),
        
        # Lever 1: Circuit Breaker Duration Calibration
        ("2. CB Duration: 24h Pause instead of 48h", {'cb_pause_hours': 24}),
        ("3. CB Threshold: 3 Losses instead of 2 (48h pause)", {'cb_losses': 3}),
        ("4. CB Threshold: 3 Losses + 24h pause", {'cb_losses': 3, 'cb_pause_hours': 24}),
        
        # Lever 2: Friday Trading Hours
        ("5. Friday Trading: Allow up to 15:00 UTC (Cutoff 15:00)", {'fri_cutoff_hour': 15}),
        
        # Lever 3: Risk Reward Variations
        ("6. Risk-Reward 1.65:1 (Faster TP Targets)", {'rr': 1.65}),
        ("7. Risk-Reward 1.50:1 (High Precision Speed)", {'rr': 1.50}),
        ("8. Risk-Reward 2.00:1 (Extended Runner)", {'rr': 2.00}),
        
        # Lever 4: Donchian Length
        ("9. 7-Bar Donchian (Faster Hunt Window)", {'donch_len': 7}),
        
        # Lever 5: Breakeven Protection
        ("10. Move SL to BE at +1.0R", {'be_r': 1.0}),
        
        # Lever 6: Synergistic Combination
        ("11. Composite Winner (CB 24h + Fri 15h + RR 1.75)", {'cb_pause_hours': 24, 'fri_cutoff_hour': 15}),
        ("12. Composite High Speed (CB 24h + Fri 15h + RR 1.65)", {'cb_pause_hours': 24, 'fri_cutoff_hour': 15, 'rr': 1.65})
    ]
    
    rows = []
    for name, kwargs in scenarios:
        trades = simulate_exact_gold(df, **kwargs)
        res = eval_simulation_metrics(trades, risk_pct=1.0)
        if res:
            rows.append({
                'Strategy Configuration': name,
                'Trades': res['total_trades'],
                'Freq/Wk': f"{res['total_trades']/28.0:.2f}",
                'Win Rate': f"{res['wr']:.1f}%",
                'Profit Factor': f"{res['pf']:.2f}",
                'Max DD ($)': f"${res['max_dd_dollars']:.0f} ({res['max_dd_pct']:.1f}%)",
                'Phase 1 (Days)': f"{res['p1_days_med']:.0f} d (~{res['p1_days_med']/7:.1f} w)",
                'Phase 2 (Days)': f"{res['p2_days_med']:.0f} d",
                'Payout (Days)': f"{res['tot_days_med']:.0f} d (~{res['tot_days_med']/30:.1f} mo)",
                'Pass Rate': f"{res['pass_rate']:.1f}%"
            })
            
    print(pd.DataFrame(rows).to_string(index=False))

    # Also test top candidates on the FULL 2-YEAR HISTORICAL DATASET
    print("\n" + "=" * 120)
    print("FULL 2-YEAR HISTORICAL VALIDATION (104 WEEKS: 2024 - 2026)")
    print("=" * 120)
    
    top_candidates = [
        ("1. Benchmark (Current Active Strategy)", {}),
        ("2. CB Duration: 24h Pause instead of 48h", {'cb_pause_hours': 24}),
        ("5. Friday Trading: Cutoff 15:00 UTC", {'fri_cutoff_hour': 15}),
        ("6. Risk-Reward 1.65:1", {'rr': 1.65}),
        ("11. Composite Winner (CB 24h + Fri 15h)", {'cb_pause_hours': 24, 'fri_cutoff_hour': 15}),
        ("12. Composite High Speed (CB 24h + Fri 15h + RR 1.65)", {'cb_pause_hours': 24, 'fri_cutoff_hour': 15, 'rr': 1.65})
    ]
    
    rows_2y = []
    for name, kwargs in top_candidates:
        trades_2y = simulate_exact_gold(df, start_date=None, **kwargs)
        res_2y = eval_simulation_metrics(trades_2y, risk_pct=1.0)
        if res_2y:
            rows_2y.append({
                'Strategy Configuration': name,
                'Trades': res_2y['total_trades'],
                'Freq/Wk': f"{res_2y['total_trades']/104.0:.2f}",
                'Win Rate': f"{res_2y['wr']:.1f}%",
                'Profit Factor': f"{res_2y['pf']:.2f}",
                'Max DD ($)': f"${res_2y['max_dd_dollars']:.0f} ({res_2y['max_dd_pct']:.1f}%)",
                'Phase 1 (Days)': f"{res_2y['p1_days_med']:.0f} d (~{res_2y['p1_days_med']/7:.1f} w)",
                'Payout (Days)': f"{res_2y['tot_days_med']:.0f} d (~{res_2y['tot_days_med']/30:.1f} mo)",
                'Pass Rate': f"{res_2y['pass_rate']:.1f}%"
            })
            
    print(pd.DataFrame(rows_2y).to_string(index=False))

if __name__ == '__main__':
    run_investigation()
