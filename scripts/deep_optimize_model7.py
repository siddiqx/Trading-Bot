"""
Deep Optimization of Model 7 (Quant High-Conviction Engine):
Analyzing pair selection, killzone refinement, ATR-scaled targets, and daily trade filtering.
Data: 2026-04-01 to 2026-10-09 (with real spread + 0.5p slippage + 0.35p commission + SL-first ambiguity).
"""

import sys
import pickle
import pandas as pd
import numpy as np
from deep_quant_winrate_research import load_data, compute_all_indicators, run_experiment, analyze_results, CONFIGS, PAIRS

def test_model7_enhancements():
    d15, d1h = load_data()
    data_dict = compute_all_indicators(d15, d1h)

    # Base Model 7 config:
    # 4H trend, ADX >= 20, Killzone Only (07-10, 12-15 UTC), min body >= 0.50, Model J
    print("\n" + "="*85)
    print("STEP 1: PAIR SELECTION & PORTFOLIO BASKETS ON MODEL 7")
    print("="*85)

    base_cfg = {
        "tp_pips": 15.0, "sl_pips": 10.0, "use_partial_be": True, "partial_r": 1.0,
        "require_h4": True, "min_adx": 20.0, "killzone_only": True, "min_body_ratio": 0.50
    }

    # Basket 1: All 6 pairs
    df_all = run_experiment(data_dict, {**base_cfg, "allowed_pairs": PAIRS})
    analyze_results(df_all, "All 6 Pairs (Baseline Model 7)")

    # Basket 2: Top Core Triad (EURUSD, USDCHF, AUDUSD)
    df_triad = run_experiment(data_dict, {**base_cfg, "allowed_pairs": ["EURUSD", "USDCHF", "AUDUSD"]})
    analyze_results(df_triad, "Core Alpha Triad (EURUSD + USDCHF + AUDUSD)")

    # Basket 3: EURUSD + USDCHF Only (The two consistently profitable pairs)
    df_duo = run_experiment(data_dict, {**base_cfg, "allowed_pairs": ["EURUSD", "USDCHF"]})
    analyze_results(df_duo, "Institutional Euro-Swiss Duo (EURUSD + USDCHF)")

    print("\n" + "="*85)
    print("STEP 2: TARGET & SL TUNING ON CORE BASKETS")
    print("="*85)
    for p_set_name, p_list in [
        ("Core Triad (EURUSD, USDCHF, AUDUSD)", ["EURUSD", "USDCHF", "AUDUSD"]),
        ("Euro-Swiss Duo (EURUSD, USDCHF)", ["EURUSD", "USDCHF"]),
        ("All 6 Pairs", PAIRS)
    ]:
        print(f"\n--- Testing {p_set_name} across TP/SL matrix ---")
        for sl, tp in [(10.0, 15.0), (10.0, 18.0), (12.0, 18.0), (12.0, 20.0), (14.0, 21.0)]:
            cfg = {
                **base_cfg,
                "allowed_pairs": p_list,
                "sl_pips": sl,
                "tp_pips": tp
            }
            res = run_experiment(data_dict, cfg)
            if res.empty: continue
            w = (res['outcome'] == 'WIN').sum()
            tot = len(res)
            wr = (w / tot) * 100
            net_r = res['realized_r'].sum()
            net_pips = res['realized_pips'].sum()
            gw = res[res['realized_r'] > 0]['realized_r'].sum()
            gl = abs(res[res['realized_r'] < 0]['realized_r'].sum())
            pf = (gw / gl) if gl > 0 else 99.0
            print(f"  SL: {sl:4.1f}p | TP: {tp:4.1f}p | Tr: {tot:3d} | WR: {wr:5.1f}% | Net R: {net_r:+6.2f}R | PF: {pf:.2f} | Net Pips: {net_pips:+6.1f}p")

if __name__ == "__main__":
    test_model7_enhancements()
