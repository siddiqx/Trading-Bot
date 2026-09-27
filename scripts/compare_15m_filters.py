import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np
from scripts.optimize_15m_mtf import load_all_m15_and_h1, test_15m_variations
from scripts.test_strategies_deep import print_summary

data = load_all_m15_and_h1()

print("\n" + "="*70)
print("TEST A: 15m Entry (32-bar / 8h Session) WITHOUT Session Filter (24 Hours)")
print("="*70)
res_24h = test_15m_variations(data, donch_len=32, require_session=False, require_m15_ema=True, min_sl_pips=16.0)
print_summary(res_24h, "15m 24-Hours (No Session Filter)")

print("\n" + "="*70)
print("TEST B: 15m Entry (32-bar / 8h Session) WITH London/NY Session Filter (07:00 - 17:00 UTC)")
print("="*70)
res_session = test_15m_variations(data, donch_len=32, require_session=True, require_m15_ema=True, min_sl_pips=16.0)
print_summary(res_session, "15m London/NY Session (07-17 UTC)")
