import pickle
import pandas as pd
import numpy as np

# Load dataset
with open('archives/data_cache.pkl', 'rb') as f:
    cache = pickle.load(f)[1]

def calculate_indicators(df, d1_df=None):
    df = df.copy()
    if 'time' in df.columns:
        df['datetime'] = pd.to_datetime(df['time'], unit='s')
    else:
        df['datetime'] = pd.to_datetime(df.index)
    
    # 1H EMAs
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
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
    df['plus_di'] = plus_di14
    df['minus_di'] = minus_di14
    df['adx_slope'] = df['adx14'] - df['adx14'].shift(1)
    
    # Bollinger Bands (20, 2)
    df['bb_mid'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']
    
    # Keltner Channels (20, 1.5 ATR)
    df['kc_upper'] = df['bb_mid'] + 1.5 * df['atr14']
    df['kc_lower'] = df['bb_mid'] - 1.5 * df['atr14']
    
    # Squeeze: BB inside KC
    df['in_squeeze'] = (df['bb_lower'] > df['kc_lower']) & (df['bb_upper'] < df['kc_upper'])
    df['recent_squeeze'] = df['in_squeeze'].rolling(6).max().fillna(0).astype(bool)
    
    # Candle body ratio
    candle_range = (df['high'] - df['low']).replace(0, 1e-6)
    candle_body = (df['close'] - df['open']).abs()
    df['body_ratio'] = candle_body / candle_range
    
    # Hour of day (UTC)
    df['hour'] = df['datetime'].dt.hour
    df['london_ny_session'] = (df['hour'] >= 7) & (df['hour'] <= 16)
    
    # Donchian Channels for multiple lookbacks: 20, 36, 48, 72
    for lb in [20, 36, 48, 72]:
        df[f'donchian_high_{lb}'] = df['high'].shift(1).rolling(lb).max()
        df[f'donchian_low_{lb}'] = df['low'].shift(1).rolling(lb).min()
        
    # Daily Macro alignment
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
        df['d1_bullish'] = df['d1_close_prev'] > df['d1_ema50_prev']
        df['d1_bearish'] = df['d1_close_prev'] < df['d1_ema50_prev']
    else:
        df['d1_bullish'] = True
        df['d1_bearish'] = True
        
    df.bfill(inplace=True)
    df.ffill(inplace=True)
    return df

def simulate_fast(df, lookback=20, use_session=False, use_d1=False, use_adx_rising=False, 
                  use_squeeze=False, use_body_filter=False, be_at_1r=False, rr=2.0):
    # Extract numpy arrays for blazing speed
    c = df['close'].values
    h = df['high'].values
    l = df['low'].values
    ema20 = df['ema20'].values
    ema50 = df['ema50'].values
    ema200 = df['ema200'].values
    atr = df['atr14'].values
    adx = df['adx14'].values
    adx_slope = df['adx_slope'].values
    sess = df['london_ny_session'].values
    d1_bull = df['d1_bullish'].values
    d1_bear = df['d1_bearish'].values
    squeeze = df['recent_squeeze'].values
    body = df['body_ratio'].values
    d_high = df[f'donchian_high_{lookback}'].values
    d_low = df[f'donchian_low_{lookback}'].values
    
    n = len(c)
    trades = []
    in_pos = False
    pos_type = 0
    entry_p = 0.0
    sl_p = 0.0
    tp_p = 0.0
    risk = 0.0
    be_active = False
    
    for i in range(100, n):
        # Position check
        if in_pos:
            hi = h[i]
            li = l[i]
            if pos_type == 1: # Long
                if be_at_1r and not be_active and hi >= entry_p + risk:
                    sl_p = entry_p
                    be_active = True
                if li <= sl_p:
                    trades.append(0.0 if be_active and sl_p == entry_p else -1.0)
                    in_pos = False
                elif hi >= tp_p:
                    trades.append(rr)
                    in_pos = False
            elif pos_type == -1: # Short
                if be_at_1r and not be_active and li <= entry_p - risk:
                    sl_p = entry_p
                    be_active = True
                if hi >= sl_p:
                    trades.append(0.0 if be_active and sl_p == entry_p else -1.0)
                    in_pos = False
                elif li <= tp_p:
                    trades.append(rr)
                    in_pos = False
            continue
            
        # Entry check
        # Breakout Candle #1: previous close was inside or at boundary, current close strictly breaks out
        prev_c = c[i-1]
        prev_dh = d_high[i-1]
        prev_dl = d_low[i-1]
        curr_c = c[i]
        curr_dh = d_high[i]
        curr_dl = d_low[i]
        
        long_bo = (prev_c <= prev_dh) and (curr_c > curr_dh)
        short_bo = (prev_c >= prev_dl) and (curr_c < curr_dl)
        
        if not (long_bo or short_bo):
            continue
            
        # 1H Trend
        long_tr = (curr_c > ema200[i]) and (ema20[i] > ema50[i])
        short_tr = (curr_c < ema200[i]) and (ema20[i] < ema50[i])
        
        # Base ADX
        if adx[i] < 20:
            continue
            
        # Filters
        if use_session and not sess[i]:
            continue
        if use_d1:
            if long_bo and not d1_bull[i]:
                continue
            if short_bo and not d1_bear[i]:
                continue
        if use_adx_rising and adx_slope[i] <= 0:
            continue
        if use_squeeze and not squeeze[i]:
            continue
        if use_body_filter and body[i] < 0.50:
            continue
            
        if long_bo and long_tr:
            in_pos = True
            pos_type = 1
            entry_p = curr_c
            risk = 1.5 * atr[i]
            sl_p = entry_p - risk
            tp_p = entry_p + (risk * rr)
            be_active = False
        elif short_bo and short_tr:
            in_pos = True
            pos_type = -1
            entry_p = curr_c
            risk = 1.5 * atr[i]
            sl_p = entry_p + risk
            tp_p = entry_p - (risk * rr)
            be_active = False
            
    if not trades:
        return {'trades': 0, 'win_rate': 0.0, 'profit_factor': 0.0, 'total_r': 0.0, 'max_dd_r': 0.0, 'expectancy_r': 0.0, 'wins': 0, 'losses': 0, 'be': 0}
        
    trades = np.array(trades)
    wins = np.sum(trades > 0)
    losses = np.sum(trades < 0)
    bes = np.sum(trades == 0)
    tot_trades = len(trades)
    win_rate = (wins / tot_trades) * 100.0
    gross_p = np.sum(trades[trades > 0])
    gross_l = np.abs(np.sum(trades[trades < 0]))
    pf = (gross_p / gross_l) if gross_l > 0 else 99.0
    tot_r = np.sum(trades)
    exp_r = np.mean(trades)
    
    # DD
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
        'breakevens': int(bes)
    }

pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF']
data_dict = {}
for p in pairs:
    h1 = cache[p]['H1']
    d1 = cache[p]['D1']
    data_dict[p] = calculate_indicators(h1, d1)

def run_experiment_across_all(name, **kwargs):
    results = {}
    tot_trades = 0
    tot_wins = 0
    tot_losses = 0
    tot_be = 0
    tot_r = 0.0
    gross_p = 0.0
    gross_l = 0.0
    
    for p in pairs:
        res = simulate_fast(data_dict[p], **kwargs)
        results[p] = res
        tot_trades += res['trades']
        tot_wins += res.get('wins', 0)
        tot_losses += res.get('losses', 0)
        tot_be += res.get('breakevens', 0)
        tot_r += res.get('total_r', 0)
        gross_p += res.get('wins', 0) * kwargs.get('rr', 2.0)
        gross_l += res.get('losses', 0) * 1.0
        
    overall_pf = round(gross_p / gross_l, 2) if gross_l > 0 else 99.0
    overall_wr = round(tot_wins / tot_trades * 100, 1) if tot_trades > 0 else 0.0
    overall_exp = round(tot_r / tot_trades, 3) if tot_trades > 0 else 0.0
    
    print(f"=== {name} ===")
    print(f"Overall: Trades={tot_trades} | WinRate={overall_wr}% | PF={overall_pf} | Net={tot_r:+.1f}R | Exp={overall_exp:+.3f}R")
    for p in pairs:
        r = results[p]
        print(f"  {p:6s}: Trades={r['trades']:3d} | WR={r['win_rate']:4.1f}% | PF={r['profit_factor']:4.2f} | Net={r['total_r']:+6.1f}R | MaxDD={r['max_dd_r']:4.1f}R | BE={r.get('breakevens', 0)}")
    print()

run_experiment_across_all("1. Baseline (Donchian 20, 24/7, No D1, No Squeeze, Fixed 1:2 RR)", lookback=20)
run_experiment_across_all("2. Session Filter Only (London + NY: 07-16 UTC)", lookback=20, use_session=True)
run_experiment_across_all("3. Macro Daily Trend Filter (D1 EMA 50)", lookback=20, use_d1=True)
run_experiment_across_all("4. Session + Daily Trend", lookback=20, use_session=True, use_d1=True)
run_experiment_across_all("5. Lookback 36h (1.5 Days) + Session + D1", lookback=36, use_session=True, use_d1=True)
run_experiment_across_all("6. Lookback 48h (2 Full Days) + Session + D1", lookback=48, use_session=True, use_d1=True)
run_experiment_across_all("7. Lookback 72h (3 Full Days) + Session + D1", lookback=72, use_session=True, use_d1=True)
run_experiment_across_all("8. Squeeze Contraction Pre-Filter + Lookback 48h + Session + D1", lookback=48, use_session=True, use_d1=True, use_squeeze=True)
run_experiment_across_all("9. Rising ADX Momentum + Lookback 48h + Session + D1", lookback=48, use_session=True, use_d1=True, use_adx_rising=True)
run_experiment_across_all("10. Anti-Wick Body Filter (>=50% body) + Lookback 48h + Session + D1", lookback=48, use_session=True, use_d1=True, use_body_filter=True)
run_experiment_across_all("11. Breakeven at +1R + Lookback 48h + Session + D1 + Rising ADX", lookback=48, use_session=True, use_d1=True, use_adx_rising=True, be_at_1r=True)
run_experiment_across_all("12. THE OPTIMIZED COMBO: 48h Lookback + Session + D1 + Squeeze + Rising ADX + BE@1R", lookback=48, use_session=True, use_d1=True, use_squeeze=True, use_adx_rising=True, be_at_1r=True)
