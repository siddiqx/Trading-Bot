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
    
    # Volume SMA
    if 'tick_volume' in df.columns:
        df['vol_ma'] = df['tick_volume'].rolling(20).mean()
        df['vol_surge'] = df['tick_volume'] > df['vol_ma']
    else:
        df['vol_surge'] = True
        
    # Donchian Channels
    for lb in [20, 36, 48, 72]:
        df[f'dh_{lb}'] = df['high'].shift(1).rolling(lb).max()
        df[f'dl_{lb}'] = df['low'].shift(1).rolling(lb).min()
        
    # Session
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
        d1['d1_ema200'] = d1['close'].ewm(span=200, adjust=False).mean()
        
        df['date'] = df['datetime'].dt.date
        d1_shifted = d1[['date', 'd1_ema50', 'd1_ema200', 'close']].copy()
        d1_shifted['d1_close_prev'] = d1_shifted['close'].shift(1)
        d1_shifted['d1_ema50_prev'] = d1_shifted['d1_ema50'].shift(1)
        d1_shifted['d1_ema200_prev'] = d1_shifted['d1_ema200'].shift(1)
        
        df = pd.merge(df, d1_shifted[['date', 'd1_close_prev', 'd1_ema50_prev', 'd1_ema200_prev']], on='date', how='left')
        df['d1_bull'] = df['d1_close_prev'] > df['d1_ema50_prev']
        df['d1_bear'] = df['d1_close_prev'] < df['d1_ema50_prev']
    else:
        df['d1_bull'] = True
        df['d1_bear'] = True
        
    df.bfill(inplace=True)
    df.ffill(inplace=True)
    return df

def simulate_advanced(df, lookback=48, rr=1.5, entry_type='market', 
                      use_vol=False, use_rsi=False, trail_stop=False, sl_mult=1.5):
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
    vol_surge = df['vol_surge'].values
    sess = df['session_ok'].values
    d1_bull = df['d1_bull'].values
    d1_bear = df['d1_bear'].values
    dh = df[f'dh_{lookback}'].values
    dl = df[f'dl_{lookback}'].values
    
    n = len(c)
    trades = []
    in_pos = False
    pending = False
    pos_type = 0
    pending_type = 0
    limit_price = 0.0
    pending_expire = 0
    entry_p = 0.0
    sl_p = 0.0
    tp_p = 0.0
    risk = 0.0
    
    for i in range(100, n):
        # 1. Manage active position
        if in_pos:
            hi = h[i]
            li = l[i]
            if pos_type == 1:
                # Trailing stop option: trail below EMA20 or 1.5 ATR
                if trail_stop:
                    new_sl = c[i] - (sl_mult * atr[i])
                    if new_sl > sl_p:
                        sl_p = new_sl
                if li <= sl_p:
                    # Stopped out
                    pnl_r = (sl_p - entry_p) / risk
                    trades.append(pnl_r)
                    in_pos = False
                elif hi >= tp_p:
                    # Hit TP
                    trades.append(rr)
                    in_pos = False
            elif pos_type == -1:
                if trail_stop:
                    new_sl = c[i] + (sl_mult * atr[i])
                    if new_sl < sl_p:
                        sl_p = new_sl
                if hi >= sl_p:
                    pnl_r = (entry_p - sl_p) / risk
                    trades.append(pnl_r)
                    in_pos = False
                elif li <= tp_p:
                    trades.append(rr)
                    in_pos = False
            continue
            
        # 2. Check pending limit orders (Retest / Intraday Entry)
        if pending:
            if i > pending_expire:
                pending = False # Expired
            else:
                if pending_type == 1: # Long limit
                    if l[i] <= limit_price: # Filled!
                        in_pos = True
                        pending = False
                        pos_type = 1
                        entry_p = limit_price
                        sl_p = pending_sl
                        tp_p = entry_p + ((entry_p - sl_p) * rr)
                        risk = entry_p - sl_p
                        continue
                elif pending_type == -1: # Short limit
                    if h[i] >= limit_price: # Filled!
                        in_pos = True
                        pending = False
                        pos_type = -1
                        entry_p = limit_price
                        sl_p = pending_sl
                        tp_p = entry_p - ((sl_p - entry_p) * rr)
                        risk = sl_p - entry_p
                        continue
                        
        # 3. Check for new breakout signal on Candle #1
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
            
        # Core Filters: Session + D1 + 1H Trend + Rising ADX
        if not sess[i]:
            continue
        if long_bo and not (d1_bull[i] and curr_c > ema200[i] and ema20[i] > ema50[i]):
            continue
        if short_bo and not (d1_bear[i] and curr_c < ema200[i] and ema20[i] < ema50[i]):
            continue
        if adx[i] < 20 or adx_slope[i] <= 0:
            continue
            
        # Optional filters
        if use_vol and not vol_surge[i]:
            continue
        if use_rsi:
            if long_bo and (rsi[i] < 55 or rsi[i] > 75):
                continue
            if short_bo and (rsi[i] > 45 or rsi[i] < 25):
                continue
                
        # Determine Entry: 'market' vs 'retest_50' (midpoint between breakout level and close)
        if entry_type == 'market':
            in_pos = True
            pos_type = 1 if long_bo else -1
            entry_p = curr_c
            risk = sl_mult * atr[i]
            sl_p = entry_p - risk if long_bo else entry_p + risk
            tp_p = entry_p + (risk * rr) if long_bo else entry_p - (risk * rr)
        elif entry_type == 'retest_50':
            # Place limit order at 50% retracement of breakout candle
            pending = True
            pending_type = 1 if long_bo else -1
            bo_level = curr_dh if long_bo else curr_dl
            limit_price = (curr_c + bo_level) / 2.0
            pending_sl = limit_price - (sl_mult * atr[i]) if long_bo else limit_price + (sl_mult * atr[i])
            pending_expire = i + 4 # valid for next 4 hours
            
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

def test_config(name, **kwargs):
    results = {}
    tot_trades = 0
    tot_wins = 0
    tot_losses = 0
    tot_r = 0.0
    gross_p = 0.0
    gross_l = 0.0
    
    for p in pairs:
        res = simulate_advanced(data_dict[p], **kwargs)
        results[p] = res
        tot_trades += res['trades']
        tot_wins += res.get('wins', 0)
        tot_losses += res.get('losses', 0)
        tot_r += res.get('total_r', 0)
        
    overall_pf = round(sum(results[p]['wins'] * kwargs.get('rr', 1.5) for p in pairs) / max(1, sum(results[p]['losses'] for p in pairs)), 2)
    overall_wr = round(tot_wins / tot_trades * 100, 1) if tot_trades > 0 else 0.0
    overall_exp = round(tot_r / tot_trades, 3) if tot_trades > 0 else 0.0
    
    print(f"=== {name} ===")
    print(f"Overall: Trades={tot_trades} | WinRate={overall_wr}% | PF={overall_pf} | Total R={tot_r:+.1f}R | Exp={overall_exp:+.3f}R")
    for p in pairs:
        r = results[p]
        print(f"  {p:6s}: Trades={r['trades']:3d} | WR={r['win_rate']:4.1f}% | PF={r['profit_factor']:4.2f} | Net={r['total_r']:+6.1f}R | MaxDD={r['max_dd_r']:4.1f}R")
    print()

# Test various R:R targets and mechanisms
test_config("A. 48h Lookback, RR=1.5, Market Entry", lookback=48, rr=1.5, entry_type='market')
test_config("B. 48h Lookback, RR=1.2, Market Entry", lookback=48, rr=1.2, entry_type='market')
test_config("C. 48h Lookback, RR=2.0, Market Entry", lookback=48, rr=2.0, entry_type='market')
test_config("D. 48h Lookback, RR=1.5, Retest 50% Limit Entry", lookback=48, rr=1.5, entry_type='retest_50')
test_config("E. 48h Lookback, RR=2.0, Retest 50% Limit Entry", lookback=48, rr=2.0, entry_type='retest_50')
test_config("F. 72h Lookback (3 Days), RR=1.5, Market Entry", lookback=72, rr=1.5, entry_type='market')
test_config("G. 72h Lookback (3 Days), RR=2.0, Market Entry", lookback=72, rr=2.0, entry_type='market')
test_config("H. 48h Lookback, RR=1.5, Volume Surge Filter", lookback=48, rr=1.5, entry_type='market', use_vol=True)
test_config("I. 48h Lookback, RR=1.5, RSI Filter (55-75 bull / 25-45 bear)", lookback=48, rr=1.5, entry_type='market', use_rsi=True)
test_config("J. 72h Lookback, RR=1.5, Retest 50% Limit Entry", lookback=72, rr=1.5, entry_type='retest_50')
