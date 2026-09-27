import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

def evaluate_portfolio(trades_df):
    if len(trades_df) == 0:
        return {'n': 0, 'wr': 0, 'pf': 0, 'net_r': 0, 'pips': 0, 'max_loss_streak': 0}
    n = len(trades_df)
    wins = (trades_df['res'] == 'WIN').sum()
    wr = wins / n * 100
    gross_w = trades_df[trades_df['R'] > 0]['R'].sum()
    gross_l = abs(trades_df[trades_df['R'] < 0]['R'].sum())
    pf = gross_w / (gross_l + 1e-9)
    net_r = trades_df['R'].sum()
    pips = trades_df['pips'].sum()
    
    # Calculate max consecutive loss streak
    streaks = []
    for pair in trades_df['pair'].unique():
        p_trades = trades_df[trades_df['pair'] == pair].sort_values('time')
        cur = 0
        for r in p_trades['res']:
            if r == 'LOSS':
                cur += 1
            else:
                if cur > 0:
                    streaks.append(cur)
                cur = 0
        if cur > 0:
            streaks.append(cur)
    max_streak = max(streaks) if streaks else 0
    return {
        'n': n,
        'wr': wr,
        'pf': pf,
        'net_r': net_r,
        'pips': pips,
        'max_loss_streak': max_streak
    }

def run_simulation(
    use_session_filter=True,
    min_atr_ratio=1.0,
    require_m15_ema=True,
    max_hunt_bars=4,
    use_circuit_breaker=True,
    cb_trigger=2,
    cb_pause=20
):
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        data = pickle.load(f)
    pairs_data = data[1]
    
    pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'USDCHF']
    all_trades = []
    
    for pair in pairs:
        if pair not in pairs_data:
            continue
        m15 = pairs_data[pair]['M15'].copy()
        h1 = pairs_data[pair]['H1'].copy()
        d1 = pairs_data[pair]['D1'].copy()
        
        is_jpy = 'JPY' in pair
        pip_unit = 0.01 if is_jpy else 0.0001
        min_sl_dist = 16.0 * pip_unit
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
        
        h1['date_only'] = h1['time_dt'].dt.floor('D')
        d1_bull_map = dict(zip(d1['time_dt'], d1['close'] > d1['ema50']))
        h1['d1_bull'] = h1['date_only'].map(d1_bull_map).fillna(False)
        
        h1['h1_bull'] = (h1['close'] > h1['ema200']) & (h1['ema20'] > h1['ema50']) & (h1['d1_bull'])
        h1['h1_bear'] = (h1['close'] < h1['ema200']) & (h1['ema20'] < h1['ema50']) & (~h1['d1_bull'])
        
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
                        all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'WIN', 'R': rr, 'pips': (tp_price - entry_price)/pip_unit})
                        state = 0
                        consec_losses = 0
                    elif l <= sl_price:
                        all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'LOSS', 'R': -1.0, 'pips': (sl_price - entry_price)/pip_unit})
                        state = 0
                        consec_losses += 1
                        if use_circuit_breaker and consec_losses >= cb_trigger:
                            pause_until_idx = i + cb_pause
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (c - entry_price) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        r_mult = pips / ((entry_price - sl_price) / pip_unit)
                        all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'R': r_mult, 'pips': pips})
                        state = 0
                        if res == 'LOSS':
                            consec_losses += 1
                            if use_circuit_breaker and consec_losses >= cb_trigger:
                                pause_until_idx = i + cb_pause
                                consec_losses = 0
                        else:
                            consec_losses = 0
                elif state == -1:
                    if l <= tp_price:
                        all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'WIN', 'R': rr, 'pips': (entry_price - tp_price)/pip_unit})
                        state = 0
                        consec_losses = 0
                    elif h >= sl_price:
                        all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'LOSS', 'R': -1.0, 'pips': (entry_price - sl_price)/pip_unit})
                        state = 0
                        consec_losses += 1
                        if use_circuit_breaker and consec_losses >= cb_trigger:
                            pause_until_idx = i + cb_pause
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (entry_price - c) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        r_mult = pips / ((sl_price - entry_price) / pip_unit)
                        all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'R': r_mult, 'pips': pips})
                        state = 0
                        if res == 'LOSS':
                            consec_losses += 1
                            if use_circuit_breaker and consec_losses >= cb_trigger:
                                pause_until_idx = i + cb_pause
                                consec_losses = 0
                        else:
                            consec_losses = 0
                continue
                
            if i < pause_until_idx:
                continue
                
            # Session check
            # Best hours from research: London + NY (07:00 to 17:00 UTC)
            if use_session_filter:
                in_session = (hr >= 7 and hr <= 17)
            else:
                in_session = (hr != 21) # only avoid rollover
                
            if hunting == 0:
                long_setup = break_high[i] and h1_bull[i] and in_session
                short_setup = break_low[i] and h1_bear[i] and in_session
                
                # Check 15m EMA confluence at setup
                if require_m15_ema:
                    long_setup = long_setup and (m15_ema20[i] > m15_ema50[i])
                    short_setup = short_setup and (m15_ema20[i] < m15_ema50[i])
                
                # Check Volatility Expansion: ATR must not be dying/contracting
                if min_atr_ratio > 0:
                    long_setup = long_setup and (atr_ratio[i] >= min_atr_ratio)
                    short_setup = short_setup and (atr_ratio[i] >= min_atr_ratio)
                    
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
                hunt_bars = i - hunt_idx
                if hunt_bars > max_hunt_bars:
                    hunting = 0
                elif hunting == 1:
                    retrace = (l <= hunt_fib50) or (l <= hunt_ob_h)
                    rejection = c > o
                    if retrace and rejection and in_session:
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
                    if retrace and rejection and in_session:
                        raw_sl = hunt_ob_h + (hunt_atr * sl_mult)
                        sl_dist = max(raw_sl - c, min_sl_dist)
                        if sl_dist <= max_sl_dist:
                            state = -1
                            hunting = 0
                            entry_price = c
                            entry_idx = i
                            sl_price = entry_price + sl_dist
                            tp_price = entry_price - (sl_dist * rr)
                            
    df_all = pd.DataFrame(all_trades)
    return df_all

if __name__ == '__main__':
    # Test configurations
    configs = [
        {"name": "1. Baseline 15m MTF (No filters, 24h)", "use_session": False, "min_atr": 0.0, "req_m15_ema": False, "max_hunt": 8, "use_cb": False},
        {"name": "2. + London/NY Session (07-17 UTC)", "use_session": True, "min_atr": 0.0, "req_m15_ema": False, "max_hunt": 8, "use_cb": False},
        {"name": "3. + 15m EMA 20/50 Momentum Confluence", "use_session": True, "min_atr": 0.0, "req_m15_ema": True, "max_hunt": 8, "use_cb": False},
        {"name": "4. + Volatility Expansion Filter (ATR Ratio >= 1.0)", "use_session": True, "min_atr": 1.0, "req_m15_ema": True, "max_hunt": 8, "use_cb": False},
        {"name": "5. + Retracement Timeout (<= 4 bars)", "use_session": True, "min_atr": 1.0, "req_m15_ema": True, "max_hunt": 4, "use_cb": False},
        {"name": "6. + Circuit Breaker (Pause 20 bars on 2 losses)", "use_session": True, "min_atr": 1.0, "req_m15_ema": True, "max_hunt": 4, "use_cb": True}
    ]
    
    results = []
    for cfg in configs:
        trades = run_simulation(
            use_session_filter=cfg['use_session'],
            min_atr_ratio=cfg['min_atr'],
            require_m15_ema=cfg['req_m15_ema'],
            max_hunt_bars=cfg['max_hunt'],
            use_circuit_breaker=cfg['use_cb']
        )
        stats = evaluate_portfolio(trades)
        results.append({
            'Configuration': cfg['name'],
            'Trades': stats['n'],
            'Win Rate': f"{stats['wr']:.1f}%",
            'Profit Factor': f"{stats['pf']:.2f}",
            'Net Return': f"{stats['net_r']:+.1f}R",
            'Net Pips': f"{stats['pips']:+.0f}",
            'Max Loss Streak': stats['max_loss_streak']
        })
        
    df_res = pd.DataFrame(results)
    print("\n" + "="*80)
    print("STEP-BY-STEP FILTER IMPACT ON WIN RATE & LOSS STREAK REDUCTION")
    print("="*80)
    print(df_res.to_string(index=False))
