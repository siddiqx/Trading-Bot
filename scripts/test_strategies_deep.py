import pickle
import pandas as pd
import numpy as np

def load_data():
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        data = pickle.load(f)
    return data[1]

def run_numpy_backtest(pairs_data, strat_type="trend_retrace", rr=1.5, sl_mult=0.5, min_sl_pips=18.0, 
                       use_cb=True, cb_limit=2, cb_pause=16, donch_len=20, max_hunt=12, require_rejection=True):
    results = {}
    
    for pair, tfs in pairs_data.items():
        df = tfs['H1'].copy()
        d1 = tfs['D1'].copy()
        
        is_jpy = "JPY" in pair
        pip_unit = 0.01 if is_jpy else 0.0001
        min_sl_dist = min_sl_pips * pip_unit
        
        # D1 EMA 50
        d1['ema50'] = d1['close'].ewm(span=50, adjust=False).mean()
        d1['time_dt'] = pd.to_datetime(d1['time'], unit='s').dt.floor('D')
        df['time_dt'] = pd.to_datetime(df['time'], unit='s')
        df['date_only'] = df['time_dt'].dt.floor('D')
        
        d1_bull_map = dict(zip(d1['time_dt'], d1['close'] > d1['ema50']))
        df['d1_bull'] = df['date_only'].map(d1_bull_map).fillna(False).values
        df['d1_bear'] = ~df['d1_bull']
        
        # H1 indicators
        close = df['close'].values
        open_ = df['open'].values
        high = df['high'].values
        low = df['low'].values
        n = len(close)
        
        ema200 = df['close'].ewm(span=200, adjust=False).mean().values
        ema50 = df['close'].ewm(span=50, adjust=False).mean().values
        ema20 = df['close'].ewm(span=20, adjust=False).mean().values
        
        # ATR
        tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
        tr[0] = high[0] - low[0]
        atr = pd.Series(tr).rolling(14).mean().bfill().values
        
        # Donchian
        don_h = pd.Series(high).shift(1).rolling(donch_len).max().bfill().values
        don_l = pd.Series(low).shift(1).rolling(donch_len).min().bfill().values
        
        # RSI
        delta = pd.Series(close).diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi = (100 - (100 / (1 + rs))).bfill().values
        
        # Breakouts
        break_high = (close > don_h) & (np.roll(close, 1) <= np.roll(don_h, 1))
        break_low = (close < don_l) & (np.roll(close, 1) >= np.roll(don_l, 1))
        break_high[0] = False
        break_low[0] = False
        
        # OB levels
        prev_is_bear = np.roll(close, 1) < np.roll(open_, 1)
        prev_is_bull = np.roll(close, 1) > np.roll(open_, 1)
        ob_bull_l = np.where(prev_is_bear, np.roll(low, 1), low)
        ob_bear_h = np.where(prev_is_bull, np.roll(high, 1), high)
        
        d1_bull = df['d1_bull'].values
        d1_bear = df['d1_bear'].values
        
        trades = []
        state = 0
        entry_price = 0.0
        sl_price = 0.0
        tp_price = 0.0
        entry_idx = 0
        consec_losses = 0
        pause_until_idx = -999
        
        hunting = 0
        hunt_idx = 0
        hunt_ob_l = 0.0
        hunt_ob_h = 0.0
        hunt_fib50 = 0.0
        hunt_atr = 0.0
        
        # Store context at entry to learn winners vs losers
        entry_meta = {}
        
        for i in range(200, n):
            c = close[i]
            h = high[i]
            l = low[i]
            o = open_[i]
            a = atr[i]
            
            if state != 0:
                if state == 1:
                    if h >= tp_price:
                        pips = (tp_price - entry_price) / pip_unit
                        trades.append({**entry_meta, 'pair': pair, 'exit_idx': i, 'res': 'WIN', 'pips': pips, 'R': rr, 'hold': i - entry_idx})
                        state = 0
                        consec_losses = 0
                    elif l <= sl_price:
                        pips = (sl_price - entry_price) / pip_unit
                        trades.append({**entry_meta, 'pair': pair, 'exit_idx': i, 'res': 'LOSS', 'pips': pips, 'R': -1.0, 'hold': i - entry_idx})
                        state = 0
                        consec_losses += 1
                        if use_cb and consec_losses >= cb_limit:
                            pause_until_idx = i + cb_pause
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (c - entry_price) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        r_mult = pips / ((entry_price - sl_price) / pip_unit)
                        trades.append({**entry_meta, 'pair': pair, 'exit_idx': i, 'res': res, 'pips': pips, 'R': r_mult, 'hold': i - entry_idx})
                        state = 0
                        if res == 'LOSS':
                            consec_losses += 1
                            if use_cb and consec_losses >= cb_limit:
                                pause_until_idx = i + cb_pause
                                consec_losses = 0
                        else:
                            consec_losses = 0
                elif state == -1:
                    if l <= tp_price:
                        pips = (entry_price - tp_price) / pip_unit
                        trades.append({**entry_meta, 'pair': pair, 'exit_idx': i, 'res': 'WIN', 'pips': pips, 'R': rr, 'hold': i - entry_idx})
                        state = 0
                        consec_losses = 0
                    elif h >= sl_price:
                        pips = (entry_price - sl_price) / pip_unit
                        trades.append({**entry_meta, 'pair': pair, 'exit_idx': i, 'res': 'LOSS', 'pips': pips, 'R': -1.0, 'hold': i - entry_idx})
                        state = 0
                        consec_losses += 1
                        if use_cb and consec_losses >= cb_limit:
                            pause_until_idx = i + cb_pause
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (entry_price - c) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        r_mult = pips / ((sl_price - entry_price) / pip_unit)
                        trades.append({**entry_meta, 'pair': pair, 'exit_idx': i, 'res': res, 'pips': pips, 'R': r_mult, 'hold': i - entry_idx})
                        state = 0
                        if res == 'LOSS':
                            consec_losses += 1
                            if use_cb and consec_losses >= cb_limit:
                                pause_until_idx = i + cb_pause
                                consec_losses = 0
                        else:
                            consec_losses = 0
                continue
            
            if i < pause_until_idx:
                continue
                
            if strat_type == "trend_retrace":
                if hunting == 0:
                    long_cond = (break_high[i] and c > ema200[i] and ema20[i] > ema50[i] and 
                                 rsi[i] >= 45 and rsi[i] <= 72 and d1_bull[i])
                    short_cond = (break_low[i] and c < ema200[i] and ema20[i] < ema50[i] and 
                                  rsi[i] >= 28 and rsi[i] <= 55 and d1_bear[i])
                    if long_cond:
                        hunting = 1
                        hunt_idx = i
                        hunt_ob_l = ob_bull_l[i]
                        hunt_ob_h = high[i]
                        hunt_fib50 = hunt_ob_h - 0.5 * (hunt_ob_h - hunt_ob_l)
                        hunt_atr = a
                    elif short_cond:
                        hunting = -1
                        hunt_idx = i
                        hunt_ob_h = ob_bear_h[i]
                        hunt_ob_l = low[i]
                        hunt_fib50 = hunt_ob_l + 0.5 * (hunt_ob_h - hunt_ob_l)
                        hunt_atr = a
                else:
                    if (i - hunt_idx) > max_hunt:
                        hunting = 0
                    elif hunting == 1:
                        retrace = (l <= hunt_fib50) or (l <= hunt_ob_h)
                        rejection = (c > o) if require_rejection else True
                        if retrace and rejection:
                            state = 1
                            hunting = 0
                            entry_price = c
                            entry_idx = i
                            raw_sl = hunt_ob_l - (hunt_atr * sl_mult)
                            sl_dist = max(entry_price - raw_sl, min_sl_dist)
                            sl_price = entry_price - sl_dist
                            tp_price = entry_price + (sl_dist * rr)
                            
                            # Capture behavioral features for machine learning / pattern analysis
                            entry_meta = {
                                'pair': pair,
                                'entry_idx': i,
                                'type': 'LONG',
                                'rsi': rsi[i],
                                'atr_pips': a / pip_unit,
                                'sl_pips': sl_dist / pip_unit,
                                'bars_waited': i - hunt_idx,
                                'ema20_dist': (c - ema20[i]) / pip_unit,
                                'ema50_dist': (c - ema50[i]) / pip_unit,
                                'ema200_dist': (c - ema200[i]) / pip_unit,
                                'hour': df['time_dt'].iloc[i].hour,
                                'day_of_week': df['time_dt'].iloc[i].dayofweek
                            }
                    elif hunting == -1:
                        retrace = (h >= hunt_fib50) or (h >= hunt_ob_l)
                        rejection = (c < o) if require_rejection else True
                        if retrace and rejection:
                            state = -1
                            hunting = 0
                            entry_price = c
                            entry_idx = i
                            raw_sl = hunt_ob_h + (hunt_atr * sl_mult)
                            sl_dist = max(raw_sl - entry_price, min_sl_dist)
                            sl_price = entry_price + sl_dist
                            tp_price = entry_price - (sl_dist * rr)
                            
                            entry_meta = {
                                'pair': pair,
                                'entry_idx': i,
                                'type': 'SHORT',
                                'rsi': rsi[i],
                                'atr_pips': a / pip_unit,
                                'sl_pips': sl_dist / pip_unit,
                                'bars_waited': i - hunt_idx,
                                'ema20_dist': (ema20[i] - c) / pip_unit,
                                'ema50_dist': (ema50[i] - c) / pip_unit,
                                'ema200_dist': (ema200[i] - c) / pip_unit,
                                'hour': df['time_dt'].iloc[i].hour,
                                'day_of_week': df['time_dt'].iloc[i].dayofweek
                            }
            elif strat_type == "direct_breakout":
                long_cond = (break_high[i] and c > ema200[i] and ema20[i] > ema50[i] and 
                             rsi[i] >= 45 and rsi[i] <= 70 and d1_bull[i])
                short_cond = (break_low[i] and c < ema200[i] and ema20[i] < ema50[i] and 
                              rsi[i] >= 30 and rsi[i] <= 55 and d1_bear[i])
                if long_cond:
                    state = 1
                    entry_price = c
                    entry_idx = i
                    raw_sl = ob_bull_l[i] - (a * sl_mult)
                    sl_dist = max(entry_price - raw_sl, min_sl_dist)
                    sl_price = entry_price - sl_dist
                    tp_price = entry_price + (sl_dist * rr)
                    entry_meta = {
                        'pair': pair,
                        'entry_idx': i,
                        'type': 'LONG',
                        'rsi': rsi[i],
                        'atr_pips': a / pip_unit,
                        'sl_pips': sl_dist / pip_unit,
                        'bars_waited': 0,
                        'ema20_dist': (c - ema20[i]) / pip_unit,
                        'ema50_dist': (c - ema50[i]) / pip_unit,
                        'ema200_dist': (c - ema200[i]) / pip_unit,
                        'hour': df['time_dt'].iloc[i].hour,
                        'day_of_week': df['time_dt'].iloc[i].dayofweek
                    }
                elif short_cond:
                    state = -1
                    entry_price = c
                    entry_idx = i
                    raw_sl = ob_bear_h[i] + (a * sl_mult)
                    sl_dist = max(raw_sl - entry_price, min_sl_dist)
                    sl_price = entry_price + sl_dist
                    tp_price = entry_price - (sl_dist * rr)
                    entry_meta = {
                        'pair': pair,
                        'entry_idx': i,
                        'type': 'SHORT',
                        'rsi': rsi[i],
                        'atr_pips': a / pip_unit,
                        'sl_pips': sl_dist / pip_unit,
                        'bars_waited': 0,
                        'ema20_dist': (ema20[i] - c) / pip_unit,
                        'ema50_dist': (ema50[i] - c) / pip_unit,
                        'ema200_dist': (ema200[i] - c) / pip_unit,
                        'hour': df['time_dt'].iloc[i].hour,
                        'day_of_week': df['time_dt'].iloc[i].dayofweek
                    }
        results[pair] = pd.DataFrame(trades)
    return results

def print_summary(results, title=""):
    print("="*75)
    print(f"RESULTS: {title}")
    print("="*75)
    total_trades = 0
    total_wins = 0
    total_r = 0.0
    total_pips = 0.0
    all_trades = []
    
    for pair, df in results.items():
        if len(df) == 0:
            print(f"{pair:7s} | 0 trades")
            continue
        all_trades.append(df)
        n = len(df)
        wins = (df['res'] == 'WIN').sum()
        wr = wins / n * 100
        gross_win_r = df[df['R'] > 0]['R'].sum()
        gross_loss_r = abs(df[df['R'] < 0]['R'].sum())
        pf = gross_win_r / (gross_loss_r + 1e-9)
        net_r = df['R'].sum()
        pips = df['pips'].sum()
        
        is_loss = (df['res'] == 'LOSS').astype(int)
        loss_streaks = []
        cur_streak = 0
        for l in is_loss:
            if l == 1:
                cur_streak += 1
            else:
                if cur_streak > 0:
                    loss_streaks.append(cur_streak)
                cur_streak = 0
        if cur_streak > 0:
            loss_streaks.append(cur_streak)
        max_cl = max(loss_streaks) if loss_streaks else 0
        
        print(f"{pair:7s} | Trades: {n:4d} | WinRate: {wr:5.1f}% | PF: {pf:4.2f} | Net R: {net_r:+6.1f}R | Net Pips: {pips:+7.0f} | Max Cons Loss: {max_cl}")
        total_trades += n
        total_wins += wins
        total_r += net_r
        total_pips += pips
        
    tot_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0
    gross_w = sum(df[df['R'] > 0]['R'].sum() for df in all_trades) if all_trades else 0
    gross_l = sum(abs(df[df['R'] < 0]['R'].sum()) for df in all_trades) if all_trades else 0
    port_pf = gross_w / (gross_l + 1e-9)
    print("-"*75)
    print(f"PORTFOLIO TOTAL | Trades: {total_trades:4d} | Avg WR: {tot_wr:5.1f}% | PF: {port_pf:4.2f} | Net R: {total_r:+6.1f}R | Net Pips: {total_pips:+.0f}")
    print("="*75)
    return pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()

if __name__ == '__main__':
    data = load_data()
    print("Running Fast Numpy Backtests across 2022-2026 data...")
    res_retrace = run_numpy_backtest(data, strat_type="trend_retrace", rr=1.5, sl_mult=0.5, min_sl_pips=18.0)
    df_retrace = print_summary(res_retrace, "Trend Retrace (1H Pullback + Rejection) RR=1.5")
    
    res_direct = run_numpy_backtest(data, strat_type="direct_breakout", rr=1.5, sl_mult=0.5, min_sl_pips=18.0)
    df_direct = print_summary(res_direct, "Direct Breakout on Bar Close RR=1.5")
