import pickle
import pandas as pd
import numpy as np

# Load dataset
with open('archives/data_cache.pkl', 'rb') as f:
    cache = pickle.load(f)[1]

def prepare_data(df, d1_df=None):
    df = df.copy()
    if 'time' in df.columns:
        df['datetime'] = pd.to_datetime(df['time'], unit='s')
    else:
        df['datetime'] = pd.to_datetime(df.index)
        
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # ATR
    hl = df['high'] - df['low']
    hc = (df['high'] - df['close'].shift()).abs()
    lc = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df['atr14'] = tr.rolling(14).mean()
    
    # ADX and DMI
    up = df['high'] - df['high'].shift()
    down = df['low'].shift() - df['low']
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr14 = tr.rolling(14).sum()
    plus_di14 = 100 * (pd.Series(plus_dm, index=df.index).rolling(14).sum() / tr14)
    minus_di14 = 100 * (pd.Series(minus_dm, index=df.index).rolling(14).sum() / tr14)
    dx = 100 * (plus_di14 - minus_di14).abs() / (plus_di14 + minus_di14)
    df['adx14'] = dx.rolling(14).mean()
    df['adx_slope'] = df['adx14'] - df['adx14'].shift(1)
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-6)
    df['rsi14'] = 100 - (100 / (1 + rs))
    
    # Donchian Channels (48 bars = 2 days)
    df['dh_48'] = df['high'].shift(1).rolling(48).max()
    df['dl_48'] = df['low'].shift(1).rolling(48).min()
    
    # Session (London + NY)
    df['hour'] = df['datetime'].dt.hour
    df['session_ok'] = (df['hour'] >= 7) & (df['hour'] <= 16)
    
    # D1 Macro Trend
    if d1_df is not None:
        d1 = d1_df.copy()
        if 'time' in d1.columns:
            d1['date'] = pd.to_datetime(d1['time'], unit='s').dt.date
        else:
            d1['date'] = pd.to_datetime(d1.index).dt.date
        d1['d1_ema50'] = d1['close'].ewm(span=50, adjust=False).mean()
        
        df['date'] = df['datetime'].dt.date
        d1_shifted = d1[['date', 'd1_ema50', 'close']].copy()
        d1_shifted['d1_close_prev'] = d1_shifted['close'].shift(1)
        d1_shifted['d1_ema50_prev'] = d1_shifted['d1_ema50'].shift(1)
        
        df = pd.merge(df, d1_shifted[['date', 'd1_close_prev', 'd1_ema50_prev']], on='date', how='left')
        df['d1_bull'] = df['d1_close_prev'] > df['d1_ema50_prev']
        df['d1_bear'] = df['d1_close_prev'] < df['d1_ema50_prev']
    else:
        df['d1_bull'] = True
        df['d1_bear'] = True
        
    df.bfill(inplace=True)
    df.ffill(inplace=True)
    return df

def simulate_ob_fib(df, rr=2.0, max_pullback_bars=6, fib_level=0.618, use_ob_mean=False):
    """
    Simulates Order Block + Fibonacci Retracement Strategy:
    1. 1H Breakout Anchor occurs.
    2. Identify the Origin Order Block (OB):
       - For Long: The last bearish candle (close < open) prior to the breakout displacement.
       - For Short: The last bullish candle (close > open) prior to the breakdown displacement.
    3. Measure the Impulse Swing:
       - For Long: Swing Low (low of the OB) to Impulse High (high of breakout candle).
       - For Short: Swing High (high of the OB) to Impulse Low (low of breakout candle).
    4. Calculate Fibonacci Retracement Levels:
       - Fib 50% = Equilibrium
       - Fib 61.8% = Golden Ratio
       - Fib 70.5% = ICT OTE Sweet Spot
       - Fib 78.6% = Deep Discount
       - Fib OTE Range = [Fib 61.8%, Fib 78.6%]
    5. Confluence Entry:
       - Entry limit order set at the confluence of the Order Block and Fibonacci level.
       - If use_ob_mean: Order Block Mean Threshold (high+low)/2.
       - Otherwise: Fib 61.8% or 70.5%.
    6. Structural Invalidation (Exit):
       - Stop Loss placed just below the Order Block Low (for Long) or above OB High (for Short) with 0.15*ATR buffer.
       - Take Profit placed at Fibonacci Extension (-0.272 ext or fixed RR on tight OB stop).
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
    
    for i in range(100, n):
        # 1. Manage Active Position
        if in_pos:
            hi = h[i]
            li = l[i]
            if pos_type == 1: # Long
                if li <= sl_p:
                    # Stopped out
                    trades.append(-1.0)
                    in_pos = False
                elif hi >= tp_p:
                    # Hit TP
                    trades.append(rr)
                    in_pos = False
            elif pos_type == -1: # Short
                if hi >= sl_p:
                    trades.append(-1.0)
                    in_pos = False
                elif li <= tp_p:
                    trades.append(rr)
                    in_pos = False
            continue
            
        # 2. Check Pending Limit Order (Waiting for Retest into OB / Fib OTE Zone)
        if pending:
            if i > pending_expire:
                pending = False # Pullback expired without filling
            else:
                if pending_type == 1: # Long Limit
                    if l[i] <= limit_price: # Filled inside OB / Fib zone!
                        in_pos = True
                        pending = False
                        pos_type = 1
                        entry_p = limit_price
                        sl_p = pending_sl
                        tp_p = pending_tp
                        risk = entry_p - sl_p
                        continue
                elif pending_type == -1: # Short Limit
                    if h[i] >= limit_price: # Filled inside OB / Fib zone!
                        in_pos = True
                        pending = False
                        pos_type = -1
                        entry_p = limit_price
                        sl_p = pending_sl
                        tp_p = pending_tp
                        risk = sl_p - entry_p
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
            
        # Filters: Session + D1 Trend + 1H EMA Align + ADX Rising + RSI Sweet-Spot
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
            
        # 4. ORDER BLOCK IDENTIFICATION & FIBONACCI RETRACEMENT
        if long_bo:
            # Look backwards from breakout bar to find the Origin Order Block (last bearish candle)
            ob_idx = None
            for look in range(1, 6):
                idx = i - look
                if c[idx] < o[idx]: # Bearish candle
                    ob_idx = idx
                    break
            if ob_idx is None:
                ob_idx = i - 1
                
            ob_high = h[ob_idx]
            ob_low = l[ob_idx]
            ob_mean = (ob_high + ob_low) / 2.0
            
            # Swing Range for Fib: Swing Low (OB low) to Breakout High
            swing_low = ob_low
            swing_high = h[i]
            swing_rng = swing_high - swing_low
            if swing_rng <= 0:
                continue
                
            # Fib Levels:
            # 61.8% retracement from swing_high down towards swing_low:
            # Fib 61.8% = swing_high - 0.618 * swing_rng = swing_low + 0.382 * swing_rng
            # Or Fib 50% = swing_low + 0.50 * swing_rng
            fib_retrace_price = swing_high - (fib_level * swing_rng)
            
            # Confluence Entry Price:
            if use_ob_mean:
                # Target the Order Block Mean Threshold if it's within the discount area
                entry_level = min(ob_mean, swing_high - (0.50 * swing_rng))
            else:
                # Target the Fibonacci Retracement level (e.g. 61.8% or 70.5%)
                entry_level = fib_retrace_price
                
            # Structural Invalidation (SL):
            # Just below the Order Block Low with a small ATR buffer
            sl_level = ob_low - (0.2 * atr[i])
            risk_dist = entry_level - sl_level
            
            if risk_dist <= 0:
                continue
                
            tp_level = entry_level + (risk_dist * rr)
            
            # Set pending limit order
            pending = True
            pending_type = 1
            limit_price = entry_level
            pending_sl = sl_level
            pending_tp = tp_level
            pending_expire = i + max_pullback_bars # e.g. valid for 6 hours
            
        elif short_bo:
            # Look backwards from breakdown bar to find the Origin Order Block (last bullish candle)
            ob_idx = None
            for look in range(1, 6):
                idx = i - look
                if c[idx] > o[idx]: # Bullish candle
                    ob_idx = idx
                    break
            if ob_idx is None:
                ob_idx = i - 1
                
            ob_high = h[ob_idx]
            ob_low = l[ob_idx]
            ob_mean = (ob_high + ob_low) / 2.0
            
            swing_high = ob_high
            swing_low = l[i]
            swing_rng = swing_high - swing_low
            if swing_rng <= 0:
                continue
                
            fib_retrace_price = swing_low + (fib_level * swing_rng)
            
            if use_ob_mean:
                entry_level = max(ob_mean, swing_low + (0.50 * swing_rng))
            else:
                entry_level = fib_retrace_price
                
            sl_level = ob_high + (0.2 * atr[i])
            risk_dist = sl_level - entry_level
            
            if risk_dist <= 0:
                continue
                
            tp_level = entry_level - (risk_dist * rr)
            
            pending = True
            pending_type = -1
            limit_price = entry_level
            pending_sl = sl_level
            pending_tp = tp_level
            pending_expire = i + max_pullback_bars
            
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
        'losses': int(losses)
    }

pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF']
data_dict = {}
for p in pairs:
    data_dict[p] = prepare_data(cache[p]['H1'], cache[p]['D1'])

def test_ob_strategy(name, **kwargs):
    results = {}
    tot_trades = 0
    tot_wins = 0
    tot_losses = 0
    tot_r = 0.0
    
    for p in pairs:
        res = simulate_ob_fib(data_dict[p], **kwargs)
        results[p] = res
        tot_trades += res['trades']
        tot_wins += res.get('wins', 0)
        tot_losses += res.get('losses', 0)
        tot_r += res.get('total_r', 0)
        
    rr = kwargs.get('rr', 2.0)
    overall_pf = round((tot_wins * rr) / max(1, tot_losses), 2)
    overall_wr = round(tot_wins / tot_trades * 100, 1) if tot_trades > 0 else 0.0
    overall_exp = round(tot_r / tot_trades, 3) if tot_trades > 0 else 0.0
    
    print(f"=== {name} ===")
    print(f"Overall: Trades={tot_trades} | WinRate={overall_wr}% | PF={overall_pf} | Total R={tot_r:+.1f}R | Exp={overall_exp:+.3f}R")
    for p in pairs:
        r = results[p]
        print(f"  {p:6s}: Trades={r['trades']:3d} | WR={r['win_rate']:4.1f}% | PF={r['profit_factor']:4.2f} | Net={r['total_r']:+6.1f}R | MaxDD={r['max_dd_r']:4.1f}R")
    print()

# Test various Fibonacci retracement depths & Order Block levels
test_ob_strategy("1. Fib 50% (Equilibrium Retracement), RR=1.5", fib_level=0.50, rr=1.5)
test_ob_strategy("2. Fib 50% (Equilibrium Retracement), RR=2.0", fib_level=0.50, rr=2.0)
test_ob_strategy("3. Fib 61.8% (Golden Zone Retracement), RR=1.5", fib_level=0.618, rr=1.5)
test_ob_strategy("4. Fib 61.8% (Golden Zone Retracement), RR=2.0", fib_level=0.618, rr=2.0)
test_ob_strategy("5. Fib 70.5% (ICT OTE Sweet Spot), RR=2.0", fib_level=0.705, rr=2.0)
test_ob_strategy("6. Fib 70.5% (ICT OTE Sweet Spot), RR=2.5", fib_level=0.705, rr=2.5)
test_ob_strategy("7. Order Block Mean Threshold (MT 50% of OB), RR=2.0", use_ob_mean=True, rr=2.0)
test_ob_strategy("8. Order Block Mean Threshold (MT 50% of OB), RR=2.5", use_ob_mean=True, rr=2.5)
