import pickle
import pandas as pd
import numpy as np

with open('archives/data_cache.pkl', 'rb') as f:
    cache = pickle.load(f)[1]

from scratch_research_ob_fib import prepare_data, pairs

data_dict = {}
for p in pairs:
    data_dict[p] = prepare_data(cache[p]['H1'], cache[p]['D1'])

def test_exact_ob_fib_model(df, exit_target='fib_272'):
    c = df['close'].values
    o = df['open'].values
    h = df['high'].values
    l = df['low'].values
    ema20 = df['ema20'].values
    ema50 = df['ema50'].values
    ema200 = df['ema200'].values
    atr = df['atr14'].values
    adx = df['adx14'].values
    adx_slope = df['adx_slope'].values
    rsi = df['rsi14'].values
    sess = df['session_ok'].values
    d1_bull = df['d1_bull'].values
    d1_bear = df['d1_bear'].values
    dh = df['dh_48'].values
    dl = df['dl_48'].values
    
    n = len(c)
    trades = []
    in_pos = False
    pending = False
    pos_type = 0
    limit_price = 0.0
    pending_sl = 0.0
    pending_tp = 0.0
    pending_expire = 0
    entry_p = 0.0
    sl_p = 0.0
    tp_p = 0.0
    risk = 0.0
    actual_rr = 0.0
    
    for i in range(100, n):
        if in_pos:
            hi = h[i]
            li = l[i]
            if pos_type == 1:
                if li <= sl_p:
                    trades.append(-1.0)
                    in_pos = False
                elif hi >= tp_p:
                    trades.append(actual_rr)
                    in_pos = False
            elif pos_type == -1:
                if hi >= sl_p:
                    trades.append(-1.0)
                    in_pos = False
                elif li <= tp_p:
                    trades.append(actual_rr)
                    in_pos = False
            continue
            
        if pending:
            if i > pending_expire:
                pending = False
            else:
                if pos_type == 1:
                    if l[i] <= limit_price:
                        in_pos = True
                        pending = False
                        entry_p = limit_price
                        sl_p = pending_sl
                        tp_p = pending_tp
                        risk = entry_p - sl_p
                        actual_rr = (tp_p - entry_p) / risk if risk > 0 else 1.5
                        continue
                elif pos_type == -1:
                    if h[i] >= limit_price:
                        in_pos = True
                        pending = False
                        entry_p = limit_price
                        sl_p = pending_sl
                        tp_p = pending_tp
                        risk = sl_p - entry_p
                        actual_rr = (entry_p - tp_p) / risk if risk > 0 else 1.5
                        continue
                        
        prev_c = c[i-1]
        prev_dh = dh[i-1]
        prev_dl = dl[i-1]
        curr_c = c[i]
        curr_dh = dh[i]
        curr_dl = dl[i]
        
        long_bo = (prev_c <= prev_dh) and (curr_c > curr_dh)
        short_bo = (prev_c >= prev_dl) and (curr_c < curr_dl)
        
        if not (long_bo or short_bo):
            continue
            
        if not sess[i]:
            continue
        if long_bo and not (d1_bull[i] and curr_c > ema200[i] and ema20[i] > ema50[i]):
            continue
        if short_bo and not (d1_bear[i] and curr_c < ema200[i] and ema20[i] < ema50[i]):
            continue
        if adx[i] < 20 or adx_slope[i] <= 0:
            continue
        if long_bo and (rsi[i] < 55 or rsi[i] > 75):
            continue
        if short_bo and (rsi[i] > 45 or rsi[i] < 25):
            continue
            
        if long_bo:
            # Find origin Order Block (last bearish candle)
            ob_idx = i - 1
            for k in range(1, 6):
                if c[i - k] < o[i - k]:
                    ob_idx = i - k
                    break
            ob_h = h[ob_idx]
            ob_l = l[ob_idx]
            
            swing_low = ob_l
            swing_high = h[i]
            rng = swing_high - swing_low
            if rng <= 0:
                continue
                
            fib_50 = swing_high - (0.50 * rng)
            fib_618 = swing_high - (0.618 * rng)
            # Entry: confluence between Order Block top and Equilibrium / Fib 50
            entry_level = min(ob_h, fib_50)
            sl_level = ob_l - (0.15 * atr[i])
            risk_dist = entry_level - sl_level
            if risk_dist <= 0:
                continue
                
            if exit_target == 'fib_272':
                tp_level = swing_high + (0.272 * rng)
            elif exit_target == 'fib_618':
                tp_level = swing_high + (0.618 * rng)
            else:
                tp_level = entry_level + (risk_dist * 1.5)
                
            if (tp_level - entry_level) / risk_dist < 1.2:
                tp_level = entry_level + (risk_dist * 1.5)
                
            pending = True
            pos_type = 1
            limit_price = entry_level
            pending_sl = sl_level
            pending_tp = tp_level
            pending_expire = i + 8
            
        elif short_bo:
            ob_idx = i - 1
            for k in range(1, 6):
                if c[i - k] > o[i - k]:
                    ob_idx = i - k
                    break
            ob_h = h[ob_idx]
            ob_l = l[ob_idx]
            
            swing_high = ob_h
            swing_low = l[i]
            rng = swing_high - swing_low
            if rng <= 0:
                continue
                
            fib_50 = swing_low + (0.50 * rng)
            fib_618 = swing_low + (0.618 * rng)
            entry_level = max(ob_l, fib_50)
            sl_level = ob_h + (0.15 * atr[i])
            risk_dist = sl_level - entry_level
            if risk_dist <= 0:
                continue
                
            if exit_target == 'fib_272':
                tp_level = swing_low - (0.272 * rng)
            elif exit_target == 'fib_618':
                tp_level = swing_low - (0.618 * rng)
            else:
                tp_level = entry_level - (risk_dist * 1.5)
                
            if (entry_level - tp_level) / risk_dist < 1.2:
                tp_level = entry_level - (risk_dist * 1.5)
                
            pending = True
            pos_type = -1
            limit_price = entry_level
            pending_sl = sl_level
            pending_tp = tp_level
            pending_expire = i + 8
            
    if not trades:
        return {'trades': 0, 'win_rate': 0.0, 'profit_factor': 0.0, 'total_r': 0.0, 'max_dd_r': 0.0, 'wins': 0, 'losses': 0}
        
    trades = np.array(trades)
    wins = np.sum(trades > 0)
    losses = np.sum(trades <= 0)
    tot_trades = len(trades)
    win_rate = (wins / tot_trades) * 100.0
    gross_p = np.sum(trades[trades > 0])
    gross_l = np.abs(np.sum(trades[trades <= 0]))
    pf = (gross_p / gross_l) if gross_l > 0 else 99.0
    tot_r = np.sum(trades)
    
    equity = np.cumsum(trades)
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    max_dd = np.max(dd) if len(dd) > 0 else 0.0
    
    return {
        'trades': tot_trades,
        'win_rate': round(win_rate, 1),
        'profit_factor': round(pf, 2),
        'total_r': round(tot_r, 1),
        'max_dd_r': round(max_dd, 1),
        'wins': int(wins),
        'losses': int(losses),
        'avg_win_r': round(np.mean(trades[trades > 0]), 2) if wins > 0 else 0.0
    }

print("=== FINAL STRATEGY VERIFICATION: ORDER BLOCK + FIBONACCI RETRACEMENT & EXTENSION ===")
for target in ['fib_272', 'fib_618', 'fixed_1.5']:
    tot_t, tot_w, tot_l, tot_r, gross_p, gross_l = 0, 0, 0, 0.0, 0.0, 0.0
    for p in pairs:
        r = test_exact_ob_fib_model(data_dict[p], exit_target=target)
        tot_t += r['trades']
        tot_w += r['wins']
        tot_l += r['losses']
        tot_r += r['total_r']
        if r['wins'] > 0:
            gross_p += r['wins'] * r['avg_win_r']
        gross_l += r['losses'] * 1.0
    pf = round(gross_p / max(1.0, gross_l), 2)
    wr = round(tot_w / max(1, tot_t) * 100, 1)
    exp = round(tot_r / max(1, tot_t), 3)
    print(f"Target={target:9s}: Trades={tot_t} | WinRate={wr}% | PF={pf} | Net={tot_r:+.1f}R | Exp={exp:+.3f}R")
