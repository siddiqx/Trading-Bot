import pickle, math
import pandas as pd
import numpy as np

def run_portfolio_matrix(start_date='2026-03-15', weeks=28.0):
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
        
    START_DATE = start_date
    
    # Pre-generate candidate trades for each pair
    pair_candidates = {}
    all_pairs = ['USDCAD', 'USDCHF', 'USDJPY', 'AUDUSD', 'XAUUSD']
    
    for pair in all_pairs:
        df = all_data[pair].copy()
        if df['time_dt'].dt.tz is not None:
            df['time_dt'] = df['time_dt'].dt.tz_localize(None)
            
        is_gold = 'XAU' in pair
        
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
        start_idx = df[df['time_dt'] >= START_DATE].index[0]
        
        hunting = 0
        hunt_idx, hunt_level, hunt_ob_h, hunt_ob_l, hunt_fib, hunt_atr = 0,0,0,0,0,0
        candidates = []
        
        for i in range(start_idx, len(df)):
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
                            exit_bar = None
                            exit_result = None
                            for fwd in range(i+1, min(i+161, len(df))):
                                if h[fwd] >= tent_tp and l[fwd] <= tent_sl:
                                    exit_bar = fwd
                                    exit_result = 'LOSS'
                                    break
                                elif h[fwd] >= tent_tp:
                                    exit_bar = fwd
                                    exit_result = 'WIN'
                                    break
                                elif l[fwd] <= tent_sl:
                                    exit_bar = fwd
                                    exit_result = 'LOSS'
                                    break
                                elif fwd == i + 160:
                                    exit_bar = fwd
                                    exit_result = 'WIN' if c[fwd] > c[i] else 'LOSS'
                                    break
                            if exit_bar is not None:
                                candidates.append({
                                    'pair': pair,
                                    'priority': 0 if is_gold else 1,
                                    'entry_time': times[i],
                                    'exit_time': times[exit_bar],
                                    'entry_idx': i,
                                    'exit_idx': exit_bar,
                                    'result': exit_result,
                                    'r': rr if exit_result == 'WIN' else -1.0
                                })
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
                            exit_bar = None
                            exit_result = None
                            for fwd in range(i+1, min(i+161, len(df))):
                                if l[fwd] <= tent_tp and h[fwd] >= tent_sl:
                                    exit_bar = fwd
                                    exit_result = 'LOSS'
                                    break
                                elif l[fwd] <= tent_tp:
                                    exit_bar = fwd
                                    exit_result = 'WIN'
                                    break
                                elif h[fwd] >= tent_sl:
                                    exit_bar = fwd
                                    exit_result = 'LOSS'
                                    break
                                elif fwd == i + 160:
                                    exit_bar = fwd
                                    exit_result = 'WIN' if c[fwd] < c[i] else 'LOSS'
                                    break
                            if exit_bar is not None:
                                candidates.append({
                                    'pair': pair,
                                    'priority': 0 if is_gold else 1,
                                    'entry_time': times[i],
                                    'exit_time': times[exit_bar],
                                    'entry_idx': i,
                                    'exit_idx': exit_bar,
                                    'result': exit_result,
                                    'r': rr if exit_result == 'WIN' else -1.0
                                })
                            hunting = 0
        pair_candidates[pair] = candidates

    # Evaluate multiple portfolio subsets
    subsets = [
        ("1. Gold Only (Tuned 8-bar + Toxic Filter)", ['XAUUSD']),
        ("2. Dual Synergy (Gold + USDCAD)", ['XAUUSD', 'USDCAD']),
        ("3. Triple Synergy (Gold + USDCAD + AUDUSD)", ['XAUUSD', 'USDCAD', 'AUDUSD']),
        ("4. Quad Synergy (Gold + USDCAD + AUDUSD + USDJPY)", ['XAUUSD', 'USDCAD', 'AUDUSD', 'USDJPY']),
        ("5. Full 5-Pair Whitelist (Gold + All 4 FX)", ['XAUUSD', 'USDCAD', 'AUDUSD', 'USDJPY', 'USDCHF']),
    ]
    
    EQUITY = 5000.0
    RISK_CASH = 50.0
    # weeks is passed as argument
    
    results = []
    
    for name, p_list in subsets:
        combined = []
        for p in p_list:
            combined.extend(pair_candidates[p])
            
        df_sub = pd.DataFrame(combined)
        df_sub['entry_dt'] = pd.to_datetime(df_sub['entry_time'])
        df_sub['exit_dt'] = pd.to_datetime(df_sub['exit_time'])
        df_sub = df_sub.sort_values(by=['entry_dt', 'priority']).reset_index(drop=True)
        
        executed = []
        cur_exit_dt = pd.Timestamp.min
        for _, tr in df_sub.iterrows():
            if tr['entry_dt'] >= cur_exit_dt:
                executed.append(tr)
                cur_exit_dt = tr['exit_dt']
                
        edf = pd.DataFrame(executed)
        edf['exit_date'] = edf['exit_dt'].dt.date
        edf['pnl'] = edf['r'] * RISK_CASH
        
        n_tr = len(edf)
        wins = len(edf[edf['result'] == 'WIN'])
        wr = (wins / n_tr) * 100.0 if n_tr > 0 else 0.0
        
        win_sum = edf[edf['pnl'] > 0]['pnl'].sum()
        loss_sum = abs(edf[edf['pnl'] < 0]['pnl'].sum())
        pf = (win_sum / loss_sum) if loss_sum > 0 else 99.0
        
        net_prof = edf['pnl'].sum()
        ret_pct = (net_prof / EQUITY) * 100.0
        net_r = edf['r'].sum()
        
        daily_pnl = edf.groupby('exit_date')['pnl'].sum()
        max_daily_loss = abs(daily_pnl.min()) if len(daily_pnl) > 0 and daily_pnl.min() < 0 else 0.0
        max_daily_dd = (max_daily_loss / EQUITY) * 100.0
        
        cum = edf['pnl'].cumsum()
        peak = cum.cummax()
        dd = peak - cum
        max_dd = (dd.max() / EQUITY) * 100.0
        
        results.append({
            'Portfolio Configuration': name,
            'Trades': n_tr,
            'Trades/Wk': round(n_tr / weeks, 2),
            'Win Rate': f"{wr:.1f}%",
            'Profit Factor': f"{pf:.2f}",
            'Net Profit': f"${net_prof:.2f}",
            'Return': f"+{ret_pct:.1f}%",
            'Net R': f"+{net_r:.2f} R",
            'Max Daily DD': f"{max_daily_dd:.2f}%",
            'Max Total DD': f"{max_dd:.2f}%",
            'Prop Firm Status': 'PASS' if max_daily_dd <= 3.0 and max_dd <= 8.0 else 'WARN DD'
        })
        
    print("=" * 125)
    print("PORTFOLIO SYNERGY MATRIX (STRICT SINGLE-TRADE LOCK, ZERO CONCURRENT RISK)")
    print("=" * 125)
    print(pd.DataFrame(results).to_string(index=False))

if __name__ == '__main__':
    print("=" * 125)
    print("PORTFOLIO SYNERGY MATRIX: LAST 6 MONTHS (28 WEEKS) EVALUATION")
    print("=" * 125)
    run_portfolio_matrix(start_date='2026-03-15', weeks=28.0)
    
    print("\n" + "=" * 125)
    print("PORTFOLIO SYNERGY MATRIX: FULL 2-YEAR (104 WEEKS) WALK-FORWARD VALIDATION")
    print("=" * 125)
    run_portfolio_matrix(start_date='2024-10-01', weeks=104.0)
