"""
Weekly distribution analysis
"""
import pickle
import pandas as pd
from frequency_optimizer import run_simulation

with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
    data_cache = pickle.load(f)

# Baseline
base_df = run_simulation(['XAUUSD', 'EURUSD', 'USDCAD'], data_cache)
base_wk = base_df.groupby('week_cohort').size()

# Optimized
opt_df = run_simulation(['XAUUSD', 'EURUSD', 'USDCAD'], data_cache, {'max_hunt': 12, 'lockout_hours': 12, 'min_spacing': 1})
opt_wk = opt_df.groupby('week_cohort').size()

print("BASELINE WEEKLY FREQUENCY DISTRIBUTION:")
print(f"Total active weeks: {len(base_wk)} of 103 weeks")
print(f"Mean trades/active week: {base_wk.mean():.2f}")
print(f"Median trades/active week: {base_wk.median():.1f}")
print(f"Min: {base_wk.min()} | Max: {base_wk.max()}")
print(f"Distribution counts:\n{base_wk.value_counts().sort_index()}")

print("\n" + "="*50)
print("OPTIMIZED AGILITY (max_hunt=12, Lockout=12h, Spacing=1):")
print(f"Total active weeks: {len(opt_wk)} of 103 weeks")
print(f"Mean trades/active week: {opt_wk.mean():.2f}")
print(f"Median trades/active week: {opt_wk.median():.1f}")
print(f"Min: {opt_wk.min()} | Max: {opt_wk.max()}")
print(f"Distribution counts:\n{opt_wk.value_counts().sort_index()}")
