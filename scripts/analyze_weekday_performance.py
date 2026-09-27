import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

def run_weekday_analysis():
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        data = pickle.load(f)
    pairs_data = data[1]
    
    pairs = ['USDCAD', 'USDCHF', 'USDJPY', 'AUDUSD', 'EURUSD', 'GBPUSD']
    
    rr = 1.75
    sl_mult = 0.5
    
    all_trades = []
    
    for pair in pairs:
        if pair not in pairs_data:
            continue
        m15 = pairs_data[pair]['M15'].copy()
        h1 = pairs_data[pair]['H1'].copy()
        
        pip_unit = 0.01 if 'JPY' in pair else 0.0001
        min_sl_dist = 18.0 * pip_unit
        max_sl_dist = 60.0 * pip_unit
        
        m15['time_dt'] = pd.to_datetime(m15['time'], unit='s')
        h1['time_dt'] = pd.to_datetime(h1['time'], unit='s')
        
        # 1H Calculations
        h1['e20'] = h1['close'].ewm(span=20, adjust=False).mean()
        h1['e50'] = h1['close'].ewm(span=50, adjust=False).mean()
        h1['e20_slope'] = h1['e20'] - h1['e20'].shift(2)
        
        tr_h1 = np.maximum(h1['high'] - h1['low'], np.maximum(np.abs(h1['high'] - h1['close'].shift(1)), np.abs(h1['low'] - h1['close'].shift(1))))
        h1['atr'] = pd.Series(tr_h1).rolling(14).mean().bfill()
        
        # 4H Resample
        h1_idx = h1.set_index('time_dt')
        h4 = h1_idx.resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna().reset_index()
        h4['e20'] = h4['close'].ewm(span=20, adjust=False).mean()
        h4['e50'] = h4['close'].ewm(span=50, adjust=False).mean()
        h4['ema_bull'] = h4['e20'] > h4['e50']
        h4['ema_bear'] = h4['e20'] < h4['e50']
        
        m15['h1_time'] = m15['time_dt'].dt.floor('h') - pd.Timedelta(hours=1)
        m15['h4_time'] = m15['time_dt'].dt.floor('4h') - pd.Timedelta(hours=4)
        
        m15['h1_e50'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['e50']))).values
        m15['h1_e20'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['e20']))).values
        m15['h1_slope'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['e20_slope']))).values
        m15['h1_atr'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['atr']))).values
        
        m15['h4_ema_bull'] = m15['h4_time'].map(dict(zip(h4['time_dt'], h4['ema_bull']))).fillna(True).values
        m15['h4_ema_bear'] = m15['h4_time'].map(dict(zip(h4['time_dt'], h4['ema_bear']))).fillna(True).values
        
        close = m15['close'].values
        open_ = m15['open'].values
        high = m15['high'].values
        low = m15['low'].values
        hours = m15['time_dt'].dt.hour.values
        n = len(close)
        
        m15_e20 = m15['close'].ewm(span=20, adjust=False).mean().values
        m15_e50 = m15['close'].ewm(span=50, adjust=False).mean().values
        
        tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
        tr[0] = high[0] - low[0]
        atr14 = pd.Series(tr).rolling(14).mean().bfill().values
        
        delta = pd.Series(close).diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        rs = gain.rolling(14).mean() / (loss.rolling(14).mean() + 1e-9)
        rsi = (100 - (100 / (1 + rs))).bfill().values
        
        don_h = pd.Series(high).shift(1).rolling(32).max().bfill().values
        don_l = pd.Series(low).shift(1).rolling(32).min().bfill().values
        
        rng = np.maximum(high - low, 1e-6)
        body_long = (close - low) / rng
        body_short = (high - close) / rng
        
        break_high = (close > don_h) & (np.roll(close, 1) <= np.roll(don_h, 1)) & (body_long >= 0.35)
        break_low = (close < don_l) & (np.roll(close, 1) >= np.roll(don_l, 1)) & (body_short >= 0.35)
        break_high[0] = False
        break_low[0] = False
        
        h1_e50 = m15['h1_e50'].values
        h1_e20 = m15['h1_e20'].values
        h1_slope = m15['h1_slope'].values
        h1_atr = m15['h1_atr'].values
        
        h4_ema_bull = m15['h4_ema_bull'].values
        h4_ema_bear = m15['h4_ema_bear'].values
        
        state = 0
        entry_price = 0.0
        sl_price = 0.0
        tp_price = 0.0
        entry_idx = 0
        hunting = 0
        hunt_idx = 0
        hunt_level = 0.0
        hunt_ob_h = 0.0
        hunt_ob_l = 0.0
        hunt_fib_50 = 0.0
        hunt_atr = 0.0
        
        last_exit_idx = -999
        consec_losses = 0
        lockout_until = 0
        
        for i in range(200, n):
            c = close[i]
            h = high[i]
            l = low[i]
            o = open_[i]
            a = atr14[i]
            hr = hours[i]
            t = m15['time_dt'].iloc[i]
            
            if state != 0:
                if state == 1:
                    if h >= tp_price:
                        all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'WIN', 'pips': (tp_price - entry_price)/pip_unit, 'R': rr, 'weekday': m15['time_dt'].iloc[entry_idx].day_name(), 'hour': m15['time_dt'].iloc[entry_idx].hour})
                        state = 0
                        last_exit_idx = i
                        consec_losses = 0
                    elif l <= sl_price:
                        all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'LOSS', 'pips': (sl_price - entry_price)/pip_unit, 'R': -1.0, 'weekday': m15['time_dt'].iloc[entry_idx].day_name(), 'hour': m15['time_dt'].iloc[entry_idx].hour})
                        state = 0
                        last_exit_idx = i
                        consec_losses += 1
                        if consec_losses >= 2:
                            lockout_until = i + 48
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (c - entry_price) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'pips': pips, 'R': pips/((entry_price-sl_price)/pip_unit), 'weekday': m15['time_dt'].iloc[entry_idx].day_name(), 'hour': m15['time_dt'].iloc[entry_idx].hour})
                        state = 0
                        last_exit_idx = i
                elif state == -1:
                    if l <= tp_price:
                        all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'WIN', 'pips': (entry_price - tp_price)/pip_unit, 'R': rr, 'weekday': m15['time_dt'].iloc[entry_idx].day_name(), 'hour': m15['time_dt'].iloc[entry_idx].hour})
                        state = 0
                        last_exit_idx = i
                        consec_losses = 0
                    elif h >= sl_price:
                        all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'LOSS', 'pips': (entry_price - sl_price)/pip_unit, 'R': -1.0, 'weekday': m15['time_dt'].iloc[entry_idx].day_name(), 'hour': m15['time_dt'].iloc[entry_idx].hour})
                        state = 0
                        last_exit_idx = i
                        consec_losses += 1
                        if consec_losses >= 2:
                            lockout_until = i + 48
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (entry_price - c) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'pips': pips, 'R': pips/((sl_price-entry_price)/pip_unit), 'weekday': m15['time_dt'].iloc[entry_idx].day_name(), 'hour': m15['time_dt'].iloc[entry_idx].hour})
                        state = 0
                        last_exit_idx = i
                continue
                
            if i < lockout_until or (i - last_exit_idx) < 3:
                continue
                
            in_active_hours = (hr != 21)
            
            slope_thresh = 0.10 * h1_atr[i]
            h1_slope_bull = h1_slope[i] >= slope_thresh
            h1_slope_bear = -h1_slope[i] >= slope_thresh
            
            h1_trend_bull = (c > h1_e50[i]) and (h1_e20[i] > h1_e50[i]) and h1_slope_bull
            h1_trend_bear = (c < h1_e50[i]) and (h1_e20[i] < h1_e50[i]) and h1_slope_bear
            
            if hunting == 0:
                long_setup = break_high[i] and h1_trend_bull and h4_ema_bull[i] and (m15_e20[i] > m15_e50[i]) and in_active_hours and (rsi[i] >= 35 and rsi[i] <= 80)
                short_setup = break_low[i] and h1_trend_bear and h4_ema_bear[i] and (m15_e20[i] < m15_e50[i]) and in_active_hours and (rsi[i] <= 65 and rsi[i] >= 20)
                
                if long_setup:
                    hunting = 1
                    hunt_idx = i
                    hunt_level = don_h[i]
                    hunt_ob_l = low[i-1] if close[i-1] < open_[i-1] else low[i]
                    hunt_ob_h = high[i-1] if close[i-1] < open_[i-1] else high[i]
                    hunt_fib_50 = high[i] - 0.50 * (high[i] - hunt_ob_l)
                    hunt_atr = a
                elif short_setup:
                    hunting = -1
                    hunt_idx = i
                    hunt_level = don_l[i]
                    hunt_ob_h = high[i-1] if close[i-1] > open_[i-1] else high[i]
                    hunt_ob_l = low[i-1] if close[i-1] > open_[i-1] else low[i]
                    hunt_fib_50 = low[i] + 0.50 * (hunt_ob_h - low[i])
                    hunt_atr = a
            else:
                if (i - hunt_idx) > 8:
                    hunting = 0
                elif hunting == 1:
                    retest = (l <= hunt_level * 1.0005) or (l <= m15_e20[i]) or (l <= hunt_fib_50) or (l <= hunt_ob_h)
                    rejection = (c > o)
                    if retest and rejection and (rsi[i] <= 78) and in_active_hours:
                        raw_sl = min(hunt_ob_l, l) - (hunt_atr * sl_mult)
                        sl_dist = max(c - raw_sl, min_sl_dist)
                        if sl_dist <= max_sl_dist:
                            state = 1
                            hunting = 0
                            entry_price = c
                            entry_idx = i
                            sl_price = entry_price - sl_dist
                            tp_price = entry_price + (sl_dist * rr)
                elif hunting == -1:
                    retest = (h >= hunt_level * 0.9995) or (h >= m15_e20[i]) or (h >= hunt_fib_50) or (h >= hunt_ob_l)
                    rejection = (c < o)
                    if retest and rejection and (rsi[i] >= 22) and in_active_hours:
                        raw_sl = max(hunt_ob_h, h) + (hunt_atr * sl_mult)
                        sl_dist = max(raw_sl - c, min_sl_dist)
                        if sl_dist <= max_sl_dist:
                            state = -1
                            hunting = 0
                            entry_price = c
                            entry_idx = i
                            sl_price = entry_price + sl_dist
                            tp_price = entry_price - (sl_dist * rr)
                            
    df = pd.DataFrame(all_trades)
    df['time'] = pd.to_datetime(df['time'])
    
    # Analyze 6-Month Period (March 15 to Sept 15, 2026)
    df_6m = df[df['time'] >= '2026-03-15'].copy()
    
    days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Sunday']
    
    print("================================================================================")
    print("WEEKDAY PERFORMANCE AUDIT (Last 6 Months: March - Sept 2026)")
    print("================================================================================")
    
    weekday_summary = []
    for day in days_order:
        sub = df_6m[df_6m['weekday'] == day]
        if len(sub) == 0:
            continue
        tot = len(sub)
        w = len(sub[sub['res'] == 'WIN'])
        l = len(sub[sub['res'] == 'LOSS'])
        wr = w / tot * 100
        pips = sub['pips'].sum()
        gw = sub[sub['pips'] > 0]['pips'].sum()
        gl = abs(sub[sub['pips'] < 0]['pips'].sum())
        pf = gw / gl if gl > 0 else (99.0 if gw > 0 else 0)
        net_r = sub['R'].sum()
        
        weekday_summary.append({
            'Day': day,
            'Trades': tot,
            'Wins': w,
            'Losses': l,
            'WinRate%': wr,
            'NetPips': pips,
            'GrossWin': gw,
            'GrossLoss': gl,
            'ProfitFactor': pf,
            'NetR': net_r
        })
        
    res_df = pd.DataFrame(weekday_summary)
    print(res_df.to_string(index=False))
    
    # Detailed breakdown of Friday by session hours (e.g. morning vs afternoon vs close)
    print("\n--------------------------------------------------------------------------------")
    print("FRIDAY TIME-OF-DAY BREAKDOWN:")
    print("--------------------------------------------------------------------------------")
    fri = df_6m[df_6m['weekday'] == 'Friday'].copy()
    if len(fri) > 0:
        fri['session_bucket'] = pd.cut(
            fri['hour'],
            bins=[-1, 7, 12, 16, 24],
            labels=['Asian (00-07 UTC)', 'London Morning (08-12 UTC)', 'NY Overlap (13-16 UTC)', 'Friday Close (17-23 UTC)']
        )
        for b, grp in fri.groupby('session_bucket', observed=False):
            w = len(grp[grp['res'] == 'WIN'])
            l = len(grp[grp['res'] == 'LOSS'])
            wr = w / len(grp) * 100 if len(grp) > 0 else 0
            p = grp['pips'].sum()
            print(f"  {b:<28}: {len(grp):2d} trades | WR: {wr:4.1f}% | Net Pips: {p:+6.1f}")

    print("\n--------------------------------------------------------------------------------")
    print("MONDAY TIME-OF-DAY BREAKDOWN:")
    print("--------------------------------------------------------------------------------")
    mon = df_6m[df_6m['weekday'] == 'Monday'].copy()
    if len(mon) > 0:
        mon['session_bucket'] = pd.cut(
            mon['hour'],
            bins=[-1, 7, 12, 16, 24],
            labels=['Asian / Gap Open (00-07 UTC)', 'London Open (08-12 UTC)', 'NY Session (13-16 UTC)', 'Afternoon (17-23 UTC)']
        )
        for b, grp in mon.groupby('session_bucket', observed=False):
            w = len(grp[grp['res'] == 'WIN'])
            l = len(grp[grp['res'] == 'LOSS'])
            wr = w / len(grp) * 100 if len(grp) > 0 else 0
            p = grp['pips'].sum()
            print(f"  {b:<30}: {len(grp):2d} trades | WR: {wr:4.1f}% | Net Pips: {p:+6.1f}")
            
    print("\n--------------------------------------------------------------------------------")
    print("WEEKDAY PERFORMANCE IN SEPTEMBER 2026 SPECIFICALLY:")
    print("--------------------------------------------------------------------------------")
    df_sep = df[df['time'] >= '2026-09-01'].copy()
    for day in days_order:
        sub = df_sep[df_sep['weekday'] == day]
        if len(sub) == 0:
            continue
        w = len(sub[sub['res'] == 'WIN'])
        l = len(sub[sub['res'] == 'LOSS'])
        wr = w / len(sub) * 100
        p = sub['pips'].sum()
        print(f"  {day:<10}: {len(sub):2d} trades ({w}W / {l}L) | WR: {wr:4.1f}% | Net Pips: {p:+6.1f}")

if __name__ == '__main__':
    run_weekday_analysis()
