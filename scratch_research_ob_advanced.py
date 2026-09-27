import pickle
import pandas as pd
import numpy as np

# Load dataset
with open('archives/data_cache.pkl', 'rb') as f:
    cache = pickle.load(f)[1]

from scratch_research_ob_fib import prepare_data, pairs

data_dict = {}
for p in pairs:
    data_dict[p] = prepare_data(cache[p]['H1'], cache[p]['D1'])

def simulate_ob_confluence(df, entry_mode='ob_retest', exit_mode='fib_ext', rr_fixed=2.0, max_bars=8):
    """
    entry_mode:
      - 'ob_retest': enters at OB High (for Long) or OB Low (for Short)
      - 'fib_50': enters at 50% Fibonacci Retracement of impulse
      - 'fib_618': enters at 61.8% Fibonacci Retracement
      - 'confluence_ote': enters at max(OB_High, Fib 50%) for Long, min(OB_Low, Fib 50%) for Short
      
    exit_mode:
      - 'fixed_rr': fixed R:R multiple of risk
      - 'fib_ext_272': Take profit at -0.272 Fibonacci Extension of impulse swing
      - 'fib_ext_618': Take profit at -0.618 Fibonacci Extension of impulse swing
    """
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
    pending_type = 0
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
        # 1. Manage Active Position
        if in_pos:
            hi = h[i]
            li = l[i]
            if pos_type == 1: # Long
                if li <= sl_p:
                    trades.append(-1.0)
                    in_pos = False
                elif hi >= tp_p:
                    trades.append(actual_rr)
                    in_pos = False
            elif pos_type == -1: # Short
                if hi >= sl_p:
                    trades.append(-1.0)
                    in_pos = False
                elif li <= tp_p:
                    trades.append(actual_rr)
                    in_pos = False
            continue
            
        # 2. Check Pending Limit Order
        if pending:
            if i > pending_expire:
                pending = False
            else:
                if pending_type == 1:
                    if l[i] <= limit_price: # Fill!
                        in_pos = True
                        pending = False
                        pos_type = 1
                        entry_p = limit_price
                        sl_p = pending_sl
                        tp_p = pending_tp
                        risk = entry_p - sl_p
                        actual_rr = (tp_p - entry_p) / risk if risk > 0 else 1.5
                        continue
                elif pending_type == -1:
                    if h[i] >= limit_price: # Fill!
                        in_pos = True
                        pending = False
                        pos_type = -1
                        entry_p = limit_price
                        sl_p = pending_sl
                        tp_p = pending_tp
                        risk = sl_p - entry_p
                        actual_rr = (entry_p - tp_p) / risk if risk > 0 else 1.5
                        continue
                        
        # 3. Check for 1H Anchor Breakout on Candle #1
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
            
        # Filters: Session + D1 + 1H EMA + ADX Rising
        if not sess[i]:
            continue
        if long_bo and not (d1_bull[i] and curr_c > ema200[i] and ema20[i] > ema50[i]):
            continue
        if short_bo and not (d1_bear[i] and curr_c < ema200[i] and ema20[i] < ema50[i]):
            continue
        if adx[i] < 20 or adx_slope[i] <= 0:
            continue
        # RSI Sweet Spot
        if long_bo and (rsi[i] < 55 or rsi[i] > 75):
            continue
        if short_bo and (rsi[i] > 45 or rsi[i] < 25):
            continue
            
        # 4. ORDER BLOCK IDENTIFICATION & FIBONACCI
        if long_bo:
            # Find the Origin Order Block (last bearish candle before the displacement)
            ob_idx = None
            for look in range(1, 6):
                idx = i - look
                if c[idx] < o[idx]:
                    ob_idx = idx
                    break
            if ob_idx is None:
                ob_idx = i - 1
                
            ob_high = h[ob_idx]
            ob_low = l[ob_idx]
            ob_mid = (ob_high + ob_low) / 2.0
            
            swing_low = ob_low
            swing_high = h[i]
            swing_rng = swing_high - swing_low
            if swing_rng <= 0:
                continue
                
            fib_50 = swing_high - (0.50 * swing_rng)
            fib_618 = swing_high - (0.618 * swing_rng)
            fib_705 = swing_high - (0.705 * swing_rng)
            
            # Determine Entry Level
            if entry_mode == 'ob_retest':
                entry_level = ob_high
            elif entry_mode == 'fib_50':
                entry_level = fib_50
            elif entry_mode == 'fib_618':
                entry_level = fib_618
            elif entry_mode == 'confluence_ote':
                # Confluence: if OB_high is above Fib 50, use Fib 50. If OB_high is within discount, use OB_high
                entry_level = min(ob_high, fib_50)
            elif entry_mode == 'ob_mid':
                entry_level = ob_mid
            else:
                entry_level = fib_50
                
            # Structural Invalidation SL: Order Block Low with 0.15*ATR buffer
            sl_level = ob_low - (0.15 * atr[i])
            risk_dist = entry_level - sl_level
            if risk_dist <= 0:
                continue
                
            # Determine Take Profit Exit
            if exit_mode == 'fib_ext_272':
                tp_level = swing_high + (0.272 * swing_rng)
            elif exit_mode == 'fib_ext_618':
                tp_level = swing_high + (0.618 * swing_rng)
            else: # fixed_rr
                tp_level = entry_level + (risk_dist * rr_fixed)
                
            # Check minimum R:R of at least 1.2
            if (tp_level - entry_level) / risk_dist < 1.2:
                tp_level = entry_level + (risk_dist * 1.5)
                
            pending = True
            pending_type = 1
            limit_price = entry_level
            pending_sl = sl_level
            pending_tp = tp_level
            pending_expire = i + max_bars
            
        elif short_bo:
            # Origin Order Block for Short (last bullish candle before the breakdown)
            ob_idx = None
            for look in range(1, 6):
                idx = i - look
                if c[idx] > o[idx]:
                    ob_idx = idx
                    break
            if ob_idx is None:
                ob_idx = i - 1
                
            ob_high = h[ob_idx]
            ob_low = l[ob_idx]
            ob_mid = (ob_high + ob_low) / 2.0
            
            swing_high = ob_high
            swing_low = l[i]
            swing_rng = swing_high - swing_low
            if swing_rng <= 0:
                continue
                
            fib_50 = swing_low + (0.50 * swing_rng)
            fib_618 = swing_low + (0.618 * swing_rng)
            fib_705 = swing_low + (0.705 * swing_rng)
            
            if entry_mode == 'ob_retest':
                entry_level = ob_low
            elif entry_mode == 'fib_50':
                entry_level = fib_50
            elif entry_mode == 'fib_618':
                entry_level = fib_618
            elif entry_mode == 'confluence_ote':
                entry_level = max(ob_low, fib_50)
            elif entry_mode == 'ob_mid':
                entry_level = ob_mid
            else:
                entry_level = fib_50
                
            sl_level = ob_high + (0.15 * atr[i])
            risk_dist = sl_level - entry_level
            if risk_dist <= 0:
                continue
                
            if exit_mode == 'fib_ext_272':
                tp_level = swing_low - (0.272 * swing_rng)
            elif exit_mode == 'fib_ext_618':
                tp_level = swing_low - (0.618 * swing_rng)
            else:
                tp_level = entry_level - (risk_dist * rr_fixed)
                
            if (entry_level - tp_level) / risk_dist < 1.2:
                tp_level = entry_level - (risk_dist * 1.5)
                
            pending = True
            pending_type = -1
            limit_price = entry_level
            pending_sl = sl_level
            pending_tp = tp_level
            pending_expire = i + max_bars
            
    if not trades:
        return {'trades': 0, 'win_rate': 0.0, 'profit_factor': 0.0, 'total_r': 0.0, 'max_dd_r': 0.0, 'expectancy_r': 0.0, 'wins': 0, 'losses': 0}
        
    trades = np.array(trades)
    wins = np.sum(trades > 0)
    losses = np.sum(trades <= 0)
    tot_trades = len(trades)
    win_rate = (wins / tot_trades) * 100.0
    gross_p = np.sum(trades[trades > 0])
    gross_l = np.abs(np.sum(trades[trades <= 0]))
    pf = (gross_p / gross_l) if gross_l > 0 else 99.0
    tot_r = np.sum(trades)
    exp_r = np.mean(trades)
    
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
        'expectancy_r': round(exp_r, 3),
        'wins': int(wins),
        'losses': int(losses),
        'avg_win_r': round(np.mean(trades[trades > 0]), 2) if wins > 0 else 0.0
    }

def run_suite(title, **kwargs):
    results = {}
    tot_t, tot_w, tot_l, tot_r, gross_p, gross_l = 0, 0, 0, 0.0, 0.0, 0.0
    for p in pairs:
        r = simulate_ob_confluence(data_dict[p], **kwargs)
        results[p] = r
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
    
    print(f"=== {title} ===")
    print(f"Overall: Trades={tot_t} | WinRate={wr}% | PF={pf} | Total R={tot_r:+.1f}R | Exp={exp:+.3f}R")
    for p in pairs:
        r = results[p]
        print(f"  {p:6s}: Trades={r['trades']:2d} | WR={r['win_rate']:4.1f}% | PF={r['profit_factor']:4.2f} | Net={r['total_r']:+5.1f}R | MaxDD={r['max_dd_r']:3.1f}R | AvgWin={r.get('avg_win_r', 0)}R")
    print()

run_suite("A. OB Retest Entry (OB High/Low) + Fixed 1.5 RR", entry_mode='ob_retest', exit_mode='fixed_rr', rr_fixed=1.5)
run_suite("B. OB Retest Entry (OB High/Low) + Fixed 2.0 RR", entry_mode='ob_retest', exit_mode='fixed_rr', rr_fixed=2.0)
run_suite("C. OB Retest Entry (OB High/Low) + Fib -0.272 Extension Exit", entry_mode='ob_retest', exit_mode='fib_ext_272')
run_suite("D. OB Retest Entry (OB High/Low) + Fib -0.618 Extension Exit", entry_mode='ob_retest', exit_mode='fib_ext_618')
run_suite("E. Confluence OTE [min(OB_High, Fib 50%)] + Fib -0.272 Extension Exit", entry_mode='confluence_ote', exit_mode='fib_ext_272')
run_suite("F. Confluence OTE [min(OB_High, Fib 50%)] + Fixed 2.0 RR", entry_mode='confluence_ote', exit_mode='fixed_rr', rr_fixed=2.0)
run_suite("G. Confluence OTE [min(OB_High, Fib 50%)] + Fixed 1.5 RR", entry_mode='confluence_ote', exit_mode='fixed_rr', rr_fixed=1.5)
run_suite("H. Fib 61.8% Golden Zone Entry + Fib -0.272 Extension Exit", entry_mode='fib_618', exit_mode='fib_ext_272')
