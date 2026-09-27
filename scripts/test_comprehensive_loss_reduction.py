import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

def calc_adx(df, n=14):
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    tr = np.maximum(high - low, np.maximum(abs(high - np.roll(close, 1)), abs(low - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    up = high - np.roll(high, 1)
    down = np.roll(low, 1) - low
    up[0] = 0
    down[0] = 0
    pos_dm = np.where((up > down) & (up > 0), up, 0.0)
    neg_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr_s = pd.Series(tr).ewm(alpha=1/n, adjust=False).mean()
    pdm_s = pd.Series(pos_dm).ewm(alpha=1/n, adjust=False).mean()
    ndm_s = pd.Series(neg_dm).ewm(alpha=1/n, adjust=False).mean()
    pdi = 100 * pdm_s / (tr_s + 1e-9)
    ndi = 100 * ndm_s / (tr_s + 1e-9)
    dx = 100 * abs(pdi - ndi) / (pdi + ndi + 1e-9)
    return dx.ewm(alpha=1/n, adjust=False).mean().values

def run_backtest(
    min_atr_ratio=1.0,
    min_h1_adx=20.0,
    require_h1_slope=True,
    min_sl_pips=20.0,
    session_start=7,
    session_end=16,
    cb_trigger=2,
    cb_pause_bars=48
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
        min_sl_dist = min_sl_pips * pip_unit
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
        h1['adx'] = calc_adx(h1, 14)
        h1['ema20_slope'] = h1['ema20'] - h1['ema20'].shift(2)
        
        h1['date_only'] = h1['time_dt'].dt.floor('D')
        d1_bull_map = dict(zip(d1['time_dt'], d1['close'] > d1['ema50']))
        h1['d1_bull'] = h1['date_only'].map(d1_bull_map).fillna(False)
        
        # H1 alignment + optional slope + optional ADX
        h1_bull_cond = (h1['close'] > h1['ema200']) & (h1['ema20'] > h1['ema50']) & (h1['d1_bull'])
        h1_bear_cond = (h1['close'] < h1['ema200']) & (h1['ema20'] < h1['ema50']) & (~h1['d1_bull'])
        
        if require_h1_slope:
            h1_bull_cond = h1_bull_cond & (h1['ema20_slope'] > 0)
            h1_bear_cond = h1_bear_cond & (h1['ema20_slope'] < 0)
            
        if min_h1_adx > 0:
            h1_bull_cond = h1_bull_cond & (h1['adx'] >= min_h1_adx)
            h1_bear_cond = h1_bear_cond & (h1['adx'] >= min_h1_adx)
            
        h1['h1_bull'] = h1_bull_cond
        h1['h1_bear'] = h1_bear_cond
        
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
                        if consec_losses >= cb_trigger:
                            pause_until_idx = i + cb_pause_bars
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (c - entry_price) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        r_mult = pips / ((entry_price - sl_price) / pip_unit)
                        all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'R': r_mult, 'pips': pips})
                        state = 0
                        if res == 'LOSS':
                            consec_losses += 1
                            if consec_losses >= cb_trigger:
                                pause_until_idx = i + cb_pause_bars
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
                        if consec_losses >= cb_trigger:
                            pause_until_idx = i + cb_pause_bars
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (entry_price - c) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        r_mult = pips / ((sl_price - entry_price) / pip_unit)
                        all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'R': r_mult, 'pips': pips})
                        state = 0
                        if res == 'LOSS':
                            consec_losses += 1
                            if consec_losses >= cb_trigger:
                                pause_until_idx = i + cb_pause_bars
                                consec_losses = 0
                        else:
                            consec_losses = 0
                continue
                
            if i < pause_until_idx:
                continue
                
            in_session = (hr >= session_start and hr <= session_end)
            
            if hunting == 0:
                long_setup = break_high[i] and h1_bull[i] and (m15_ema20[i] > m15_ema50[i]) and in_session
                short_setup = break_low[i] and h1_bear[i] and (m15_ema20[i] < m15_ema50[i]) and in_session
                
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
                if (i - hunt_idx) > 4:
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
    experiments = [
        {"name": "A. MinSL 16p, Base Session (07-17), CB 24 bars (6h)", "min_atr": 1.0, "adx": 0.0, "slope": False, "sl_pips": 16.0, "sess_end": 17, "cb_pause": 24},
        {"name": "B. MinSL 20p, Core Session (07-16), CB 48 bars (12h)", "min_atr": 1.0, "adx": 0.0, "slope": False, "sl_pips": 20.0, "sess_end": 16, "cb_pause": 48},
        {"name": "C. MinSL 20p + 1H EMA20 Slope Confluence", "min_atr": 1.0, "adx": 0.0, "slope": True, "sl_pips": 20.0, "sess_end": 16, "cb_pause": 48},
        {"name": "D. MinSL 20p + 1H ADX >= 18 Trend Strength", "min_atr": 1.0, "adx": 18.0, "slope": True, "sl_pips": 20.0, "sess_end": 16, "cb_pause": 48},
        {"name": "E. MinSL 22p + 1H ADX >= 18 + 1H Slope + CB 48 bars", "min_atr": 1.0, "adx": 18.0, "slope": True, "sl_pips": 22.0, "sess_end": 16, "cb_pause": 48},
        {"name": "F. MinSL 22p + 1H ADX >= 20 + 1H Slope + CB 64 bars", "min_atr": 1.0, "adx": 20.0, "slope": True, "sl_pips": 22.0, "sess_end": 16, "cb_pause": 64},
    ]
    
    out = []
    for exp in experiments:
        df_trades = run_backtest(
            min_atr_ratio=exp['min_atr'],
            min_h1_adx=exp['adx'],
            require_h1_slope=exp['slope'],
            min_sl_pips=exp['sl_pips'],
            session_end=exp['sess_end'],
            cb_pause_bars=exp['cb_pause']
        )
        if len(df_trades) == 0:
            continue
        n = len(df_trades)
        wins = (df_trades['res'] == 'WIN').sum()
        wr = wins / n * 100
        gross_w = df_trades[df_trades['R'] > 0]['R'].sum()
        gross_l = abs(df_trades[df_trades['R'] < 0]['R'].sum())
        pf = gross_w / (gross_l + 1e-9)
        net_r = df_trades['R'].sum()
        pips = df_trades['pips'].sum()
        
        # Measure loss streaks across pairs
        streaks = []
        for pair in df_trades['pair'].unique():
            p_trades = df_trades[df_trades['pair'] == pair].sort_values('time')
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
        s_ser = pd.Series(streaks)
        max_s = s_ser.max() if len(s_ser) > 0 else 0
        avg_s = s_ser.mean() if len(s_ser) > 0 else 0
        gt3 = (s_ser >= 4).sum() if len(s_ser) > 0 else 0
        
        # Calculate signal frequency: trades per month across the 5 pairs (data span ~4 years)
        trades_per_month = n / (4.2 * 12)
        trades_per_week = trades_per_month / 4.33
        
        out.append({
            'Strategy Variant': exp['name'],
            'Trades': n,
            'Frequency (Trades/Wk)': f"{trades_per_week:.1f} /wk",
            'Win Rate': f"{wr:.1f}%",
            'Profit Factor': f"{pf:.2f}",
            'Net Return': f"{net_r:+.1f}R",
            'Net Pips': f"{pips:+.0f}",
            'Max Loss Streak': max_s,
            'Streaks >= 4': gt3
        })
        
    df_eval = pd.DataFrame(out)
    print("\n" + "="*95)
    print("EMPIRICAL COMPARISON OF STRATEGY ENHANCEMENTS ACROSS INSTITUTIONAL PAIRS")
    print("="*95)
    print(df_eval.to_string(index=False))
