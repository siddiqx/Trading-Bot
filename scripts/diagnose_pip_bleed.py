import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np
from scripts.backtest_last_6_months import run_last_6_months_audit

# Let's inspect all trades from last 6 months
with open('archives/data_cache_orb.pkl', 'rb') as f:
    data = pickle.load(f)
pairs_data = data[1]

# Run baseline simulation tracking every detail
pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'USDCHF']
all_trades = []

for pair in pairs:
    m15 = pairs_data[pair]['M15'].copy()
    h1 = pairs_data[pair]['H1'].copy()
    d1 = pairs_data[pair]['D1'].copy()
    
    is_jpy = 'JPY' in pair
    pip_unit = 0.01 if is_jpy else 0.0001
    min_sl_dist = 20.0 * pip_unit
    max_sl_dist = 60.0 * pip_unit
    rr = 1.5
    sl_mult = 0.5
    
    d1['ema50'] = d1['close'].ewm(span=50, adjust=False).mean()
    d1['time_dt'] = pd.to_datetime(d1['time'], unit='s').dt.floor('D')
    
    h1['time_dt'] = pd.to_datetime(h1['time'], unit='s')
    h1['ema200'] = h1['close'].ewm(span=200, adjust=False).mean()
    h1['ema50'] = h1['close'].ewm(span=50, adjust=False).mean()
    h1['ema20'] = h1['close'].ewm(span=20, adjust=False).mean()
    h1['ema20_slope'] = h1['ema20'] - h1['ema20'].shift(2)
    
    h1['date_only'] = h1['time_dt'].dt.floor('D')
    d1_bull_map = dict(zip(d1['time_dt'], d1['close'] > d1['ema50']))
    h1['d1_bull'] = h1['date_only'].map(d1_bull_map).fillna(False)
    
    h1['h1_bull'] = (h1['close'] > h1['ema200']) & (h1['ema20'] > h1['ema50']) & (h1['d1_bull']) & (h1['ema20_slope'] > 0)
    h1['h1_bear'] = (h1['close'] < h1['ema200']) & (h1['ema20'] < h1['ema50']) & (~h1['d1_bull']) & (h1['ema20_slope'] < 0)
    
    m15['time_dt'] = pd.to_datetime(m15['time'], unit='s')
    m15['h1_time'] = m15['time_dt'].dt.floor('h') - pd.Timedelta(hours=1)
    
    h1_bull_map = dict(zip(h1['time_dt'], h1['h1_bull']))
    h1_bear_map = dict(zip(h1['time_dt'], h1['h1_bear']))
    
    m15['h1_bull'] = m15['h1_time'].map(h1_bull_map).fillna(False).values
    m15['h1_bear'] = m15['h1_time'].map(h1_bear_map).fillna(False).values
    
    close = m15['close'].values
    open_ = m15['open'].values
    high = m15['high'].values
    low = m15['low'].values
    hours = m15['time_dt'].dt.hour.values
    n = len(close)
    
    m15_ema20 = m15['close'].ewm(span=20, adjust=False).mean().values
    m15_ema50 = m15['close'].ewm(span=50, adjust=False).mean().values
    
    tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    atr14 = pd.Series(tr).rolling(14).mean().bfill().values
    atr_sma = pd.Series(atr14).rolling(20).mean().bfill().values
    atr_ratio = atr14 / (atr_sma + 1e-9)
    
    delta = pd.Series(close).diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    rsi = (100 - (100 / (1 + rs))).bfill().values
    
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
    
    for i in range(200, n):
        c = close[i]
        h = high[i]
        l = low[i]
        o = open_[i]
        a = atr14[i]
        hr = hours[i]
        
        if state != 0:
            if state == 1:
                if h >= tp_price:
                    all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'WIN', 'pips': (tp_price - entry_price)/pip_unit, 'sl_pips': (entry_price - sl_price)/pip_unit, 'tp_pips': (tp_price - entry_price)/pip_unit, 'hold': i - entry_idx, 'hour': hours[entry_idx]})
                    state = 0
                    consec_losses = 0
                elif l <= sl_price:
                    all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'LOSS', 'pips': (sl_price - entry_price)/pip_unit, 'sl_pips': (entry_price - sl_price)/pip_unit, 'tp_pips': (tp_price - entry_price)/pip_unit, 'hold': i - entry_idx, 'hour': hours[entry_idx]})
                    state = 0
                    consec_losses += 1
                    if consec_losses >= 2:
                        pause_until_idx = i + 48
                        consec_losses = 0
                elif (i - entry_idx) >= 160:
                    pips = (c - entry_price) / pip_unit
                    res = 'WIN' if pips > 0 else 'LOSS'
                    all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'pips': pips, 'sl_pips': (entry_price - sl_price)/pip_unit, 'tp_pips': (tp_price - entry_price)/pip_unit, 'hold': i - entry_idx, 'hour': hours[entry_idx]})
                    state = 0
                    if res == 'LOSS':
                        consec_losses += 1
                        if consec_losses >= 2:
                            pause_until_idx = i + 48
                            consec_losses = 0
                    else:
                        consec_losses = 0
            elif state == -1:
                if l <= tp_price:
                    all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'WIN', 'pips': (entry_price - tp_price)/pip_unit, 'sl_pips': (sl_price - entry_price)/pip_unit, 'tp_pips': (entry_price - tp_price)/pip_unit, 'hold': i - entry_idx, 'hour': hours[entry_idx]})
                    state = 0
                    consec_losses = 0
                elif h >= sl_price:
                    all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': 'LOSS', 'pips': (entry_price - sl_price)/pip_unit, 'sl_pips': (sl_price - entry_price)/pip_unit, 'tp_pips': (entry_price - tp_price)/pip_unit, 'hold': i - entry_idx, 'hour': hours[entry_idx]})
                    state = 0
                    consec_losses += 1
                    if consec_losses >= 2:
                        pause_until_idx = i + 48
                        consec_losses = 0
                elif (i - entry_idx) >= 160:
                    pips = (entry_price - c) / pip_unit
                    res = 'WIN' if pips > 0 else 'LOSS'
                    all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'res': res, 'pips': pips, 'sl_pips': (sl_price - entry_price)/pip_unit, 'tp_pips': (entry_price - tp_price)/pip_unit, 'hold': i - entry_idx, 'hour': hours[entry_idx]})
                    state = 0
                    if res == 'LOSS':
                        consec_losses += 1
                        if consec_losses >= 2:
                            pause_until_idx = i + 48
                            consec_losses = 0
                    else:
                        consec_losses = 0
            continue
            
        if i < pause_until_idx:
            continue
            
        in_session = (hr >= 7 and hr <= 16)
        
        if hunting == 0:
            long_setup = break_high[i] and h1_bull[i] and (m15_ema20[i] > m15_ema50[i]) and (atr_ratio[i] >= 1.0) and in_session
            short_setup = break_low[i] and h1_bear[i] and (m15_ema20[i] < m15_ema50[i]) and (atr_ratio[i] >= 1.0) and in_session
            
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
            if (i - hunt_idx) > 4:
                hunting = 0
            elif hunting == 1:
                retrace = (l <= hunt_fib50) or (l <= hunt_ob_h)
                rejection = c > o
                rsi_ok = rsi[i] <= 68.0
                if retrace and rejection and rsi_ok and in_session:
                    raw_sl = hunt_ob_l - (hunt_atr * sl_mult)
                    sl_dist = max(c - raw_sl, min_sl_dist)
                    if sl_dist <= max_sl_dist:
                        state = 1
                        hunting = 0
                        entry_price = c
                        entry_idx = i
                        sl_price = entry_price - sl_dist
                        tp_price = entry_price + (sl_dist * rr)
            elif hunting == -1:
                retrace = (h >= hunt_fib50) or (h >= hunt_ob_l)
                rejection = c < o
                rsi_ok = rsi[i] >= 32.0
                if retrace and rejection and rsi_ok and in_session:
                    raw_sl = hunt_ob_h + (hunt_atr * sl_mult)
                    sl_dist = max(raw_sl - c, min_sl_dist)
                    if sl_dist <= max_sl_dist:
                        state = -1
                        hunting = 0
                        entry_price = c
                        entry_idx = i
                        sl_price = entry_price + sl_dist
                        tp_price = entry_price - (sl_dist * rr)

df = pd.DataFrame(all_trades)
df['time'] = pd.to_datetime(df['time'])
df_6m = df[(df['time'] >= '2026-03-15') & (df['time'] <= '2026-09-16')].copy()

print("="*60)
print("LAST 6 MONTHS: DETAILED PIP BLEED DIAGNOSIS")
print("="*60)
print(f"Total Trades: {len(df_6m)}")
print(f"Gross Pips Won:  {df_6m[df_6m['pips'] > 0]['pips'].sum():+.0f} pips across {len(df_6m[df_6m['pips'] > 0])} wins (avg {df_6m[df_6m['pips'] > 0]['pips'].mean():.1f} pips/win)")
print(f"Gross Pips Lost: {df_6m[df_6m['pips'] < 0]['pips'].sum():+.0f} pips across {len(df_6m[df_6m['pips'] < 0])} losses (avg {df_6m[df_6m['pips'] < 0]['pips'].mean():.1f} pips/loss)")
print(f"Net Pips:        {df_6m['pips'].sum():+.0f} pips")

print("\nPip Breakdown by Pair (Last 6 Months):")
pair_pip = df_6m.groupby('pair').agg(
    trades=('pips', 'count'),
    wins=('res', lambda x: (x == 'WIN').sum()),
    losses=('res', lambda x: (x == 'LOSS').sum()),
    gross_win_pips=('pips', lambda x: x[x > 0].sum()),
    gross_loss_pips=('pips', lambda x: x[x < 0].sum()),
    net_pips=('pips', 'sum')
)
print(pair_pip.to_string())

print("\nPip Breakdown by Entry Hour (UTC) (Last 6 Months):")
hr_pip = df_6m.groupby('hour').agg(
    trades=('pips', 'count'),
    win_rate=('res', lambda x: (x == 'WIN').mean() * 100),
    net_pips=('pips', 'sum')
)
print(hr_pip.to_string())
