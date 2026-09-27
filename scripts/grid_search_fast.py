import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np
from itertools import product
from scripts.test_strategies_deep import load_data

def evaluate_parameters():
    pairs_data = load_data()
    
    # We want to test combinations of:
    # 1. rr: [1.4, 1.5, 1.6, 1.75]
    # 2. sl_mult: [0.3, 0.5, 0.75]
    # 3. min_sl_pips: [15.0, 18.0, 22.0]
    # 4. donch_len: [20, 24]
    # 5. max_hunt: [4, 6, 8]
    # 6. require_strong_rejection: [False (c > o), True (c > h[1])]
    
    param_grid = {
        'rr': [1.4, 1.5, 1.6, 1.75],
        'sl_mult': [0.4, 0.6, 0.8],
        'min_sl_pips': [16.0, 20.0],
        'donch_len': [20, 24],
        'max_hunt': [4, 6]
    }
    
    # Pre-calculate data for each pair to make grid search lightning fast
    precomputed = {}
    for pair, tfs in pairs_data.items():
        df = tfs['H1'].copy()
        d1 = tfs['D1'].copy()
        is_jpy = "JPY" in pair
        pip_unit = 0.01 if is_jpy else 0.0001
        
        d1['ema50'] = d1['close'].ewm(span=50, adjust=False).mean()
        d1['time_dt'] = pd.to_datetime(d1['time'], unit='s').dt.floor('D')
        df['time_dt'] = pd.to_datetime(df['time'], unit='s')
        df['date_only'] = df['time_dt'].dt.floor('D')
        d1_bull_map = dict(zip(d1['time_dt'], d1['close'] > d1['ema50']))
        d1_bull = df['date_only'].map(d1_bull_map).fillna(False).values
        d1_bear = ~d1_bull
        
        close = df['close'].values
        open_ = df['open'].values
        high = df['high'].values
        low = df['low'].values
        hours = df['time_dt'].dt.hour.values
        
        ema200 = df['close'].ewm(span=200, adjust=False).mean().values
        ema50 = df['close'].ewm(span=50, adjust=False).mean().values
        ema20 = df['close'].ewm(span=20, adjust=False).mean().values
        
        tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
        tr[0] = high[0] - low[0]
        atr = pd.Series(tr).rolling(14).mean().bfill().values
        
        delta = pd.Series(close).diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi = (100 - (100 / (1 + rs))).bfill().values
        
        prev_is_bear = np.roll(close, 1) < np.roll(open_, 1)
        prev_is_bull = np.roll(close, 1) > np.roll(open_, 1)
        ob_bull_l = np.where(prev_is_bear, np.roll(low, 1), low)
        ob_bear_h = np.where(prev_is_bull, np.roll(high, 1), high)
        
        precomputed[pair] = {
            'close': close, 'open': open_, 'high': high, 'low': low, 'hours': hours,
            'ema200': ema200, 'ema50': ema50, 'ema20': ema20, 'atr': atr, 'rsi': rsi,
            'd1_bull': d1_bull, 'd1_bear': d1_bear, 'ob_bull_l': ob_bull_l, 'ob_bear_h': ob_bear_h,
            'pip_unit': pip_unit, 'n': len(close)
        }

    keys, values = zip(*param_grid.items())
    all_combos = [dict(zip(keys, v)) for v in product(*values)]
    print(f"Total parameter combinations to test: {len(all_combos)}")
    
    results_list = []
    
    for combo in all_combos:
        rr = combo['rr']
        sl_mult = combo['sl_mult']
        min_sl_pips = combo['min_sl_pips']
        donch_len = combo['donch_len']
        max_hunt = combo['max_hunt']
        
        tot_trades = 0
        tot_wins = 0
        tot_gross_win = 0.0
        tot_gross_loss = 0.0
        tot_net_r = 0.0
        
        for pair, pdata in precomputed.items():
            close = pdata['close']
            open_ = pdata['open']
            high = pdata['high']
            low = pdata['low']
            hours = pdata['hours']
            ema200 = pdata['ema200']
            ema50 = pdata['ema50']
            ema20 = pdata['ema20']
            atr = pdata['atr']
            rsi = pdata['rsi']
            d1_bull = pdata['d1_bull']
            d1_bear = pdata['d1_bear']
            ob_bull_l = pdata['ob_bull_l']
            ob_bear_h = pdata['ob_bear_h']
            pip_unit = pdata['pip_unit']
            min_sl_dist = min_sl_pips * pip_unit
            n = pdata['n']
            
            don_h = pd.Series(high).shift(1).rolling(donch_len).max().bfill().values
            don_l = pd.Series(low).shift(1).rolling(donch_len).min().bfill().values
            break_high = (close > don_h) & (np.roll(close, 1) <= np.roll(don_h, 1))
            break_low = (close < don_l) & (np.roll(close, 1) >= np.roll(don_l, 1))
            break_high[0] = False
            break_low[0] = False
            
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
            
            for i in range(200, n):
                c = close[i]
                h = high[i]
                l = low[i]
                o = open_[i]
                a = atr[i]
                
                if state != 0:
                    if state == 1:
                        if h >= tp_price:
                            tot_trades += 1
                            tot_wins += 1
                            tot_gross_win += rr
                            tot_net_r += rr
                            state = 0
                        elif l <= sl_price:
                            tot_trades += 1
                            tot_gross_loss += 1.0
                            tot_net_r -= 1.0
                            state = 0
                        elif (i - entry_idx) >= 160:
                            pips = (c - entry_price) / pip_unit
                            r_mult = pips / ((entry_price - sl_price) / pip_unit)
                            tot_trades += 1
                            if r_mult > 0:
                                tot_wins += 1
                                tot_gross_win += r_mult
                            else:
                                tot_gross_loss += abs(r_mult)
                            tot_net_r += r_mult
                            state = 0
                    elif state == -1:
                        if l <= tp_price:
                            tot_trades += 1
                            tot_wins += 1
                            tot_gross_win += rr
                            tot_net_r += rr
                            state = 0
                        elif h >= sl_price:
                            tot_trades += 1
                            tot_gross_loss += 1.0
                            tot_net_r -= 1.0
                            state = 0
                        elif (i - entry_idx) >= 160:
                            pips = (entry_price - c) / pip_unit
                            r_mult = pips / ((sl_price - entry_price) / pip_unit)
                            tot_trades += 1
                            if r_mult > 0:
                                tot_wins += 1
                                tot_gross_win += r_mult
                            else:
                                tot_gross_loss += abs(r_mult)
                            tot_net_r += r_mult
                            state = 0
                    continue
                
                if hunting == 0:
                    long_cond = (break_high[i] and c > ema200[i] and ema20[i] > ema50[i] and 
                                 rsi[i] >= 45 and rsi[i] <= 70 and d1_bull[i])
                    short_cond = (break_low[i] and c < ema200[i] and ema20[i] < ema50[i] and 
                                  rsi[i] >= 30 and rsi[i] <= 55 and d1_bear[i])
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
                        rejection = c > o
                        if retrace and rejection and hours[i] != 21:
                            state = 1
                            hunting = 0
                            entry_price = c
                            entry_idx = i
                            raw_sl = hunt_ob_l - (hunt_atr * sl_mult)
                            sl_dist = max(entry_price - raw_sl, min_sl_dist)
                            sl_price = entry_price - sl_dist
                            tp_price = entry_price + (sl_dist * rr)
                    elif hunting == -1:
                        retrace = (h >= hunt_fib50) or (h >= hunt_ob_l)
                        rejection = c < o
                        if retrace and rejection and hours[i] != 21:
                            state = -1
                            hunting = 0
                            entry_price = c
                            entry_idx = i
                            raw_sl = hunt_ob_h + (hunt_atr * sl_mult)
                            sl_dist = max(raw_sl - entry_price, min_sl_dist)
                            sl_price = entry_price + sl_dist
                            tp_price = entry_price - (sl_dist * rr)
        
        wr = (tot_wins / tot_trades * 100) if tot_trades > 0 else 0
        pf = (tot_gross_win / (tot_gross_loss + 1e-9)) if tot_trades > 0 else 0
        results_list.append({
            **combo,
            'trades': tot_trades,
            'win_rate': round(wr, 1),
            'profit_factor': round(pf, 2),
            'net_r': round(tot_net_r, 1)
        })
        
    df_res = pd.DataFrame(results_list)
    df_res = df_res.sort_values(by='net_r', ascending=False)
    print("\n" + "="*80)
    print("TOP 15 PARAMETER COMBINATIONS BY NET R")
    print("="*80)
    print(df_res.head(15).to_string())
    
    df_pf = df_res.sort_values(by='profit_factor', ascending=False)
    print("\n" + "="*80)
    print("TOP 10 PARAMETER COMBINATIONS BY PROFIT FACTOR")
    print("="*80)
    print(df_pf.head(10).to_string())

if __name__ == '__main__':
    evaluate_parameters()
