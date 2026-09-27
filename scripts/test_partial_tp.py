import pickle, math
import pandas as pd
import numpy as np

def test_partial_tp():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
        
    df = all_data['XAUUSD'].copy()
    if df['time_dt'].dt.tz is not None:
        df['time_dt'] = df['time_dt'].dt.tz_localize(None)
        
    START_DATE = '2026-03-15'
    
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
    
    df['don_h'] = df['high'].shift(1).rolling(12).max() # 12-bar
    df['don_l'] = df['low'].shift(1).rolling(12).min()
    
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
    entry_price, sl_price = 0, 0
    entry_idx = 0
    hunting = 0
    hunt_level, hunt_ob_h, hunt_ob_l, hunt_fib, hunt_atr, hunt_idx = 0,0,0,0,0,0
    lockout_until = 0
    consec_losses = 0
    last_exit_idx = -999
    
    tp1_hit = False
    
    start_idx = df[df['time_dt'] >= START_DATE].index[0]
    
    for i in range(start_idx, len(df)):
        if state != 0:
            hold = i - entry_idx
            if hold >= 1:
                sl_dist = abs(entry_price - sl_price)
                tp1_price = entry_price + (sl_dist * 1.0) if state == 1 else entry_price - (sl_dist * 1.0)
                tp2_price = entry_price + (sl_dist * 2.0) if state == 1 else entry_price - (sl_dist * 2.0)
                
                # Check TP1
                if not tp1_hit:
                    if (state == 1 and h[i] >= tp1_price) or (state == -1 and l[i] <= tp1_price):
                        tp1_hit = True
                        
                cur_sl = entry_price if tp1_hit else sl_price
                
                exit_trig = False
                res_type = None
                pnl_r = 0.0
                
                if state == 1:
                    if h[i] >= tp2_price:
                        exit_trig = True
                        res_type = 'WIN'
                        pnl_r = 1.0 * 0.5 + 2.0 * 0.5 # 1.5 R total
                    elif l[i] <= cur_sl:
                        exit_trig = True
                        if tp1_hit:
                            res_type = 'WIN_PARTIAL'
                            pnl_r = 1.0 * 0.5 + 0.0 # 0.5 R
                        else:
                            res_type = 'LOSS'
                            pnl_r = -1.0
                    elif hold >= 160:
                        exit_trig = True
                        diff_r = (c[i] - entry_price) / sl_dist
                        pnl_r = (1.0 * 0.5 + diff_r * 0.5) if tp1_hit else diff_r
                        res_type = 'WIN' if pnl_r > 0 else 'LOSS'
                elif state == -1:
                    if l[i] <= tp2_price:
                        exit_trig = True
                        res_type = 'WIN'
                        pnl_r = 1.0 * 0.5 + 2.0 * 0.5
                    elif h[i] >= cur_sl:
                        exit_trig = True
                        if tp1_hit:
                            res_type = 'WIN_PARTIAL'
                            pnl_r = 1.0 * 0.5 + 0.0
                        else:
                            res_type = 'LOSS'
                            pnl_r = -1.0
                    elif hold >= 160:
                        exit_trig = True
                        diff_r = (entry_price - c[i]) / sl_dist
                        pnl_r = (1.0 * 0.5 + diff_r * 0.5) if tp1_hit else diff_r
                        res_type = 'WIN' if pnl_r > 0 else 'LOSS'
                        
                if exit_trig:
                    trades.append({'res': res_type, 'r': pnl_r, 'sl_dist': sl_dist})
                    state = 0
                    last_exit_idx = i
                    tp1_hit = False
                    if pnl_r > 0: consec_losses = 0
                    else:
                        consec_losses += 1
                        if consec_losses >= 2:
                            lockout_until = i + 48
                            consec_losses = 0
                    continue
                    
        if i < lockout_until or (i - last_exit_idx) < 3: continue
        hr = hours[i]
        wday = weekdays[i]
        in_act = (hr != 21) and not (wday == 'Friday' and hr >= 12)
        
        slope_thresh = 0.10 * atr[i]
        h1_slope_bull = e20_slope[i] >= slope_thresh
        h1_slope_bear = -e20_slope[i] >= slope_thresh
        
        trend_bull = (c[i] > e50[i]) and (e20[i] > e50[i]) and h1_slope_bull and h4_bull[i]
        trend_bear = (c[i] < e50[i]) and (e20[i] < e50[i]) and h1_slope_bear and h4_bear[i]
        
        long_s = trend_bull and (c[i] > don_h[i]) and (c[i-1] <= don_h[i-1]) and in_act
        short_s = trend_bear and (c[i] < don_l[i]) and (c[i-1] >= don_l[i-1]) and in_act
        
        if hunting == 0:
            if long_s:
                hunting, hunt_idx = 1, i
                hunt_level = don_h[i]
                hunt_ob_l = l[i-1] if c[i-1] < o[i-1] else l[i]
                hunt_ob_h = h[i-1] if c[i-1] < o[i-1] else h[i]
                hunt_fib = h[i] - 0.5 * (h[i] - hunt_ob_l)
                hunt_atr = atr[i]
            elif short_s:
                hunting, hunt_idx = -1, i
                hunt_level = don_l[i]
                hunt_ob_h = h[i-1] if c[i-1] > o[i-1] else h[i]
                hunt_ob_l = l[i-1] if c[i-1] > o[i-1] else l[i]
                hunt_fib = l[i] + 0.5 * (hunt_ob_h - l[i])
                hunt_atr = atr[i]
        else:
            if (i - hunt_idx) > 8: hunting = 0
            elif hunting == 1:
                if (l[i] <= hunt_fib or l[i] <= hunt_ob_h) and (c[i] > o[i]) and in_act:
                    raw_sl = hunt_ob_l - 0.5 * hunt_atr
                    act_sl = min(max(abs(c[i] - raw_sl), 18.0), 25.0)
                    state, hunting = 1, 0
                    entry_price, sl_price, entry_idx = c[i], c[i] - act_sl, i
                    tp1_hit = False
            elif hunting == -1:
                if (h[i] >= hunt_fib or h[i] >= hunt_ob_l) and (c[i] < o[i]) and in_act:
                    raw_sl = hunt_ob_h + 0.5 * hunt_atr
                    act_sl = min(max(abs(raw_sl - c[i]), 18.0), 25.0)
                    state, hunting = -1, 0
                    entry_price, sl_price, entry_idx = c[i], c[i] + act_sl, i
                    tp1_hit = False

    df_t = pd.DataFrame(trades)
    wins = len(df_t[df_t['r'] > 0])
    losses = len(df_t[df_t['r'] <= 0])
    wr = wins / len(df_t) * 100
    net_r = df_t['r'].sum()
    w_sum = df_t[df_t['r'] > 0]['r'].sum()
    l_sum = abs(df_t[df_t['r'] < 0]['r'].sum())
    pf = w_sum / l_sum
    print("="*60)
    print("PARTIAL TP AT 1.0R + RUNNER TO 2.0R RESULTS (12-bar Donchian)")
    print("="*60)
    print(f"Total Trades:  {len(df_t)}")
    print(f"Win Rate:      {wr:.1f}% ({wins} Wins / {losses} Losses)")
    print(f"Net R:         {net_r:+.2f} R")
    print(f"Profit Factor: {pf:.2f}")

if __name__ == '__main__':
    test_partial_tp()
