import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

def run_last_6_months_audit():
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        data = pickle.load(f)
    pairs_data = data[1]
    pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'USDCHF']
    
    cb_bars = 48
    all_trades = []
    
    for pair in pairs:
        if pair not in pairs_data:
            continue
        m15 = pairs_data[pair]['M15'].copy()
        h1 = pairs_data[pair]['H1'].copy()
        d1 = pairs_data[pair]['D1'].copy()
        
        is_jpy = 'JPY' in pair
        pip_unit = 0.01 if is_jpy else 0.0001
        min_sl_dist = 20.0 * pip_unit
        max_sl_dist = 60.0 * pip_unit
        rr = 1.5
        sl_mult = 0.5
        
        # D1 EMA 50
        d1['ema50'] = d1['close'].ewm(span=50, adjust=False).mean()
        d1['time_dt'] = pd.to_datetime(d1['time'], unit='s').dt.floor('D')
        
        # H1 indicators
        h1['time_dt'] = pd.to_datetime(h1['time'], unit='s')
        h1['ema200'] = h1['close'].ewm(span=200, adjust=False).mean()
        h1['ema50'] = h1['close'].ewm(span=50, adjust=False).mean()
        h1['ema20'] = h1['close'].ewm(span=20, adjust=False).mean()
        h1['ema20_slope'] = h1['ema20'] - h1['ema20'].shift(2)
        
        h1['date_only'] = h1['time_dt'].dt.floor('D')
        d1_bull_map = dict(zip(d1['time_dt'], d1['close'] > d1['ema50']))
        h1['d1_bull'] = h1['date_only'].map(d1_bull_map).fillna(False)
        
        h1['h1_bull'] = (h1['close'] > h1['ema200']) & (h1['ema20'] > h1['ema50']) & (h1['d1_bull']) & (h1['ema20_slope'] > 0)
        h1['h1_bear'] = (h1['close'] < h1['ema200']) & (h1['ema20'] < h1['ema50']) & (~h1['d1_bull']) & (h1['ema20_slope'] < 0)
        
        m15['time_dt'] = pd.to_datetime(m15['time'], unit='s')
        m15['h1_time'] = m15['time_dt'].dt.floor('h') - pd.Timedelta(hours=1)
        
        h1_bull_map = dict(zip(h1['time_dt'], h1['h1_bull']))
        h1_bear_map = dict(zip(h1['time_dt'], h1['h1_bear']))
        
        m15['h1_bull'] = m15['h1_time'].map(h1_bull_map).fillna(False).values
        m15['h1_bear'] = m15['h1_time'].map(h1_bear_map).fillna(False).values
        
        close = m15['close'].values
        open_ = m15['open'].values
        high = m15['high'].values
        low = m15['low'].values
        hours = m15['time_dt'].dt.hour.values
        n = len(close)
        
        m15_ema20 = m15['close'].ewm(span=20, adjust=False).mean().values
        m15_ema50 = m15['close'].ewm(span=50, adjust=False).mean().values
        
        tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
        tr[0] = high[0] - low[0]
        atr14 = pd.Series(tr).rolling(14).mean().bfill().values
        atr_sma = pd.Series(atr14).rolling(20).mean().bfill().values
        atr_ratio = atr14 / (atr_sma + 1e-9)
        
        delta = pd.Series(close).diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi = (100 - (100 / (1 + rs))).bfill().values
        
        don_h = pd.Series(high).shift(1).rolling(28).max().bfill().values
        don_l = pd.Series(low).shift(1).rolling(28).min().bfill().values
        break_high = (close > don_h) & (np.roll(close, 1) <= np.roll(don_h, 1))
        break_low = (close < don_l) & (np.roll(close, 1) >= np.roll(don_l, 1))
        break_high[0] = False
        break_low[0] = False
        
        prev_is_bear = np.roll(close, 1) < np.roll(open_, 1)
        prev_is_bull = np.roll(close, 1) > np.roll(open_, 1)
        ob_bull_l = np.where(prev_is_bear, np.roll(low, 1), low)
        ob_bear_h = np.where(prev_is_bull, np.roll(high, 1), high)
        
        h1_bull = m15['h1_bull'].values
        h1_bear = m15['h1_bear'].values
        
        state = 0
        entry_price = 0.0
        sl_price = 0.0
        tp_price = 0.0
        entry_idx = 0
        hunting = 0
        hunt_idx = 0
        hunt_ob_l = 0.0
        hunt_ob_h = 0.0
        hunt_fib50 = 0.0
        hunt_atr = 0.0
        
        consec_losses = 0
        pause_until_idx = -999
        trades = []
        
        for i in range(200, n):
            c = close[i]
            h = high[i]
            l = low[i]
            o = open_[i]
            a = atr14[i]
            hr = hours[i]
            
            if state != 0:
                if state == 1:
                    if h >= tp_price:
                        trades.append({'pair': pair, 'entry_time': m15['time_dt'].iloc[entry_idx], 'exit_time': m15['time_dt'].iloc[i], 'direction': 'LONG', 'entry': entry_price, 'sl': sl_price, 'tp': tp_price, 'res': 'WIN', 'R': rr, 'pips': (tp_price - entry_price)/pip_unit, 'hold_bars': i - entry_idx})
                        state = 0
                        consec_losses = 0
                    elif l <= sl_price:
                        trades.append({'pair': pair, 'entry_time': m15['time_dt'].iloc[entry_idx], 'exit_time': m15['time_dt'].iloc[i], 'direction': 'LONG', 'entry': entry_price, 'sl': sl_price, 'tp': tp_price, 'res': 'LOSS', 'R': -1.0, 'pips': (sl_price - entry_price)/pip_unit, 'hold_bars': i - entry_idx})
                        state = 0
                        consec_losses += 1
                        if consec_losses >= 2:
                            pause_until_idx = i + cb_bars
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (c - entry_price) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        r_mult = pips / ((entry_price - sl_price) / pip_unit)
                        trades.append({'pair': pair, 'entry_time': m15['time_dt'].iloc[entry_idx], 'exit_time': m15['time_dt'].iloc[i], 'direction': 'LONG', 'entry': entry_price, 'sl': sl_price, 'tp': tp_price, 'res': res, 'R': r_mult, 'pips': pips, 'hold_bars': i - entry_idx})
                        state = 0
                        if res == 'LOSS':
                            consec_losses += 1
                            if consec_losses >= 2:
                                pause_until_idx = i + cb_bars
                                consec_losses = 0
                        else:
                            consec_losses = 0
                elif state == -1:
                    if l <= tp_price:
                        trades.append({'pair': pair, 'entry_time': m15['time_dt'].iloc[entry_idx], 'exit_time': m15['time_dt'].iloc[i], 'direction': 'SHORT', 'entry': entry_price, 'sl': sl_price, 'tp': tp_price, 'res': 'WIN', 'R': rr, 'pips': (entry_price - tp_price)/pip_unit, 'hold_bars': i - entry_idx})
                        state = 0
                        consec_losses = 0
                    elif h >= sl_price:
                        trades.append({'pair': pair, 'entry_time': m15['time_dt'].iloc[entry_idx], 'exit_time': m15['time_dt'].iloc[i], 'direction': 'SHORT', 'entry': entry_price, 'sl': sl_price, 'tp': tp_price, 'res': 'LOSS', 'R': -1.0, 'pips': (entry_price - sl_price)/pip_unit, 'hold_bars': i - entry_idx})
                        state = 0
                        consec_losses += 1
                        if consec_losses >= 2:
                            pause_until_idx = i + cb_bars
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (entry_price - c) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        r_mult = pips / ((sl_price - entry_price) / pip_unit)
                        trades.append({'pair': pair, 'entry_time': m15['time_dt'].iloc[entry_idx], 'exit_time': m15['time_dt'].iloc[i], 'direction': 'SHORT', 'entry': entry_price, 'sl': sl_price, 'tp': tp_price, 'res': res, 'R': r_mult, 'pips': pips, 'hold_bars': i - entry_idx})
                        state = 0
                        if res == 'LOSS':
                            consec_losses += 1
                            if consec_losses >= 2:
                                pause_until_idx = i + cb_bars
                                consec_losses = 0
                        else:
                            consec_losses = 0
                continue
                
            if i < pause_until_idx:
                continue
                
            in_session = (hr >= 7 and hr <= 16)
            
            if hunting == 0:
                long_setup = break_high[i] and h1_bull[i] and (m15_ema20[i] > m15_ema50[i]) and (atr_ratio[i] >= 1.0) and in_session
                short_setup = break_low[i] and h1_bear[i] and (m15_ema20[i] < m15_ema50[i]) and (atr_ratio[i] >= 1.0) and in_session
                
                if long_setup:
                    hunting = 1
                    hunt_idx = i
                    hunt_ob_l = ob_bull_l[i]
                    hunt_ob_h = high[i]
                    hunt_fib50 = hunt_ob_h - 0.5 * (hunt_ob_h - hunt_ob_l)
                    hunt_atr = a
                elif short_setup:
                    hunting = -1
                    hunt_idx = i
                    hunt_ob_h = ob_bear_h[i]
                    hunt_ob_l = low[i]
                    hunt_fib50 = hunt_ob_l + 0.5 * (hunt_ob_h - hunt_ob_l)
                    hunt_atr = a
            else:
                if (i - hunt_idx) > 4:
                    hunting = 0
                elif hunting == 1:
                    retrace = (l <= hunt_fib50) or (l <= hunt_ob_h)
                    rejection = c > o
                    rsi_ok = rsi[i] <= 68.0
                    if retrace and rejection and rsi_ok and in_session:
                        raw_sl = hunt_ob_l - (hunt_atr * sl_mult)
                        sl_dist = max(c - raw_sl, min_sl_dist)
                        if sl_dist <= max_sl_dist:
                            state = 1
                            hunting = 0
                            entry_price = c
                            entry_idx = i
                            sl_price = entry_price - sl_dist
                            tp_price = entry_price + (sl_dist * rr)
                elif hunting == -1:
                    retrace = (h >= hunt_fib50) or (h >= hunt_ob_l)
                    rejection = c < o
                    rsi_ok = rsi[i] >= 32.0
                    if retrace and rejection and rsi_ok and in_session:
                        raw_sl = hunt_ob_h + (hunt_atr * sl_mult)
                        sl_dist = max(raw_sl - c, min_sl_dist)
                        if sl_dist <= max_sl_dist:
                            state = -1
                            hunting = 0
                            entry_price = c
                            entry_idx = i
                            sl_price = entry_price + sl_dist
                            tp_price = entry_price - (sl_dist * rr)
                            
        all_trades.extend(trades)
        
    df = pd.DataFrame(all_trades)
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    
    # Filter for the last 6 months (2026-03-15 to 2026-09-15)
    last_6m = df[(df['entry_time'] >= '2026-03-15') & (df['entry_time'] <= '2026-09-16')].sort_values('entry_time').copy()
    
    print("\n" + "="*85)
    print("BACKTEST AUDIT: LAST 6 MONTHS PERFORMANCE (March 15, 2026 - September 15, 2026)")
    print("="*85)
    
    n_6m = len(last_6m)
    wins_6m = (last_6m['res'] == 'WIN').sum()
    wr_6m = wins_6m / n_6m * 100
    gross_w = last_6m[last_6m['R'] > 0]['R'].sum()
    gross_l = abs(last_6m[last_6m['R'] < 0]['R'].sum())
    pf_6m = gross_w / (gross_l + 1e-9)
    net_r_6m = last_6m['R'].sum()
    pips_6m = last_6m['pips'].sum()
    
    # Time gap analysis
    last_6m_sorted = last_6m.sort_values('entry_time').copy()
    last_6m_sorted['gap_hours'] = last_6m_sorted['entry_time'].diff().dt.total_seconds() / 3600.0
    mean_gap_hours = last_6m_sorted['gap_hours'].mean()
    median_gap_hours = last_6m_sorted['gap_hours'].median()
    
    print(f"Total Portfolio Trades (Last 6 Months): {n_6m}")
    print(f"Win Rate: {wr_6m:.1f}% ({wins_6m} Wins / {n_6m - wins_6m} Losses)")
    print(f"Profit Factor: {pf_6m:.2f}")
    print(f"Net Return: {net_r_6m:+.1f} R")
    print(f"Net Pips: {pips_6m:+.0f} pips")
    print(f"Average Signal Frequency: {n_6m / 26.0:.1f} trades/week across portfolio (~1 trade every {mean_gap_hours/24:.1f} days)")
    print(f"Median Time Between Signals: {median_gap_hours:.1f} hours ({median_gap_hours/24:.1f} days)")
    
    # 1. Per-Pair Breakdown in Last 6 Months
    print("\n--- PERFORMANCE BY PAIR (LAST 6 MONTHS) ---")
    pair_stats = []
    for pair in pairs:
        pdf = last_6m[last_6m['pair'] == pair].sort_values('entry_time')
        pn = len(pdf)
        if pn == 0:
            continue
        pwins = (pdf['res'] == 'WIN').sum()
        pwr = pwins / pn * 100
        pgross_w = pdf[pdf['R'] > 0]['R'].sum()
        pgross_l = abs(pdf[pdf['R'] < 0]['R'].sum())
        ppf = pgross_w / (pgross_l + 1e-9)
        pnet_r = pdf['R'].sum()
        ppips = pdf['pips'].sum()
        
        # Streak
        cur = 0
        pstreaks = []
        for r in pdf['res']:
            if r == 'LOSS':
                cur += 1
            else:
                if cur > 0:
                    pstreaks.append(cur)
                cur = 0
        if cur > 0:
            pstreaks.append(cur)
        pmax_streak = max(pstreaks) if pstreaks else 0
        
        pair_stats.append({
            'Pair': pair,
            'Trades': pn,
            'Trades/Mo': f"{pn / 6.0:.1f}",
            'Win Rate': f"{pwr:.1f}%",
            'Profit Factor': f"{ppf:.2f}",
            'Net Return': f"{pnet_r:+.1f}R",
            'Net Pips': f"{ppips:+.0f}",
            'Max Loss Streak': pmax_streak
        })
    print(pd.DataFrame(pair_stats).to_string(index=False))
    
    # 2. Month-by-Month Breakdown
    print("\n--- MONTH-BY-MONTH PORTFOLIO BREAKDOWN (2026) ---")
    last_6m['month'] = last_6m['entry_time'].dt.strftime('%Y-%m')
    m_grp = last_6m.groupby('month').agg(
        trades=('res', 'count'),
        wins=('res', lambda x: (x == 'WIN').sum()),
        win_rate=('res', lambda x: (x == 'WIN').mean() * 100),
        net_R=('R', 'sum'),
        net_pips=('pips', 'sum')
    )
    m_grp['profit_factor'] = last_6m.groupby('month').apply(
        lambda df_m: df_m[df_m['R'] > 0]['R'].sum() / (abs(df_m[df_m['R'] < 0]['R'].sum()) + 1e-9)
    )
    print(m_grp.to_string())
    
    # 3. Recent 10 Trades Sample
    print("\n--- MOST RECENT 10 TRADES IN DATASET (August - September 2026) ---")
    recent_10 = last_6m.tail(10)[['entry_time', 'pair', 'direction', 'entry', 'sl', 'tp', 'res', 'R', 'pips']]
    print(recent_10.to_string(index=False))

if __name__ == '__main__':
    run_last_6_months_audit()
