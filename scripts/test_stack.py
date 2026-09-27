import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np
from scripts.test_strategies_deep import load_data, print_summary

def test_stack_and_circuit_breaker(pairs_data, require_full_stack=True, max_sl_pips=55.0):
    results = {}
    
    for pair, tfs in pairs_data.items():
        df = tfs['H1'].copy()
        d1 = tfs['D1'].copy()
        
        is_jpy = "JPY" in pair
        pip_unit = 0.01 if is_jpy else 0.0001
        min_sl_dist = 16.0 * pip_unit
        max_sl_dist = max_sl_pips * pip_unit
        
        d1['ema50'] = d1['close'].ewm(span=50, adjust=False).mean()
        d1['time_dt'] = pd.to_datetime(d1['time'], unit='s').dt.floor('D')
        df['time_dt'] = pd.to_datetime(df['time'], unit='s')
        df['date_only'] = df['time_dt'].dt.floor('D')
        
        d1_bull_map = dict(zip(d1['time_dt'], d1['close'] > d1['ema50']))
        df['d1_bull'] = df['date_only'].map(d1_bull_map).fillna(False).values
        df['d1_bear'] = ~df['d1_bull']
        
        close = df['close'].values
        open_ = df['open'].values
        high = df['high'].values
        low = df['low'].values
        hours = df['time_dt'].dt.hour.values
        n = len(close)
        
        ema200 = df['close'].ewm(span=200, adjust=False).mean().values
        ema50 = df['close'].ewm(span=50, adjust=False).mean().values
        ema20 = df['close'].ewm(span=20, adjust=False).mean().values
        
        tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
        tr[0] = high[0] - low[0]
        atr = pd.Series(tr).rolling(14).mean().bfill().values
        
        don_h = pd.Series(high).shift(1).rolling(20).max().bfill().values
        don_l = pd.Series(low).shift(1).rolling(20).min().bfill().values
        
        delta = pd.Series(close).diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi = (100 - (100 / (1 + rs))).bfill().values
        
        break_high = (close > don_h) & (np.roll(close, 1) <= np.roll(don_h, 1))
        break_low = (close < don_l) & (np.roll(close, 1) >= np.roll(don_l, 1))
        break_high[0] = False
        break_low[0] = False
        
        prev_is_bear = np.roll(close, 1) < np.roll(open_, 1)
        prev_is_bull = np.roll(close, 1) > np.roll(open_, 1)
        ob_bull_l = np.where(prev_is_bear, np.roll(low, 1), low)
        ob_bear_h = np.where(prev_is_bull, np.roll(high, 1), high)
        
        trades = []
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
        rr = 1.5
        sl_mult = 0.5
        
        for i in range(200, n):
            c = close[i]
            h = high[i]
            l = low[i]
            o = open_[i]
            a = atr[i]
            
            if state != 0:
                if state == 1:
                    if h >= tp_price:
                        trades.append({'pair': pair, 'exit_idx': i, 'res': 'WIN', 'pips': (tp_price - entry_price) / pip_unit, 'R': rr, 'hold': i - entry_idx})
                        state = 0
                        consec_losses = 0
                    elif l <= sl_price:
                        trades.append({'pair': pair, 'exit_idx': i, 'res': 'LOSS', 'pips': (sl_price - entry_price) / pip_unit, 'R': -1.0, 'hold': i - entry_idx})
                        state = 0
                        consec_losses += 1
                        if consec_losses >= 2:
                            pause_until_idx = i + 24 # 24 bars pause on 2 consecutive losses
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (c - entry_price) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        r_mult = pips / ((entry_price - sl_price) / pip_unit)
                        trades.append({'pair': pair, 'exit_idx': i, 'res': res, 'pips': pips, 'R': r_mult, 'hold': i - entry_idx})
                        state = 0
                        if res == 'LOSS':
                            consec_losses += 1
                            if consec_losses >= 2:
                                pause_until_idx = i + 24
                                consec_losses = 0
                        else:
                            consec_losses = 0
                elif state == -1:
                    if l <= tp_price:
                        trades.append({'pair': pair, 'exit_idx': i, 'res': 'WIN', 'pips': (entry_price - tp_price) / pip_unit, 'R': rr, 'hold': i - entry_idx})
                        state = 0
                        consec_losses = 0
                    elif h >= sl_price:
                        trades.append({'pair': pair, 'exit_idx': i, 'res': 'LOSS', 'pips': (entry_price - sl_price) / pip_unit, 'R': -1.0, 'hold': i - entry_idx})
                        state = 0
                        consec_losses += 1
                        if consec_losses >= 2:
                            pause_until_idx = i + 24
                            consec_losses = 0
                    elif (i - entry_idx) >= 160:
                        pips = (entry_price - c) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        r_mult = pips / ((sl_price - entry_price) / pip_unit)
                        trades.append({'pair': pair, 'exit_idx': i, 'res': res, 'pips': pips, 'R': r_mult, 'hold': i - entry_idx})
                        state = 0
                        if res == 'LOSS':
                            consec_losses += 1
                            if consec_losses >= 2:
                                pause_until_idx = i + 24
                                consec_losses = 0
                        else:
                            consec_losses = 0
                continue
                
            if i < pause_until_idx:
                continue
                
            if hunting == 0:
                if require_full_stack:
                    # Full institutional alignment: 20 > 50 > 200 for long, 20 < 50 < 200 for short
                    trend_long = (ema20[i] > ema50[i]) and (ema50[i] > ema200[i]) and (c > ema200[i])
                    trend_short = (ema20[i] < ema50[i]) and (ema50[i] < ema200[i]) and (c < ema200[i])
                else:
                    trend_long = (ema20[i] > ema50[i]) and (c > ema200[i])
                    trend_short = (ema20[i] < ema50[i]) and (c < ema200[i])
                    
                long_cond = (break_high[i] and trend_long and rsi[i] >= 45 and rsi[i] <= 70 and df['d1_bull'].iloc[i])
                short_cond = (break_low[i] and trend_short and rsi[i] >= 30 and rsi[i] <= 55 and df['d1_bear'].iloc[i])
                
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
                if (i - hunt_idx) > 4: # Max 4 bars wait!
                    hunting = 0
                elif hunting == 1:
                    retrace = (l <= hunt_fib50) or (l <= hunt_ob_h)
                    rejection = c > o
                    if retrace and rejection and hours[i] != 21:
                        raw_sl = hunt_ob_l - (hunt_atr * sl_mult)
                        sl_dist = max(c - raw_sl, min_sl_dist)
                        if sl_dist <= max_sl_dist: # Volatility guard!
                            state = 1
                            hunting = 0
                            entry_price = c
                            entry_idx = i
                            sl_price = entry_price - sl_dist
                            tp_price = entry_price + (sl_dist * rr)
                elif hunting == -1:
                    retrace = (h >= hunt_fib50) or (h >= hunt_ob_l)
                    rejection = c < o
                    if retrace and rejection and hours[i] != 21:
                        raw_sl = hunt_ob_h + (hunt_atr * sl_mult)
                        sl_dist = max(raw_sl - c, min_sl_dist)
                        if sl_dist <= max_sl_dist:
                            state = -1
                            hunting = 0
                            entry_price = c
                            entry_idx = i
                            sl_price = entry_price + sl_dist
                            tp_price = entry_price - (sl_dist * rr)
                            
        results[pair] = pd.DataFrame(trades)
    return results

data = load_data()
print("\n--- TEST: STANDARD TREND FILTER (EMA 20 > EMA 50 and Close > EMA 200) ---")
res_std = test_stack_and_circuit_breaker(data, require_full_stack=False, max_sl_pips=55.0)
print_summary(res_std, "Standard Trend Filter + Volatility Guard + Circuit Breaker")

print("\n--- TEST: FULL INSTITUTIONAL STACK (EMA 20 > EMA 50 > EMA 200) ---")
res_stack = test_stack_and_circuit_breaker(data, require_full_stack=True, max_sl_pips=55.0)
print_summary(res_stack, "Full EMA Stack Alignment + Volatility Guard + Circuit Breaker")
