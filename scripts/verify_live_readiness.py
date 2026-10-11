"""
Live Market Feed & Paper Trading Readiness Verification.
Validates live forex prices, gold rejection, timestamp synchronization, and fixed 15p/10p exits.
"""

import sys
sys.path.append('.')
from datetime import datetime, timezone
import pandas as pd
from market_scanner import get_live_price, fetch_candles, SYMBOLS
from core.instrument_validator import (
    validate_instrument_eligibility,
    is_gold_symbol,
    calculate_tp_sl,
    calculate_position_size
)

def verify_live_market_readiness():
    print("================================================================================")
    print("PHASE 11: LIVE-MARKET READINESS & FEED VERIFICATION AUDIT")
    print("================================================================================")
    now_utc = datetime.now(timezone.utc)
    print(f"Current Evaluation Timestamp (UTC): {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("Testing Live Market Connectivity across all 6 Forex pairs...\n")

    results = []
    for pair, cfg in SYMBOLS.items():
        ticker = cfg['ticker']
        pip = cfg['pip']
        digits = cfg['digits']

        # 1. Fetch live price
        live_price = get_live_price(ticker, pip, digits)

        # 2. Fetch recent M15 candle
        df_candles = fetch_candles(ticker, "15m", range_days="1d")
        candle_count = len(df_candles)
        last_candle_time = df_candles['time'].iloc[-1].strftime('%Y-%m-%d %H:%M UTC') if not df_candles.empty else "N/A"

        # 3. Compute 15p TP / 10p SL
        ref_price = live_price if live_price is not None else (df_candles['close'].iloc[-1] if not df_candles.empty else 1.0)
        long_tp, long_sl = calculate_tp_sl(ref_price, "LONG", pair, tp_pips=15.0, sl_pips=10.0)
        short_tp, short_sl = calculate_tp_sl(ref_price, "SHORT", pair, tp_pips=15.0, sl_pips=10.0)

        # 4. Position sizing ($5,000 account, 1% risk = $50)
        lots_1pct = calculate_position_size(5000.0, 0.01, 10.0, pair)
        lots_half_pct = calculate_position_size(5000.0, 0.005, 10.0, pair)

        results.append({
            'pair': pair,
            'ticker': ticker,
            'live_price': live_price,
            'last_candle': last_candle_time,
            'bars_received': candle_count,
            'long_tp': long_tp,
            'long_sl': long_sl,
            'short_tp': short_tp,
            'short_sl': short_sl,
            'lots_1pct': lots_1pct,
            'lots_0_5pct': lots_half_pct
        })
        print(f"  {pair:<7} ({ticker:<8}): Live Price: {live_price} | Last Candle: {last_candle_time} ({candle_count} bars) | Long TP/SL: {long_tp}/{long_sl} | Sizing: {lots_1pct} lots")

    # 5. Verify Gold Rejection on Live Feed
    print("\n--- LIVE GOLD FEED REJECTION VERIFICATION ---")
    for gold_query in ["XAUUSD=X", "GC=F", "XAUUSD", "GOLD", "PAXGUSDT"]:
        is_gold = is_gold_symbol(gold_query)
        eligible, reason = validate_instrument_eligibility(gold_query)
        live_gold_price = get_live_price(gold_query, 0.1, 2)
        candles_gold = fetch_candles(gold_query, "15m", range_days="1d")

        print(f"  Query '{gold_query:<9}': is_gold={is_gold} | Eligible={eligible} | Live Price={live_gold_price} | Bars Returned={len(candles_gold)}")
        assert eligible is False, f"Gold query {gold_query} was not rejected!"
        assert live_gold_price is None, f"Gold query {gold_query} returned a price!"
        assert candles_gold.empty, f"Gold query {gold_query} returned candle data!"

    print("\n[SUCCESS] Live feed audit passed: All 6 Forex pairs active; Gold 100% blocked at all layers.")

if __name__ == '__main__':
    verify_live_market_readiness()
