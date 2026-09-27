import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np
from scripts.test_strategies_deep import load_data, print_summary

def test_liquidity_sweep(pairs_data, rr=1.5, sl_mult=0.5, min_sl_pips=16.0):
    results = {}
    for pair, tfs in pairs_data.items():
        df = tfs['H1'].copy()
        d1 = tfs['D1'].copy()
        is_jpy = "JPY" in pair
        pip_unit = 0.01 if is_jpy else 0.0001
        min_sl_dist = min_sl_pips * pip_unit
        
        close = df['close'].values
        open_ = df['open'].values
        high = df['high'].values
        low = df['low'].values
        n = len(close)
        
        tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
        tr[0] = high[0] - low[0]
        atr = pd.Series(tr).rolling(14).mean().bfill().values
        
        don_h = pd.Series(high).shift(1).rolling(20).max().bfill().values
        don_l = pd.Series(low).shift(1).rolling(20).min().bfill().values
        
        # Sweep condition:
        # Long: Low pierced below don_l, but Close finished ABOVE don_l (sweep of sell-side liquidity)
        sweep_long = (low < don_l) & (close > don_l) & (close > open_)
        # Short: High pierced above don_h, but Close finished BELOW don_h (sweep of buy-side liquidity)
        sweep_short = (high > don_h) & (close < don_h) & (close < open_)
        
        trades = []
        state = 0
        entry_price = 0.0
        sl_price = 0.0
        tp_price = 0.0
        entry_idx = 0
        
        for i in range(200, n):
            c = close[i]
            h = high[i]
            l = low[i]
            a = atr[i]
            
            if state != 0:
                if state == 1:
                    if h >= tp_price:
                        trades.append({'pair': pair, 'exit_idx': i, 'res': 'WIN', 'pips': (tp_price - entry_price) / pip_unit, 'R': rr, 'hold': i - entry_idx})
                        state = 0
                    elif l <= sl_price:
                        trades.append({'pair': pair, 'exit_idx': i, 'res': 'LOSS', 'pips': (sl_price - entry_price) / pip_unit, 'R': -1.0, 'hold': i - entry_idx})
                        state = 0
                    elif (i - entry_idx) >= 160:
                        pips = (c - entry_price) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        r_mult = pips / ((entry_price - sl_price) / pip_unit)
                        trades.append({'pair': pair, 'exit_idx': i, 'res': res, 'pips': pips, 'R': r_mult, 'hold': i - entry_idx})
                        state = 0
                elif state == -1:
                    if l <= tp_price:
                        trades.append({'pair': pair, 'exit_idx': i, 'res': 'WIN', 'pips': (entry_price - tp_price) / pip_unit, 'R': rr, 'hold': i - entry_idx})
                        state = 0
                    elif h >= sl_price:
                        trades.append({'pair': pair, 'exit_idx': i, 'res': 'LOSS', 'pips': (entry_price - sl_price) / pip_unit, 'R': -1.0, 'hold': i - entry_idx})
                        state = 0
                    elif (i - entry_idx) >= 160:
                        pips = (entry_price - c) / pip_unit
                        res = 'WIN' if pips > 0 else 'LOSS'
                        r_mult = pips / ((sl_price - entry_price) / pip_unit)
                        trades.append({'pair': pair, 'exit_idx': i, 'res': res, 'pips': pips, 'R': r_mult, 'hold': i - entry_idx})
                        state = 0
                continue
                
            if sweep_long[i]:
                state = 1
                entry_price = c
                entry_idx = i
                raw_sl = l - (a * sl_mult)
                sl_dist = max(entry_price - raw_sl, min_sl_dist)
                sl_price = entry_price - sl_dist
                tp_price = entry_price + (sl_dist * rr)
            elif sweep_short[i]:
                state = -1
                entry_price = c
                entry_idx = i
                raw_sl = h + (a * sl_mult)
                sl_dist = max(raw_sl - entry_price, min_sl_dist)
                sl_price = entry_price + sl_dist
                tp_price = entry_price - (sl_dist * rr)
                
        results[pair] = pd.DataFrame(trades)
    return results

data = load_data()
res_sweep = test_liquidity_sweep(data, rr=1.5, sl_mult=0.5, min_sl_pips=16.0)
print_summary(res_sweep, "Pure ICT Liquidity Sweep Reversals (Turtle Soup)")
