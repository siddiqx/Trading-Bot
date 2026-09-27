import pickle, math
import pandas as pd
import numpy as np

def research_speedup():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
        
    df_gold = all_data['XAUUSD'].copy()
    if df_gold['time_dt'].dt.tz is not None:
        df_gold['time_dt'] = df_gold['time_dt'].dt.tz_localize(None)
        
    START_2Y = '2024-10-01'
    START_6M = '2026-03-15'

    # Hypothesis 1: MFE Analysis on Winning Gold Trades
    # How far does Gold actually run once momentum triggers?
    print("=" * 80)
    print("HYPOTHESIS 1: MAXIMUM FAVORABLE EXCURSION (MFE) ON GOLD")
    print("=" * 80)
    
    from scripts.audit_signal_timing_and_latency import audit_signal_timing
    # We can inspect MFE distribution from our validated ledger
    # Let's write an exact simulator that tests:
    # 1. Base 1:1.75 R:R at 1.0% risk ($50)
    # 2. Base 1:1.75 R:R at 1.25% risk ($62.50)
    # 3. Base 1:1.75 R:R at 1.50% risk ($75.00)
    # 4. Partial TP: 50% at 1.0 R, SL to BE, 50% at 2.5 R
    # 5. Dual Engine: 6-bar London/NY Session Fast Breakout + 8-bar Baseline
    # 6. Dual Synergy: Gold + USDCAD with Strict Single-Trade Lock
    
    # Let's build a dedicated timeline simulator for each speedup method
    def evaluate_prop_speed(trades_list, risk_pct=1.0, account_size=5000.0):
        tdf = pd.DataFrame(trades_list)
        tdf['entry_dt'] = pd.to_datetime(tdf['entry_time'])
        tdf['exit_dt'] = pd.to_datetime(tdf['exit_time'])
        tdf = tdf.sort_values(by='entry_dt').reset_index(drop=True)
        
        risk_cash = account_size * (risk_pct / 100.0)
        tdf['pnl'] = tdf['r'] * risk_cash
        
        n_all = len(tdf)
        p1_days = []
        p2_days = []
        total_days = []
        dd_breaches = 0
        total_runs = 0
        
        # Test rolling challenges from every possible starting trade
        for start_i in range(0, max(1, n_all - 25)):
            total_runs += 1
            # Phase 1: Target +8% = $400
            p1_cum = 0.0
            p1_i = start_i
            p1_passed = False
            p1_peak = 0.0
            
            while p1_i < n_all:
                p1_cum += tdf.iloc[p1_i]['pnl']
                p1_peak = max(p1_peak, p1_cum)
                if (p1_peak - p1_cum) >= (account_size * 0.08): # 8% total DD limit ($400)
                    dd_breaches += 1
                    break
                if p1_cum >= (account_size * 0.08): # $400
                    p1_passed = True
                    break
                p1_i += 1
                
            if not p1_passed:
                continue
                
            p1_d = (tdf.iloc[p1_i]['exit_dt'] - tdf.iloc[start_i]['entry_dt']).days
            
            # Phase 2: Target +5% = $250
            p2_start_i = p1_i + 1
            p2_cum = 0.0
            p2_i = p2_start_i
            p2_passed = False
            p2_peak = 0.0
            
            while p2_i < n_all:
                p2_cum += tdf.iloc[p2_i]['pnl']
                p2_peak = max(p2_peak, p2_cum)
                if (p2_peak - p2_cum) >= (account_size * 0.08):
                    dd_breaches += 1
                    break
                if p2_cum >= (account_size * 0.05): # $250
                    p2_passed = True
                    break
                p2_i += 1
                
            if not p2_passed:
                continue
                
            p2_d = (tdf.iloc[p2_i]['exit_dt'] - tdf.iloc[p2_start_i]['entry_dt']).days
            
            # Payout: 14 days minimum holding
            total_pipeline = p1_d + 1 + p2_d + 1 + 14
            
            p1_days.append(p1_d)
            p2_days.append(p2_d)
            total_days.append(total_pipeline)
            
        if len(total_days) == 0:
            return {'P1 Days': 999, 'P2 Days': 999, 'Total Days': 999, 'Pass Rate': '0%'}
            
        pass_rate = (len(total_days) / total_runs) * 100.0
        return {
            'P1 Days (Median)': round(np.median(p1_days), 1),
            'P2 Days (Median)': round(np.median(p2_days), 1),
            'Total Days to Payout (Median)': round(np.median(total_days), 1),
            'Fastest Payout (Days)': round(np.min(total_days), 1),
            'Challenge Pass Rate': f"{pass_rate:.1f}%",
            'Total Trades Generated': n_all
        }

    return evaluate_prop_speed

if __name__ == '__main__':
    research_speedup()
