import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

with open('archives/data_cache_orb.pkl', 'rb') as f:
    data = pickle.load(f)
eur_h1 = data[1]['EURUSD']['H1'].copy()
eur_m15 = data[1]['EURUSD']['M15'].copy()

# Calculate ADX on H1
def calc_adx(df, n=14):
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    
    tr = np.maximum(high - low, np.maximum(abs(high - np.roll(close, 1)), abs(low - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    
    up = high - np.roll(high, 1)
    down = np.roll(low, 1) - low
    up[0] = 0
    down[0] = 0
    
    pos_dm = np.where((up > down) & (up > 0), up, 0.0)
    neg_dm = np.where((down > up) & (down > 0), down, 0.0)
    
    tr_s = pd.Series(tr).ewm(alpha=1/n, adjust=False).mean()
    pdm_s = pd.Series(pos_dm).ewm(alpha=1/n, adjust=False).mean()
    ndm_s = pd.Series(neg_dm).ewm(alpha=1/n, adjust=False).mean()
    
    pdi = 100 * pdm_s / (tr_s + 1e-9)
    ndi = 100 * ndm_s / (tr_s + 1e-9)
    dx = 100 * abs(pdi - ndi) / (pdi + ndi + 1e-9)
    adx = dx.ewm(alpha=1/n, adjust=False).mean().values
    return adx

eur_h1['adx'] = calc_adx(eur_h1)
eur_h1['time_dt'] = pd.to_datetime(eur_h1['time'], unit='s')
eur_h1['ema20'] = eur_h1['close'].ewm(span=20, adjust=False).mean()
eur_h1['ema50'] = eur_h1['close'].ewm(span=50, adjust=False).mean()
eur_h1['ema20_slope'] = (eur_h1['ema20'] - eur_h1['ema20'].shift(3)) / (eur_h1['close'] * 0.0001) # slope in pips/hour

streak_h1 = eur_h1[(eur_h1['time_dt'] >= '2022-11-15') & (eur_h1['time_dt'] <= '2023-01-25')]
print("EURUSD Nov 2022 - Jan 2023 ADX and EMA slope stats:")
print(f"Mean ADX during streak: {streak_h1['adx'].mean():.1f} | Min ADX: {streak_h1['adx'].min():.1f} | Max ADX: {streak_h1['adx'].max():.1f}")
print(f"ADX < 20 percentage: {(streak_h1['adx'] < 20).mean() * 100:.1f}%")
print(f"ADX < 25 percentage: {(streak_h1['adx'] < 25).mean() * 100:.1f}%")

# Overall EURUSD ADX stats
print(f"Overall EURUSD Mean ADX: {eur_h1['adx'].mean():.1f}")
