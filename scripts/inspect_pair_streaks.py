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

print(f"Total trades: {len(trades)}")
for pair in ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'USDCHF']:
    p_df = trades[trades['pair'] == pair].sort_values('time').copy()
    n = len(p_df)
    wins = (p_df['res'] == 'WIN').sum()
    wr = wins / n * 100
    gross_w = p_df[p_df['R'] > 0]['R'].sum()
    gross_l = abs(p_df[p_df['R'] < 0]['R'].sum())
    pf = gross_w / (gross_l + 1e-9)
    net_r = p_df['R'].sum()
    pips = p_df['pips'].sum()
    
    # Calculate streak distribution
    cur = 0
    streaks = []
    for r in p_df['res']:
        if r == 'LOSS':
            cur += 1
        else:
            if cur > 0:
                streaks.append(cur)
            cur = 0
    if cur > 0:
        streaks.append(cur)
    
    s_series = pd.Series(streaks)
    max_s = s_series.max() if len(s_series) > 0 else 0
    mean_s = s_series.mean() if len(s_series) > 0 else 0
    gt4 = (s_series >= 4).sum() if len(s_series) > 0 else 0
    gt6 = (s_series >= 6).sum() if len(s_series) > 0 else 0
    
    print(f"\n[{pair}] Trades: {n} | Win Rate: {wr:.1f}% | PF: {pf:.2f} | Net R: {net_r:+.1f}R | Net Pips: {pips:+.0f}")
    print(f"       Max Loss Streak: {max_s} | Avg Streak: {mean_s:.2f} | Streaks >=4: {gt4} | Streaks >=6: {gt6}")

