"""
Inspect Gold 1H bar characteristics: ATR, candle range, and true realistic stops
"""
import pickle
import pandas as pd
import numpy as np

with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
    data_cache = pickle.load(f)

df = data_cache['XAUUSD'].copy()
ranges = df['high'] - df['low']
tr = np.maximum(df['high'] - df['low'], np.maximum(np.abs(df['high'] - df['close'].shift(1)), np.abs(df['low'] - df['close'].shift(1))))

print(f"XAUUSD Total bars: {len(df)}")
print(f"Average 1H Bar Range: ${ranges.mean():.2f}")
print(f"Median 1H Bar Range: ${ranges.median():.2f}")
print(f"Min 1H Bar Range: ${ranges.min():.2f}")
print(f"Max 1H Bar Range: ${ranges.max():.2f}")
print(f"Average 14-ATR: ${tr.rolling(14).mean().mean():.2f}")

# Check how often a bar moves > $2.50 in both directions from open
up_wick = df['high'] - df['open']
down_wick = df['open'] - df['low']
both_over_250 = (up_wick >= 2.50) & (down_wick >= 2.50)
print(f"Bars where BOTH up and down excursion exceed $2.50: {both_over_250.sum()} / {len(df)} ({both_over_250.mean()*100:.1f}%)")
