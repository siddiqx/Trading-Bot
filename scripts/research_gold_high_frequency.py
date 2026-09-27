import pickle, math
import pandas as pd
import numpy as np

with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
    all_data = pickle.load(f)
    
df_raw = all_data['XAUUSD'].copy()
if df_raw['time_dt'].dt.tz is not None:
    df_raw['time_dt'] = df_raw['time_dt'].dt.tz_localize(None)
    
START_DATE = '2026-03-15'

def test_gold_high_freq_engine(
    donch_len=10,
    retrace_fib=0.382, # 38.2% Fib pullback
    sl_atr_buffer=0.35, # Tighter 0.35 ATR buffer
    min_sl=15.0,        # Min SL $15
    max_sl=28.0,        # Max SL $28
    rr=1.75,
    cooldown=1,         # 1 bar cooldown
    max_hunt=10,        # Up to 10 bars wait for pullback
    require_rejection=True,
    body_ratio_min=0.30
):
    df = df_raw.copy()
    
    # 1H Indicators
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
    hunting, hunt_idx, hunt_level, hunt_ob_h, hunt_ob_l, hunt_fib, hunt_atr = 0,0,0,0,0,0,0
    last_exit_idx = -999
    lockout_until = 0
    consec_losses = 0
    
    start_idx = df[df['time_dt'] >= START_DATE].index[0]
    
    for i in range(start_idx, len(df)):
        if state != 0:
            hold = i - entry_idx
            if hold >= 1:
                exit_trig, exit_type, exit_price = False, None, 0.0
                if state == 1:
                    if h[i] >= tp_price and l[i] <= sl_price: exit_trig, exit_type, exit_price = True, 'LOSS', sl_price
                    elif h[i] >= tp_price: exit_trig, exit_type, exit_price = True, 'WIN', tp_price
                    elif l[i] <= sl_price: exit_trig, exit_type, exit_price = True, 'LOSS', sl_price
                    elif hold >= 160: exit_trig, exit_price, exit_type = True, c[i], ('WIN' if c[i]>entry_price else 'LOSS')
                elif state == -1:
                    if l[i] <= tp_price and h[i] >= sl_price: exit_trig, exit_type, exit_price = True, 'LOSS', sl_price
                    elif l[i] <= tp_price: exit_trig, exit_type, exit_price = True, 'WIN', tp_price
                    elif h[i] >= sl_price: exit_trig, exit_type, exit_price = True, 'LOSS', sl_price
                    elif hold >= 160: exit_trig, exit_price, exit_type = True, c[i], ('WIN' if c[i]<entry_price else 'LOSS')
                if exit_trig:
                    sl_dist = abs(entry_price - sl_price)
                    p_diff = (exit_price - entry_price) * (1.0 if state==1 else -1.0)
                    trades.append({'res': exit_type, 'sl_dist': sl_dist, 'p_diff': p_diff, 'exit_time': times[i]})
                    state = 0
                    last_exit_idx = i
                    if exit_type == 'WIN': consec_losses = 0
                    else:
                        consec_losses += 1
                        if consec_losses >= 2: lockout_until = i + 48; consec_losses = 0
                    continue
                    
        if i < lockout_until or (i - last_exit_idx) < cooldown: continue
        hr = hours[i]
        wday = weekdays[i]
        in_act = (hr != 21) and not (wday == 'Friday' and hr >= 12)
        
        slope_thresh = 0.08 * atr[i]
        h1_slope_bull = e20_slope[i] >= slope_thresh
        h1_slope_bear = -e20_slope[i] >= slope_thresh
        
        trend_bull = (c[i] > e50[i]) and (e20[i] > e50[i]) and h1_slope_bull and h4_bull[i]
        trend_bear = (c[i] < e50[i]) and (e20[i] < e50[i]) and h1_slope_bear and h4_bear[i]
        
        rng = max(h[i] - l[i], 1e-6)
        body_long = (c[i] - l[i]) / rng
        body_short = (h[i] - c[i]) / rng
        
        long_break = trend_bull and (c[i] > don_h[i]) and (c[i-1] <= don_h[i-1]) and in_act and (body_long >= body_ratio_min)
        short_break = trend_bear and (c[i] < don_l[i]) and (c[i-1] >= don_l[i-1]) and in_act and (body_short >= body_ratio_min)
        
        if hunting == 0:
            if long_break:
                hunting, hunt_idx = 1, i
                hunt_level = don_h[i]
                hunt_ob_l = l[i-1] if c[i-1] < o[i-1] else l[i]
                hunt_ob_h = h[i-1] if c[i-1] < o[i-1] else h[i]
                hunt_fib = h[i] - retrace_fib * (h[i] - hunt_ob_l)
                hunt_atr = atr[i]
            elif short_break:
                hunting, hunt_idx = -1, i
                hunt_level = don_l[i]
                hunt_ob_h = h[i-1] if c[i-1] > o[i-1] else h[i]
                hunt_ob_l = l[i-1] if c[i-1] > o[i-1] else l[i]
                hunt_fib = l[i] + retrace_fib * (hunt_ob_h - l[i])
                hunt_atr = atr[i]
        else:
            if (i - hunt_idx) > max_hunt: hunting = 0
            elif hunting == 1:
                retrace = (l[i] <= hunt_fib) or (l[i] <= hunt_ob_h) or (l[i] <= hunt_level * 1.0005) or (l[i] <= e20[i])
                rejection = (c[i] > o[i]) if require_rejection else True
                rsi_ok = rsi[i] <= 82.0
                if retrace and rejection and rsi_ok and in_act:
                    raw_sl = hunt_ob_l - (hunt_atr * sl_atr_buffer)
                    calc_dist = abs(c[i] - raw_sl)
                    act_sl = min(max(calc_dist, min_sl), max_sl)
                    tent_sl = c[i] - act_sl
                    tent_tp = c[i] + (act_sl * rr)
                    if h[i] < tent_tp:
                        state, hunting = 1, 0
                        entry_price, sl_price, tp_price, entry_idx = c[i], tent_sl, tent_tp, i
                    else: hunting = 0
            elif hunting == -1:
                retrace = (h[i] >= hunt_fib) or (h[i] >= hunt_ob_l) or (h[i] >= hunt_level * 0.9995) or (h[i] >= e20[i])
                rejection = (c[i] < o[i]) if require_rejection else True
                rsi_ok = rsi[i] >= 18.0
                if retrace and rejection and rsi_ok and in_act:
                    raw_sl = hunt_ob_h + (hunt_atr * sl_atr_buffer)
                    calc_dist = abs(raw_sl - c[i])
                    act_sl = min(max(calc_dist, min_sl), max_sl)
                    tent_sl = c[i] + act_sl
                    tent_tp = c[i] - (act_sl * rr)
                    if l[i] > tent_tp:
                        state, hunting = -1, 0
                        entry_price, sl_price, tp_price, entry_idx = c[i], tent_sl, tent_tp, i
                    else: hunting = 0
                    
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
        gross = lots * 100.0 * tr['p_diff']
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

if __name__ == '__main__':
    tests = [
        ('1. Baseline (20-bar Donchian, 0.50 ATR, 8 Hunt)', {'donch_len': 20, 'retrace_fib': 0.50, 'sl_atr_buffer': 0.50, 'cooldown': 3, 'max_hunt': 8}),
        ('2. Fast 10-bar Donchian (0.50 ATR, 1 Cooldown, 6 Hunt)', {'donch_len': 10, 'retrace_fib': 0.50, 'sl_atr_buffer': 0.50, 'cooldown': 1, 'max_hunt': 6}),
        ('3. Responsive 8-bar Donchian (0.35 ATR, 38.2% Fib, 10 Hunt)', {'donch_len': 8, 'retrace_fib': 0.382, 'sl_atr_buffer': 0.35, 'cooldown': 1, 'max_hunt': 10}),
        ('4. Responsive 7-bar Donchian (0.35 ATR, 38.2% Fib, 8 Hunt)', {'donch_len': 7, 'retrace_fib': 0.382, 'sl_atr_buffer': 0.35, 'cooldown': 1, 'max_hunt': 8}),
        ('5. Responsive 6-bar Donchian (0.35 ATR, 38.2% Fib, 8 Hunt)', {'donch_len': 6, 'retrace_fib': 0.382, 'sl_atr_buffer': 0.35, 'cooldown': 1, 'max_hunt': 8}),
        ('6. Fast 8-bar Donchian + 1.65 R:R Target', {'donch_len': 8, 'retrace_fib': 0.382, 'sl_atr_buffer': 0.35, 'cooldown': 1, 'max_hunt': 8, 'rr': 1.65}),
        ('7. Fast 8-bar Donchian + 1.50 R:R Target', {'donch_len': 8, 'retrace_fib': 0.382, 'sl_atr_buffer': 0.35, 'cooldown': 1, 'max_hunt': 8, 'rr': 1.50}),
    ]
    
    rows = []
    for label, cfg in tests:
        res = test_gold_high_freq_engine(**cfg)
        res['configuration'] = label
        rows.append(res)
        
    df_res = pd.DataFrame(rows)[['configuration', 'trades', 'freq_wk', 'win_rate', 'profit_factor', 'net_profit', 'return_pct', 'net_r', 'max_daily_dd', 'max_overall_dd']]
    print("="*105)
    print("GOLD HIGH-FREQUENCY EXPERIMENTAL TEST MATRIX (LAST 6 MONTHS)")
    print("="*105)
    print(df_res.to_string(index=False))
