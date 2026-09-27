import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

def run_deep_trade_analysis():
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
        h1['atr14'] = pd.Series(np.maximum(h1['high'] - h1['low'], np.maximum(abs(h1['high'] - h1['close'].shift(1)), abs(h1['low'] - h1['close'].shift(1))))).rolling(14).mean().bfill().values
        
        h1['date_only'] = h1['time_dt'].dt.floor('D')
        d1_bull_map = dict(zip(d1['time_dt'], d1['close'] > d1['ema50']))
        h1['d1_bull'] = h1['date_only'].map(d1_bull_map).fillna(False)
        
        # H1 alignment
        h1['h1_bull'] = (h1['close'] > h1['ema200']) & (h1['ema20'] > h1['ema50']) & (h1['d1_bull'])
        h1['h1_bear'] = (h1['close'] < h1['ema200']) & (h1['ema20'] < h1['ema50']) & (~h1['d1_bull'])
        
        m15['time_dt'] = pd.to_datetime(m15['time'], unit='s')
        m15['h1_time'] = m15['time_dt'].dt.floor('h') - pd.Timedelta(hours=1)
        
        h1_bull_map = dict(zip(h1['time_dt'], h1['h1_bull']))
        h1_bear_map = dict(zip(h1['time_dt'], h1['h1_bear']))
        h1_atr_map = dict(zip(h1['time_dt'], h1['atr14']))
        h1_e200_map = dict(zip(h1['time_dt'], h1['ema200']))
        h1_e20_map = dict(zip(h1['time_dt'], h1['ema20']))
        h1_e50_map = dict(zip(h1['time_dt'], h1['ema50']))
        
        m15['h1_bull'] = m15['h1_time'].map(h1_bull_map).fillna(False).values
        m15['h1_bear'] = m15['h1_time'].map(h1_bear_map).fillna(False).values
        m15['h1_atr'] = m15['h1_time'].map(h1_atr_map).fillna(0.0015).values
        m15['h1_e200'] = m15['h1_time'].map(h1_e200_map).fillna(m15['close']).values
        m15['h1_e20'] = m15['h1_time'].map(h1_e20_map).fillna(m15['close']).values
        m15['h1_e50'] = m15['h1_time'].map(h1_e50_map).fillna(m15['close']).values
        
        close = m15['close'].values
        open_ = m15['open'].values
        high = m15['high'].values
        low = m15['low'].values
        hours = m15['time_dt'].dt.hour.values
        dow = m15['time_dt'].dt.dayofweek.values
        n = len(close)
        
        # 15m indicators
        m15_ema20 = m15['close'].ewm(span=20, adjust=False).mean().values
        m15_ema50 = m15['close'].ewm(span=50, adjust=False).mean().values
        
        tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
        tr[0] = high[0] - low[0]
        atr14 = pd.Series(tr).rolling(14).mean().bfill().values
        atr_sma = pd.Series(atr14).rolling(20).mean().bfill().values
        
        # 15m RSI
        delta = pd.Series(close).diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi = (100 - (100 / (1 + rs))).bfill().values
        
        # Donchian 28 bars (7 hours)
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
        h1_e200 = m15['h1_e200'].values
        h1_e20 = m15['h1_e20'].values
        h1_e50 = m15['h1_e50'].values
        
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
        
        # Track features at entry
        entry_features = {}
        
        for i in range(200, n):
            c = close[i]
            h = high[i]
            l = low[i]
            o = open_[i]
            a = atr14[i]
            hr = hours[i]
            d = dow[i]
            
            if state != 0:
                if state == 1:
                    if h >= tp_price:
                        record = dict(entry_features)
                        record.update({'res': 'WIN', 'R': rr, 'pips': (tp_price - entry_price)/pip_unit, 'hold_bars': i - entry_idx})
                        all_trades.append(record)
                        state = 0
                    elif l <= sl_price:
                        record = dict(entry_features)
                        record.update({'res': 'LOSS', 'R': -1.0, 'pips': (sl_price - entry_price)/pip_unit, 'hold_bars': i - entry_idx})
                        all_trades.append(record)
                        state = 0
                    elif (i - entry_idx) >= 160:
                        pips = (c - entry_price) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        r_mult = pips / ((entry_price - sl_price) / pip_unit)
                        record = dict(entry_features)
                        record.update({'res': res, 'R': r_mult, 'pips': pips, 'hold_bars': i - entry_idx})
                        all_trades.append(record)
                        state = 0
                elif state == -1:
                    if l <= tp_price:
                        record = dict(entry_features)
                        record.update({'res': 'WIN', 'R': rr, 'pips': (entry_price - tp_price)/pip_unit, 'hold_bars': i - entry_idx})
                        all_trades.append(record)
                        state = 0
                    elif h >= sl_price:
                        record = dict(entry_features)
                        record.update({'res': 'LOSS', 'R': -1.0, 'pips': (entry_price - sl_price)/pip_unit, 'hold_bars': i - entry_idx})
                        all_trades.append(record)
                        state = 0
                    elif (i - entry_idx) >= 160:
                        pips = (entry_price - c) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        r_mult = pips / ((sl_price - entry_price) / pip_unit)
                        record = dict(entry_features)
                        record.update({'res': res, 'R': r_mult, 'pips': pips, 'hold_bars': i - entry_idx})
                        all_trades.append(record)
                        state = 0
                continue
                
            # Hunting logic
            if hunting == 0:
                # 15m breakout + 1H trend alignment
                long_setup = break_high[i] and h1_bull[i]
                short_setup = break_low[i] and h1_bear[i]
                
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
                if hunt_bars > 8:
                    hunting = 0
                elif hunting == 1:
                    retrace = (l <= hunt_fib50) or (l <= hunt_ob_h)
                    rejection = c > o
                    if retrace and rejection:
                        raw_sl = hunt_ob_l - (hunt_atr * sl_mult)
                        sl_dist = max(c - raw_sl, min_sl_dist)
                        if sl_dist <= max_sl_dist:
                            state = 1
                            hunting = 0
                            entry_price = c
                            entry_idx = i
                            sl_price = entry_price - sl_dist
                            tp_price = entry_price + (sl_dist * rr)
                            
                            # Measure features
                            dist_h1_e200 = (c - h1_e200[i]) / (a + 1e-9)
                            m15_ema_aligned = m15_ema20[i] > m15_ema50[i]
                            candle_body = (c - o) / (h - l + 1e-9)
                            lower_wick = (o - l) / (h - l + 1e-9)
                            upper_wick = (h - c) / (h - l + 1e-9)
                            atr_ratio = a / (atr_sma[i] + 1e-9)
                            
                            entry_features = {
                                'pair': pair,
                                'time': m15['time_dt'].iloc[i],
                                'type': 'LONG',
                                'hour': hr,
                                'dow': d,
                                'hunt_bars': hunt_bars,
                                'rsi': rsi[i],
                                'dist_h1_e200_atr': dist_h1_e200,
                                'm15_ema_aligned': m15_ema_aligned,
                                'candle_body': candle_body,
                                'rejection_wick': lower_wick,
                                'atr_ratio': atr_ratio,
                                'sl_pips': sl_dist / pip_unit
                            }
                elif hunting == -1:
                    retrace = (h >= hunt_fib50) or (h >= hunt_ob_l)
                    rejection = c < o
                    if retrace and rejection:
                        raw_sl = hunt_ob_h + (hunt_atr * sl_mult)
                        sl_dist = max(raw_sl - c, min_sl_dist)
                        if sl_dist <= max_sl_dist:
                            state = -1
                            hunting = 0
                            entry_price = c
                            entry_idx = i
                            sl_price = entry_price + sl_dist
                            tp_price = entry_price - (sl_dist * rr)
                            
                            dist_h1_e200 = (h1_e200[i] - c) / (a + 1e-9)
                            m15_ema_aligned = m15_ema20[i] < m15_ema50[i]
                            candle_body = (o - c) / (h - l + 1e-9)
                            upper_wick = (h - o) / (h - l + 1e-9)
                            lower_wick = (c - l) / (h - l + 1e-9)
                            atr_ratio = a / (atr_sma[i] + 1e-9)
                            
                            entry_features = {
                                'pair': pair,
                                'time': m15['time_dt'].iloc[i],
                                'type': 'SHORT',
                                'hour': hr,
                                'dow': d,
                                'hunt_bars': hunt_bars,
                                'rsi': rsi[i],
                                'dist_h1_e200_atr': dist_h1_e200,
                                'm15_ema_aligned': m15_ema_aligned,
                                'candle_body': candle_body,
                                'rejection_wick': upper_wick,
                                'atr_ratio': atr_ratio,
                                'sl_pips': sl_dist / pip_unit
                            }
                            
    df = pd.DataFrame(all_trades)
    print(f"Total Trades Analyzed: {len(df)}")
    
    # Save to disk for quick inspection
    df.to_pickle('archives/trade_patterns_analysis.pkl')
    
    # Compare Winners vs Losers
    winners = df[df['res'] == 'WIN']
    losers = df[df['res'] == 'LOSS']
    
    print("\n" + "="*60)
    print("WINNERS VS LOSERS BEHAVIORAL COMPARISON")
    print("="*60)
    
    metrics = ['hunt_bars', 'rsi', 'dist_h1_e200_atr', 'candle_body', 'rejection_wick', 'atr_ratio', 'sl_pips', 'hold_bars']
    comp = []
    for m in metrics:
        comp.append({
            'Metric': m,
            'Winners Mean': f"{winners[m].mean():.2f}",
            'Losers Mean': f"{losers[m].mean():.2f}",
            'Winners Median': f"{winners[m].median():.2f}",
            'Losers Median': f"{losers[m].median():.2f}"
        })
    print(pd.DataFrame(comp).to_string(index=False))
    
    # 1. By Session / Hour of Day
    print("\n--- PERFORMANCE BY HOUR OF DAY (UTC) ---")
    hr_grp = df.groupby('hour').agg(
        trades=('res', 'count'),
        win_rate=('res', lambda x: (x == 'WIN').mean() * 100),
        net_R=('R', 'sum')
    )
    print(hr_grp.to_string())
    
    # 2. By Day of Week
    print("\n--- PERFORMANCE BY DAY OF WEEK (0=Mon, 4=Fri) ---")
    dow_grp = df.groupby('dow').agg(
        trades=('res', 'count'),
        win_rate=('res', lambda x: (x == 'WIN').mean() * 100),
        net_R=('R', 'sum')
    )
    print(dow_grp.to_string())
    
    # 3. By 15m EMA Alignment (Trend Momentum Confluence)
    print("\n--- PERFORMANCE BY 15m EMA ALIGNMENT ---")
    ema_grp = df.groupby('m15_ema_aligned').agg(
        trades=('res', 'count'),
        win_rate=('res', lambda x: (x == 'WIN').mean() * 100),
        net_R=('R', 'sum')
    )
    print(ema_grp.to_string())
    
    # 4. By Retracement Wait Bars (Hunt Bars)
    print("\n--- PERFORMANCE BY RETRACEMENT HUNT BARS ---")
    hunt_grp = df.groupby('hunt_bars').agg(
        trades=('res', 'count'),
        win_rate=('res', lambda x: (x == 'WIN').mean() * 100),
        net_R=('R', 'sum')
    )
    print(hunt_grp.to_string())
    
    # 5. Overextension from HTF EMA 200 (dist_h1_e200_atr bins)
    print("\n--- PERFORMANCE BY DISTANCE FROM 1H EMA 200 (in 15m ATR multiples) ---")
    df['dist_bin'] = pd.cut(df['dist_h1_e200_atr'], bins=[-10, 0, 5, 10, 15, 25, 100])
    dist_grp = df.groupby('dist_bin').agg(
        trades=('res', 'count'),
        win_rate=('res', lambda x: (x == 'WIN').mean() * 100),
        net_R=('R', 'sum')
    )
    print(dist_grp.to_string())
    
    # 6. Volatility State: ATR Ratio (Expansion vs Contraction)
    print("\n--- PERFORMANCE BY ATR RATIO (15m ATR / 20-MA ATR) ---")
    df['atr_bin'] = pd.cut(df['atr_ratio'], bins=[0, 0.8, 1.0, 1.2, 1.5, 5.0])
    atr_grp = df.groupby('atr_bin').agg(
        trades=('res', 'count'),
        win_rate=('res', lambda x: (x == 'WIN').mean() * 100),
        net_R=('R', 'sum')
    )
    print(atr_grp.to_string())
    
    # 7. Consecutive Loss Runs Analysis
    print("\n--- CONSECUTIVE LOSS DISTRIBUTION ---")
    # Compute streak lengths per pair
    streaks = []
    for p in pairs:
        p_trades = df[df['pair'] == p].copy().sort_values('time')
        current_streak = 0
        for r in p_trades['res']:
            if r == 'LOSS':
                current_streak += 1
            else:
                if current_streak > 0:
                    streaks.append(current_streak)
                current_streak = 0
        if current_streak > 0:
            streaks.append(current_streak)
            
    streak_counts = pd.Series(streaks).value_counts().sort_index()
    print("Loss Streak Length Counts across all pairs:")
    print(streak_counts.to_string())

if __name__ == '__main__':
    run_deep_trade_analysis()
