"""
Test the new selectivity filters ONE AT A TIME instead of all stacked together, so each
gets a fair shot at showing an effect without starving the others of trades.

Run after you've widened --start / added pairs in sweep_strategy_v4.Cfg, e.g.:
    python test_filter_combos.py
"""
from dataclasses import replace
from sweep_strategy_v4 import Cfg, load_all, evaluate, summarize

# Widen these once you've confirmed your broker/data has the history:
cfg = replace(Cfg(),
              start="2021-01-01", end="2026-09-15",
              pairs=("USDJPY", "EURUSD", "GBPUSD", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD", "EURJPY"))

data = load_all(cfg, use_cache=True)

combos = {
    "all filters OFF (raw signal)": dict(htf_filter=False, require_liquidity_pool=False, atr_percentile_filter=False),
    "ATR filter ONLY":              dict(htf_filter=False, require_liquidity_pool=False, atr_percentile_filter=True),
    "HTF filter ONLY":              dict(htf_filter=True,  require_liquidity_pool=False, atr_percentile_filter=False),
    "liquidity-pool ONLY":          dict(htf_filter=False, require_liquidity_pool=True,  atr_percentile_filter=False),
    "ATR + HTF":                    dict(htf_filter=True,  require_liquidity_pool=False, atr_percentile_filter=True),
    "all three (current default)":  dict(htf_filter=True,  require_liquidity_pool=True,  atr_percentile_filter=True),
}

for label, overrides in combos.items():
    df = evaluate(data, replace(cfg, **overrides))
    summarize(df, label)

print("\nLook for: which single filter(s) hold a positive expectancy with a CI mostly above zero, "
      "on the largest trade count. Don't keep a filter just because 'more filters feels safer' - "
      "each one you add should earn its place with evidence, exactly like this table shows.")
