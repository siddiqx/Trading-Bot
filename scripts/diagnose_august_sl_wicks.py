"""
Diagnose August 2026 SL wicks and test dynamic ATR-based Stop Loss breathing room.
"""

import pickle
import pandas as pd
import numpy as np

def run_diagnosis():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
    df = all_data['XAUUSD'].copy()
    if df['time_dt'].dt.tz is not None:
        df['time_dt'] = df['time_dt'].dt.tz_localize(None)

    # Let's inspect the trades in August 2026 under the current 18-25 clamp
    import sys, os
    sys.path.insert(0, os.path.abspath('.'))
    from scripts.deep_strategy_enhancement_audit import simulate_exact_gold
    
    # 1. Benchmark (18-25 min/max SL clamp)
    t_bench = simulate_exact_gold(df, min_sl=18.0, max_sl=25.0, start_date='2026-08-01')
    tdf_bench = pd.DataFrame(t_bench)
    aug_bench = tdf_bench[(tdf_bench['entry_dt'] >= '2026-08-15') & (tdf_bench['entry_dt'] <= '2026-08-30')]
    print("CURRENT BENCHMARK (18-25 clamp) in Late August 2026:")
    print(f"Total Trades: {len(aug_bench)}, Wins: {(aug_bench['result']=='WIN').sum()}, Losses: {(aug_bench['result']=='LOSS').sum()}")
    for idx, r in aug_bench.iterrows():
        print(f"  {r['entry_dt']} -> {r['exit_dt']} | {r['result']} | hold: {r['hold_bars']}h | r: {r['r']:+.2f}")

    # Now let's test dynamic ATR breathing room:
    # What if we test different min_sl and max_sl, or pure ATR structural stop?
    def test_sl_breathing_room(min_sl_val, max_sl_val, sl_buf_val, label):
        t = simulate_exact_gold(df, min_sl=min_sl_val, max_sl=max_sl_val, sl_buffer=sl_buf_val, start_date='2026-03-15')
        tdf = pd.DataFrame(t)
        n = len(tdf)
        wins = (tdf['result'] == 'WIN').sum()
        wr = (wins / n) * 100.0 if n > 0 else 0
        win_r = tdf[tdf['result'] == 'WIN']['r'].sum()
        loss_r = abs(tdf[tdf['result'] == 'LOSS']['r'].sum())
        pf = win_r / loss_r if loss_r > 0 else 0
        
        # Max consecutive losses
        res_list = tdf['result'].tolist()
        max_streak = 0
        cur_streak = 0
        for res in res_list:
            if res == 'LOSS':
                cur_streak += 1
                max_streak = max(max_streak, cur_streak)
            else:
                cur_streak = 0
                
        # Check August trades specifically
        aug_t = tdf[(tdf['entry_dt'] >= '2026-08-15') & (tdf['entry_dt'] <= '2026-08-30')]
        aug_losses = (aug_t['result'] == 'LOSS').sum()
        aug_wins = (aug_t['result'] == 'WIN').sum()
        
        # Also run 2-year backtest
        t_2y = simulate_exact_gold(df, min_sl=min_sl_val, max_sl=max_sl_val, sl_buffer=sl_buf_val, start_date=None)
        tdf_2y = pd.DataFrame(t_2y)
        n_2y = len(tdf_2y)
        wr_2y = (tdf_2y['result'] == 'WIN').mean() * 100.0 if n_2y > 0 else 0
        win_r_2y = tdf_2y[tdf_2y['result'] == 'WIN']['r'].sum()
        loss_r_2y = abs(tdf_2y[tdf_2y['result'] == 'LOSS']['r'].sum())
        pf_2y = win_r_2y / loss_r_2y if loss_r_2y > 0 else 0
        
        return {
            'Configuration': label,
            '6M Trades': n,
            '6M Win Rate': f"{wr:.1f}%",
            '6M Profit Factor': f"{pf:.2f}",
            '6M Max Loss Streak': max_streak,
            'Late Aug Wins/Losses': f"{aug_wins}W / {aug_losses}L",
            '2Y Trades': n_2y,
            '2Y Win Rate': f"{wr_2y:.1f}%",
            '2Y Profit Factor': f"{pf_2y:.2f}"
        }

    configs = [
        (18.0, 25.0, 0.35, "1. Current Tight (Min 18, Max 25, Buf 0.35)"),
        (25.0, 40.0, 0.50, "2. Moderate Breathing (Min 25, Max 40, Buf 0.50)"),
        (25.0, 50.0, 0.65, "3. Wide Structural (Min 25, Max 50, Buf 0.65)"),
        (30.0, 50.0, 0.50, "4. ATR Native (Min 30, Max 50, Buf 0.50)"),
        (20.0, 35.0, 0.45, "5. Sweet Spot Balanced (Min 20, Max 35, Buf 0.45)"),
        (22.0, 35.0, 0.40, "6. Refined Golden (Min 22, Max 35, Buf 0.40)"),
    ]

    print("\n" + "=" * 120)
    print("STOP LOSS BREATHING ROOM SWEEP: OVERCOMING THE MINOR PULLBACK WICKOUT TRAP")
    print("=" * 120)
    out = []
    for min_s, max_s, buf, lbl in configs:
        out.append(test_sl_breathing_room(min_s, max_s, buf, lbl))
    print(pd.DataFrame(out).to_string(index=False))

if __name__ == '__main__':
    run_diagnosis()
