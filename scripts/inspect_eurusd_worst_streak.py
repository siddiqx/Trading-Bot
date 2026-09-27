import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np
from scripts.test_pattern_improvements import run_simulation

trades = run_simulation(
    use_session_filter=True,
    min_atr_ratio=1.0,
    require_m15_ema=True,
    max_hunt_bars=4,
    use_circuit_breaker=True,
    cb_trigger=2,
    cb_pause=24
)

eur = trades[trades['pair'] == 'EURUSD'].sort_values('time').reset_index(drop=True)
eur['is_loss'] = (eur['res'] == 'LOSS').astype(int)

# Identify the streak of 19
eur['streak_id'] = (eur['res'] == 'WIN').cumsum()
streak_sizes = eur[eur['res'] == 'LOSS'].groupby('streak_id').size()
worst_streak_id = streak_sizes.idxmax()
print(f"Worst streak id: {worst_streak_id} with size {streak_sizes.max()}")

worst_trades = eur[eur['streak_id'] == worst_streak_id]
print("\nWorst Streak Trades:")
print(worst_trades[['time', 'res', 'R', 'pips']].to_string())
