"""
DEEP STRATEGY SPEEDUP RESEARCH:
Rigorous empirical backtest and rolling prop simulation across 2 full years (2024-2026)
and recent 6 months to determine if strategy-level improvements can speed up Phase 1, Phase 2,
and First Payout without degrading win rate or profit factor below current performance.
"""

import pickle
import math
import pandas as pd
import numpy as np

def load_data():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        data = pickle.load(f)
    df = data['XAUUSD'].copy()
    if df['time_dt'].dt.tz is not None:
        df['time_dt'] = df['time_dt'].dt.tz_localize(None)
    return df

def simulate_strategy(
    df,
    donch_len=8,
    fib_retrace=0.382,
    max_hunt=8,
    cooldown=1,
    sl_buffer=0.35,
    min_sl=18.0,
    max_sl=25.0,
    rr=1.75,
    toxic_hours=[0, 4, 15, 16, 19],
    allow_prime_only=False, # London (7-11) & NY (13-18)
    be_trigger_r=None,      # e.g., move SL to BE at +1.0R
    trail_ema=False,        # trail stop along EMA20 after 1.0R
    direct_momentum=False,  # enter on breakout close if candle body > 0.50
    start_date='2026-03-15'
):
    c_df = df.copy()
    
    # Technical Indicators
    c_df['e20'] = c_df['close'].ewm(span=20, adjust=False).mean()
    c_df['e50'] = c_df['close'].ewm(span=50, adjust=False).mean()
    c_df['e20_slope'] = c_df['e20'] - c_df['e20'].shift(2)
    
    tr = np.maximum(
        c_df['high'] - c_df['low'],
        np.maximum(
            np.abs(c_df['high'] - c_df['close'].shift(1)),
            np.abs(c_df['low'] - c_df['close'].shift(1))
        )
    )
    c_df['atr'] = pd.Series(tr).rolling(14).mean().bfill()
    
    delta = c_df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / (loss.rolling(14).mean() + 1e-9)
    c_df['rsi'] = (100 - (100 / (1 + rs))).bfill()
    
    # Donchian
    c_df['don_h'] = c_df['high'].shift(1).rolling(donch_len).max()
    c_df['don_l'] = c_df['low'].shift(1).rolling(donch_len).min()
    
    # 4H EMA Trend Filter
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
    don_h = c_df['don_h'].values
    don_l = c_df['don_l'].values
    hours = c_df['time_dt'].dt.hour.values
    times = c_df['time_dt'].values
    
    if start_date:
        start_idx = c_df[c_df['time_dt'] >= start_date].index[0]
    else:
        start_idx = 100
        
    trades = []
    state = 0
    entry_price, sl_price, orig_sl_price, tp_price, entry_idx = 0.0, 0.0, 0.0, 0.0, 0
    hunting = 0
    hunt_idx, hunt_level, hunt_ob_h, hunt_ob_l, hunt_fib, hunt_atr = 0, 0.0, 0.0, 0.0, 0.0, 0.0
    last_exit_idx = -999
    
    for i in range(start_idx, len(c_df)):
        # Active Trade Management
        if state != 0:
            hold = i - entry_idx
            if hold >= 1:
                init_sl_dist = abs(entry_price - orig_sl_price)
                
                # Breakeven adjustment
                if be_trigger_r is not None:
                    if state == 1 and (h[i-1] - entry_price) >= (init_sl_dist * be_trigger_r):
                        sl_price = max(sl_price, entry_price)
                    elif state == -1 and (entry_price - l[i-1]) >= (init_sl_dist * be_trigger_r):
                        sl_price = min(sl_price, entry_price)
                        
                # Trailing stop along EMA20
                if trail_ema:
                    if state == 1 and (h[i-1] - entry_price) >= (init_sl_dist * 1.0):
                        sl_price = max(sl_price, e20[i-1])
                    elif state == -1 and (entry_price - l[i-1]) >= (init_sl_dist * 1.0):
                        sl_price = min(sl_price, e20[i-1])
                
                if state == 1:
                    is_tp = h[i] >= tp_price
                    is_sl = l[i] <= sl_price
                    if is_tp or is_sl:
                        exit_price = tp_price if is_tp else sl_price
                        res = 'WIN' if exit_price >= entry_price else 'LOSS'
                        r_mult = (exit_price - entry_price) / init_sl_dist
                        trades.append({
                            'entry_dt': times[entry_idx],
                            'exit_dt': times[i],
                            'dir': 'BUY',
                            'entry': entry_price,
                            'exit': exit_price,
                            'pips': exit_price - entry_price,
                            'r': r_mult,
                            'result': res,
                            'hold_bars': hold
                        })
                        state = 0
                        last_exit_idx = i
                        continue
                elif state == -1:
                    is_tp = l[i] <= tp_price
                    is_sl = h[i] >= sl_price
                    if is_tp or is_sl:
                        exit_price = tp_price if is_tp else sl_price
                        res = 'WIN' if exit_price <= entry_price else 'LOSS'
                        r_mult = (entry_price - exit_price) / init_sl_dist
                        trades.append({
                            'entry_dt': times[entry_idx],
                            'exit_dt': times[i],
                            'dir': 'SELL',
                            'entry': entry_price,
                            'exit': exit_price,
                            'pips': entry_price - exit_price,
                            'r': r_mult,
                            'result': res,
                            'hold_bars': hold
                        })
                        state = 0
                        last_exit_idx = i
                        continue
                        
        # Entry Logic
        if state == 0 and (i - last_exit_idx) >= cooldown:
            hr = hours[i]
            in_toxic = hr in toxic_hours
            if allow_prime_only:
                in_active_hours = (7 <= hr <= 11) or (13 <= hr <= 18)
            else:
                in_active_hours = not in_toxic
                
            long_setup = (c[i] > don_h[i]) and (c[i] > e20[i]) and (e20[i] > e50[i]) and (e20_slope[i] > 0) and h4_bull[i] and (rsi[i] <= 70.0)
            short_setup = (c[i] < don_l[i]) and (c[i] < e20[i]) and (e20[i] < e50[i]) and (e20_slope[i] < 0) and h4_bear[i] and (rsi[i] >= 30.0)
            
            # Direct Momentum Option
            if direct_momentum and in_active_hours:
                body_ratio = abs(c[i] - o[i]) / (h[i] - l[i] + 1e-9)
                if long_setup and body_ratio >= 0.50:
                    raw_sl = min(l[i], l[i-1]) - (atr[i] * sl_buffer)
                    calc_dist = abs(c[i] - raw_sl)
                    act_sl_dist = min(max(calc_dist, min_sl), max_sl)
                    state = 1
                    entry_price = c[i]
                    orig_sl_price = c[i] - act_sl_dist
                    sl_price = orig_sl_price
                    tp_price = c[i] + (act_sl_dist * rr)
                    entry_idx = i
                    continue
                elif short_setup and body_ratio >= 0.50:
                    raw_sl = max(h[i], h[i-1]) + (atr[i] * sl_buffer)
                    calc_dist = abs(raw_sl - c[i])
                    act_sl_dist = min(max(calc_dist, min_sl), max_sl)
                    state = -1
                    entry_price = c[i]
                    orig_sl_price = c[i] + act_sl_dist
                    sl_price = orig_sl_price
                    tp_price = c[i] - (act_sl_dist * rr)
                    entry_idx = i
                    continue

            # Standard Retracement Hunting Logic
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
                        act_sl_dist = min(max(calc_dist, min_sl), max_sl)
                        tent_sl = c[i] - act_sl_dist
                        tent_tp = c[i] + (act_sl_dist * rr)
                        if h[i] < tent_tp:
                            state = 1
                            hunting = 0
                            entry_price = c[i]
                            orig_sl_price = tent_sl
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
                            orig_sl_price = tent_sl
                            sl_price = tent_sl
                            tp_price = tent_tp
                            entry_idx = i
                        else:
                            hunting = 0
                            
    return trades

def eval_prop_timeline(trades, risk_pct=1.0, account_size=5000.0, max_dd_pct=8.0):
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
    
    step = 1 if n < 100 else 3
    for start_i in range(0, n - 20, step):
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
        
        tot_d = p1_d + 1 + p2_d + 1 + 14 # 14-day funded holding
        
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
    avg_hold = tdf['hold_bars'].mean()
    
    return {
        'total_trades': n,
        'wr': wr,
        'pf': pf,
        'avg_hold_h': avg_hold,
        'p1_days_med': np.median(p1_days) if p1_days else 999,
        'p2_days_med': np.median(p2_days) if p2_days else 999,
        'tot_days_med': np.median(tot_days) if tot_days else 999,
        'pass_rate': pass_rate,
        'p1_tr_med': np.median(p1_trades) if p1_trades else 999,
        'p2_tr_med': np.median(p2_trades) if p2_trades else 999
    }

def run_all_experiments():
    df = load_data()
    print("XAUUSD Loaded:", len(df), "bars.")
    
    # -------------------------------------------------------------
    # EXPERIMENT 1: RISK-REWARD (RR) OPTIMIZATION
    # -------------------------------------------------------------
    print("\n" + "=" * 100)
    print("EXPERIMENT 1: RISK-REWARD (RR) RATIO SWEEP ON GOLD")
    print("=" * 100)
    rr_vals = [1.25, 1.40, 1.50, 1.60, 1.75, 2.00, 2.25]
    exp1_rows = []
    for r in rr_vals:
        trades = simulate_strategy(df, rr=r, start_date='2026-03-15')
        stats = eval_prop_timeline(trades, risk_pct=1.0)
        exp1_rows.append({
            'RR Ratio': f"{r:.2f}:1",
            'Trades': stats['total_trades'],
            'Win Rate': f"{stats['wr']:.1f}%",
            'Profit Factor': f"{stats['pf']:.2f}",
            'Avg Hold (Hrs)': f"{stats['avg_hold_h']:.1f}h",
            'Phase 1 (Days)': f"{stats['p1_days_med']:.0f} d",
            'Phase 2 (Days)': f"{stats['p2_days_med']:.0f} d",
            'Total Payout (Days)': f"{stats['tot_days_med']:.0f} d",
            'Pass Rate': f"{stats['pass_rate']:.1f}%"
        })
    print(pd.DataFrame(exp1_rows).to_string(index=False))
    
    # -------------------------------------------------------------
    # EXPERIMENT 2: DONCHIAN LOOKBACK & FIBONACCI RETRACEMENT
    # -------------------------------------------------------------
    print("\n" + "=" * 100)
    print("EXPERIMENT 2: DONCHIAN LOOKBACK & FIBONACCI SENSITIVITY")
    print("=" * 100)
    param_pairs = [
        (6, 0.382, "6-Bar Donchian, 38.2% Fib"),
        (8, 0.382, "8-Bar Donchian, 38.2% Fib (Benchmark)"),
        (10, 0.382, "10-Bar Donchian, 38.2% Fib"),
        (8, 0.236, "8-Bar Donchian, 23.6% Fib (Shallow)"),
        (8, 0.500, "8-Bar Donchian, 50.0% Fib (Deep)"),
        (6, 0.236, "6-Bar Donchian, 23.6% Fib (Hyper-Fast)"),
    ]
    exp2_rows = []
    for d_len, fib_val, label in param_pairs:
        trades = simulate_strategy(df, donch_len=d_len, fib_retrace=fib_val, start_date='2026-03-15')
        stats = eval_prop_timeline(trades, risk_pct=1.0)
        exp2_rows.append({
            'Configuration': label,
            'Trades': stats['total_trades'],
            'Win Rate': f"{stats['wr']:.1f}%",
            'Profit Factor': f"{stats['pf']:.2f}",
            'Avg Hold (Hrs)': f"{stats['avg_hold_h']:.1f}h",
            'Phase 1 (Days)': f"{stats['p1_days_med']:.0f} d",
            'Total Payout (Days)': f"{stats['tot_days_med']:.0f} d",
            'Pass Rate': f"{stats['pass_rate']:.1f}%"
        })
    print(pd.DataFrame(exp2_rows).to_string(index=False))

    # -------------------------------------------------------------
    # EXPERIMENT 3: BREAKEVEN & TRAILING STOP LOGIC
    # -------------------------------------------------------------
    print("\n" + "=" * 100)
    print("EXPERIMENT 3: ACTIVE TRADE MANAGEMENT (BREAKEVEN & TRAILING STOP)")
    print("=" * 100)
    mgmt_configs = [
        (None, False, "Fixed SL/TP (Benchmark)"),
        (1.0, False, "Move SL to BE at +1.0R"),
        (1.2, False, "Move SL to BE at +1.2R"),
        (1.0, True, "Trail EMA20 after +1.0R"),
    ]
    exp3_rows = []
    for be_val, trail_val, label in mgmt_configs:
        trades = simulate_strategy(df, be_trigger_r=be_val, trail_ema=trail_val, start_date='2026-03-15')
        stats = eval_prop_timeline(trades, risk_pct=1.0)
        exp3_rows.append({
            'Trade Management': label,
            'Trades': stats['total_trades'],
            'Win Rate': f"{stats['wr']:.1f}%",
            'Profit Factor': f"{stats['pf']:.2f}",
            'Phase 1 (Days)': f"{stats['p1_days_med']:.0f} d",
            'Total Payout (Days)': f"{stats['tot_days_med']:.0f} d",
            'Pass Rate': f"{stats['pass_rate']:.1f}%"
        })
    print(pd.DataFrame(exp3_rows).to_string(index=False))

    # -------------------------------------------------------------
    # EXPERIMENT 4: COOLDOWN & SESSION TIMING
    # -------------------------------------------------------------
    print("\n" + "=" * 100)
    print("EXPERIMENT 4: COOLDOWN REDUCTION & SESSION FOCUS")
    print("=" * 100)
    timing_configs = [
        (1, False, "1-Bar Cooldown, Toxic Filter Excluded (Benchmark)"),
        (0, False, "0-Bar Cooldown (Instant Re-Entry)"),
        (1, True, "Prime Sessions Only (London 7-11 & NY 13-18 UTC)"),
    ]
    exp4_rows = []
    for cd_val, prime_val, label in timing_configs:
        trades = simulate_strategy(df, cooldown=cd_val, allow_prime_only=prime_val, start_date='2026-03-15')
        stats = eval_prop_timeline(trades, risk_pct=1.0)
        exp4_rows.append({
            'Timing / Cooldown': label,
            'Trades': stats['total_trades'],
            'Win Rate': f"{stats['wr']:.1f}%",
            'Profit Factor': f"{stats['pf']:.2f}",
            'Phase 1 (Days)': f"{stats['p1_days_med']:.0f} d",
            'Total Payout (Days)': f"{stats['tot_days_med']:.0f} d",
            'Pass Rate': f"{stats['pass_rate']:.1f}%"
        })
    print(pd.DataFrame(exp4_rows).to_string(index=False))

    # -------------------------------------------------------------
    # EXPERIMENT 5: FULL 2-YEAR EXTENDED ROBUSTNESS AUDIT
    # -------------------------------------------------------------
    print("\n" + "=" * 100)
    print("EXPERIMENT 5: FULL 2-YEAR (2024-2026) EXTENDED STRESS TEST")
    print("=" * 100)
    # Test top candidates across the entire 2-year history
    candidates = [
        ("Benchmark (RR 1.75, 8-Donch, 1-Bar CD)", 1.75, 8, 0.382, None),
        ("RR 1.50 Speed Engine (RR 1.50, 8-Donch)", 1.50, 8, 0.382, None),
        ("RR 1.60 Balanced (RR 1.60, 8-Donch)", 1.60, 8, 0.382, None),
        ("Fast 6-Donchian (RR 1.75, 6-Donch)", 1.75, 6, 0.382, None),
    ]
    exp5_rows = []
    for label, r_val, d_val, fib_v, be_v in candidates:
        trades_2y = simulate_strategy(df, rr=r_val, donch_len=d_val, fib_retrace=fib_v, be_trigger_r=be_v, start_date=None)
        stats_2y = eval_prop_timeline(trades_2y, risk_pct=1.0)
        exp5_rows.append({
            'Strategy Candidate (2-Year)': label,
            'Total Trades (2Y)': stats_2y['total_trades'],
            'Win Rate (2Y)': f"{stats_2y['wr']:.1f}%",
            'Profit Factor (2Y)': f"{stats_2y['pf']:.2f}",
            'Phase 1 (Days)': f"{stats_2y['p1_days_med']:.0f} d",
            'Total Payout (Days)': f"{stats_2y['tot_days_med']:.0f} d",
            'Pass Rate (2Y)': f"{stats_2y['pass_rate']:.1f}%"
        })
    print(pd.DataFrame(exp5_rows).to_string(index=False))

if __name__ == '__main__':
    run_all_experiments()
