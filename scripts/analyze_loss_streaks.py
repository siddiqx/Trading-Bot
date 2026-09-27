import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np
from scripts.test_strategies_deep import load_data

data = load_data()

# Let's inspect EURUSD trades under optimal settings
eur_h1 = data['EURUSD']['H1'].copy()
eur_d1 = data['EURUSD']['D1'].copy()

# Run backtest tracking each trade and timestamp
pip_unit = 0.0001
min_sl_dist = 16.0 * pip_unit
rr = 1.5
sl_mult = 0.4
max_hunt = 4

eur_d1['ema50'] = eur_d1['close'].ewm(span=50, adjust=False).mean()
eur_d1['time_dt'] = pd.to_datetime(eur_d1['time'], unit='s').dt.floor('D')
eur_h1['time_dt'] = pd.to_datetime(eur_h1['time'], unit='s')
eur_h1['date_only'] = eur_h1['time_dt'].dt.floor('D')
d1_map = dict(zip(eur_d1['time_dt'], eur_d1['close'] > eur_d1['ema50']))
eur_h1['d1_bull'] = eur_h1['date_only'].map(d1_map).fillna(False).values
eur_h1['d1_bear'] = ~eur_h1['d1_bull']

close = eur_h1['close'].values
open_ = eur_h1['open'].values
high = eur_h1['high'].values
low = eur_h1['low'].values
n = len(close)

ema200 = eur_h1['close'].ewm(span=200, adjust=False).mean().values
ema50 = eur_h1['close'].ewm(span=50, adjust=False).mean().values
ema20 = eur_h1['close'].ewm(span=20, adjust=False).mean().values

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

for i in range(200, n):
    c = close[i]
    h = high[i]
    l = low[i]
    o = open_[i]
    a = atr[i]
    
    if state != 0:
        if state == 1:
            if h >= tp_price:
                trades.append({'entry_time': eur_h1['time_dt'].iloc[entry_idx], 'exit_time': eur_h1['time_dt'].iloc[i], 'type': 'LONG', 'res': 'WIN', 'pips': (tp_price - entry_price)/pip_unit, 'R': rr})
                state = 0
            elif l <= sl_price:
                trades.append({'entry_time': eur_h1['time_dt'].iloc[entry_idx], 'exit_time': eur_h1['time_dt'].iloc[i], 'type': 'LONG', 'res': 'LOSS', 'pips': (sl_price - entry_price)/pip_unit, 'R': -1.0})
                state = 0
            elif (i - entry_idx) >= 160:
                pips = (c - entry_price) / pip_unit
                res = 'WIN' if pips > 0 else 'LOSS'
                r_mult = pips / ((entry_price - sl_price) / pip_unit)
                trades.append({'entry_time': eur_h1['time_dt'].iloc[entry_idx], 'exit_time': eur_h1['time_dt'].iloc[i], 'type': 'LONG', 'res': res, 'pips': pips, 'R': r_mult})
                state = 0
        elif state == -1:
            if l <= tp_price:
                trades.append({'entry_time': eur_h1['time_dt'].iloc[entry_idx], 'exit_time': eur_h1['time_dt'].iloc[i], 'type': 'SHORT', 'res': 'WIN', 'pips': (entry_price - tp_price)/pip_unit, 'R': rr})
                state = 0
            elif h >= sl_price:
                trades.append({'entry_time': eur_h1['time_dt'].iloc[entry_idx], 'exit_time': eur_h1['time_dt'].iloc[i], 'type': 'SHORT', 'res': 'LOSS', 'pips': (entry_price - sl_price)/pip_unit, 'R': -1.0})
                state = 0
            elif (i - entry_idx) >= 160:
                pips = (entry_price - c) / pip_unit
                res = 'WIN' if pips > 0 else 'LOSS'
                r_mult = pips / ((sl_price - entry_price) / pip_unit)
                trades.append({'entry_time': eur_h1['time_dt'].iloc[entry_idx], 'exit_time': eur_h1['time_dt'].iloc[i], 'type': 'SHORT', 'res': res, 'pips': pips, 'R': r_mult})
                state = 0
        continue
        
    if hunting == 0:
        long_cond = (break_high[i] and c > ema200[i] and ema20[i] > ema50[i] and 
                     rsi[i] >= 45 and rsi[i] <= 70 and eur_h1['d1_bull'].iloc[i])
        short_cond = (break_low[i] and c < ema200[i] and ema20[i] < ema50[i] and 
                      rsi[i] >= 30 and rsi[i] <= 55 and eur_h1['d1_bear'].iloc[i])
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
            if retrace and rejection and eur_h1['time_dt'].iloc[i].hour != 21:
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
            if retrace and rejection and eur_h1['time_dt'].iloc[i].hour != 21:
                state = -1
                hunting = 0
                entry_price = c
                entry_idx = i
                raw_sl = hunt_ob_h + (hunt_atr * sl_mult)
                sl_dist = max(raw_sl - entry_price, min_sl_dist)
                sl_price = entry_price + sl_dist
                tp_price = entry_price - (sl_dist * rr)

df_tr = pd.DataFrame(trades)
print(f"EURUSD Total Trades: {len(df_tr)}, Wins: {(df_tr['res'] == 'WIN').sum()}, Losses: {(df_tr['res'] == 'LOSS').sum()}")
print(f"EURUSD Win Rate: {(df_tr['res'] == 'WIN').mean()*100:.1f}%, Net R: {df_tr['R'].sum():.1f}R")

# Find all losing streaks >= 3
loss_streaks = []
cur_streak = []
for idx, row in df_tr.iterrows():
    if row['res'] == 'LOSS':
        cur_streak.append(row)
    else:
        if len(cur_streak) >= 3:
            loss_streaks.append(cur_streak)
        cur_streak = []
if len(cur_streak) >= 3:
    loss_streaks.append(cur_streak)

print(f"\nNumber of loss streaks >= 3: {len(loss_streaks)}")
for i, s in enumerate(loss_streaks[:5]):
    start_t = s[0]['entry_time']
    end_t = s[-1]['exit_time']
    print(f"Streak #{i+1}: Length {len(s)} from {start_t} to {end_t}")
    for t in s:
        print(f"  {t['entry_time']} | {t['type']} | Pips: {t['pips']:.1f}")
