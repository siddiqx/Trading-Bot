import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- CONFIG ---
PAIRS = ["USDJPY", "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF"]
END_DATE = datetime.now()
START_DATE = END_DATE - timedelta(days=182)

BIAS_LOOKBACK_DAYS = 20
DISPLACEMENT_LOOKAHEAD_H1 = 3
DISPLACEMENT_RANGE_MULT = 1.3
DISPLACEMENT_VOL_MULT = 1.15
MSS_LOOKAHEAD_M15 = 32
ENTRY_LOOKAHEAD_M3 = 20
ENTRY_LOOKAHEAD_M3_OVERRIDE = {"XAUUSD": 60}  # gold gets 3 hours instead of 1
FORWARD_CHECK_M3 = 300
FALLBACK_RR = 2.0
SWING_LOOKBACK = 20
SL_WICK_BUFFER_MULT = 0.15
TP_SEARCH_LOOKBACK_H1 = 100

def add_months(d, months):
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    return datetime(year, month, 1)

def fetch_in_chunks(symbol, timeframe, start, end, chunk_months=3):
    all_rates = []
    current = start
    ok, failed = 0, 0
    while current < end:
        chunk_end = min(add_months(current, chunk_months), end)
        rates = mt5.copy_rates_range(symbol, timeframe, current, chunk_end)
        if rates is not None and len(rates) > 0:
            all_rates.append(rates)
            ok += 1
        else:
            failed += 1
        current = chunk_end
    if failed > 0:
        print(f"    [{symbol}] chunk fetch: {ok} ok, {failed} FAILED")
    if not all_rates:
        return None
    return np.concatenate(all_rates)

def load_rates(symbol, timeframe, start, end, chunk_months=3):
    if not mt5.symbol_select(symbol, True):
        return None
    rates = fetch_in_chunks(symbol, timeframe, start, end, chunk_months)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df = df.drop_duplicates(subset='time').reset_index(drop=True)
    return df

def build_daily_context(df_daily):
    context = {}
    for i in range(BIAS_LOOKBACK_DAYS, len(df_daily)):
        today_date = df_daily.iloc[i]['time'].date()
        prev = df_daily.iloc[i - 1]
        context[today_date] = {"pdh": prev['high'], "pdl": prev['low']}
    return context

def detect_sweep_h1(candle, pdh, pdl):
    if candle['high'] > pdh and candle['close'] < pdh:
        return "bearish_sweep", pdh, candle['high']
    if candle['low'] < pdl and candle['close'] > pdl:
        return "bullish_sweep", pdl, candle['low']
    return None, None, None

def is_displacement(candle, avg_rng, avg_vol, expected_dir):
    rng = candle['high'] - candle['low']
    body = abs(candle['close'] - candle['open'])
    if rng == 0 or rng < avg_rng * DISPLACEMENT_RANGE_MULT:
        return False
    if candle['tick_volume'] < avg_vol * DISPLACEMENT_VOL_MULT:
        return False
    if body < rng * 0.6:
        return False
    if expected_dir == "bullish" and candle['close'] <= candle['open']:
        return False
    if expected_dir == "bearish" and candle['close'] >= candle['open']:
        return False
    return True

def find_swing_points(window):
    highs, lows = window['high'], window['low']
    swing_low_idx = lows[1:-1][(lows.shift(1) > lows) & (lows.shift(-1) > lows)].index
    swing_high_idx = highs[1:-1][(highs.shift(1) < highs) & (highs.shift(-1) < highs)].index
    return swing_high_idx, swing_low_idx

def detect_mss_after(df_m15, start_time, expected_dir):
    start_idx = df_m15[df_m15['time'] > start_time].index
    if len(start_idx) == 0:
        return None, None
    start_idx = start_idx[0]
    for j in range(start_idx, min(start_idx + MSS_LOOKAHEAD_M15, len(df_m15))):
        if j < SWING_LOOKBACK:
            continue
        window = df_m15.iloc[j - SWING_LOOKBACK:j]
        swing_high_idx, swing_low_idx = find_swing_points(window)
        last_close = df_m15.iloc[j]['close']
        if expected_dir == "bullish" and len(swing_high_idx) > 0:
            recent_high = df_m15['high'].loc[swing_high_idx[-1]]
            if last_close > recent_high:
                return df_m15.iloc[j]['time'], j
        if expected_dir == "bearish" and len(swing_low_idx) > 0:
            recent_low = df_m15['low'].loc[swing_low_idx[-1]]
            if last_close < recent_low:
                return df_m15.iloc[j]['time'], j
    return None, None

def find_entry_fill(df_m3, mss_time, entry_low, entry_high, lookahead):
    start_idx = df_m3[df_m3['time'] > mss_time].index
    if len(start_idx) == 0:
        return None
    start_idx = start_idx[0]
    for j in range(start_idx, min(start_idx + lookahead, len(df_m3))):
        bar = df_m3.iloc[j]
        if bar['low'] <= entry_high and bar['high'] >= entry_low:
            return j
    return None

def find_tp_target(df_h1, sweep_idx, entry_price, direction, sl_dist):
    start = max(0, sweep_idx - TP_SEARCH_LOOKBACK_H1)
    window = df_h1.iloc[start:sweep_idx]
    swing_high_idx, swing_low_idx = find_swing_points(window)

    if direction == "bullish":
        candidates = df_h1['high'].loc[swing_high_idx]
        candidates = candidates[candidates > entry_price]
        if len(candidates) > 0:
            target = candidates.min()
            if (target - entry_price) >= sl_dist:
                return target
    else:
        candidates = df_h1['low'].loc[swing_low_idx]
        candidates = candidates[candidates < entry_price]
        if len(candidates) > 0:
            target = candidates.max()
            if (entry_price - target) >= sl_dist:
                return target

    return entry_price + sl_dist * FALLBACK_RR if direction == "bullish" else entry_price - sl_dist * FALLBACK_RR

def simulate_outcome_m3(df_m3, entry_idx, entry, sl, tp, direction):
    for j in range(entry_idx + 1, min(entry_idx + FORWARD_CHECK_M3, len(df_m3))):
        bar = df_m3.iloc[j]
        if direction == "bullish":
            if bar['low'] <= sl:
                return "loss", -1.0
            if bar['high'] >= tp:
                r = (tp - entry) / (entry - sl) if (entry - sl) != 0 else 0
                return "win", r
        else:
            if bar['high'] >= sl:
                return "loss", -1.0
            if bar['low'] <= tp:
                r = (entry - tp) / (sl - entry) if (sl - entry) != 0 else 0
                return "win", r
    return "no_fill", 0.0

def backtest_pair(symbol):
    df_daily = load_rates(symbol, mt5.TIMEFRAME_D1, START_DATE - timedelta(days=BIAS_LOOKBACK_DAYS + 5), END_DATE, chunk_months=24)
    df_h1 = load_rates(symbol, mt5.TIMEFRAME_H1, START_DATE, END_DATE, chunk_months=6)
    df_m15 = load_rates(symbol, mt5.TIMEFRAME_M15, START_DATE, END_DATE, chunk_months=6)
    df_m3 = load_rates(symbol, mt5.TIMEFRAME_M3, START_DATE, END_DATE, chunk_months=2)

    if any(x is None for x in [df_daily, df_h1, df_m15, df_m3]):
        print(f"[{symbol}] Missing data on one or more timeframes. Error: {mt5.last_error()}")
        return []

    print(f"    [{symbol}] D1:{len(df_daily)} H1:{len(df_h1)} M15:{len(df_m15)} M3:{len(df_m3)} bars loaded")

    daily_context = build_daily_context(df_daily)
    results = []
    seen_signals = set()

    lookahead = ENTRY_LOOKAHEAD_M3_OVERRIDE.get(symbol, ENTRY_LOOKAHEAD_M3)

    for i in range(TP_SEARCH_LOOKBACK_H1, len(df_h1) - DISPLACEMENT_LOOKAHEAD_H1):
        bar_date = df_h1.iloc[i]['time'].date()
        ctx = daily_context.get(bar_date)
        if not ctx:
            continue
        pdh, pdl = ctx["pdh"], ctx["pdl"]

        sweep_type, level, wick_extreme = detect_sweep_h1(df_h1.iloc[i], pdh, pdl)
        if not sweep_type:
            continue
        expected_dir = "bullish" if sweep_type == "bullish_sweep" else "bearish"

        recent_h1 = df_h1.iloc[i - 20:i]
        avg_rng = (recent_h1['high'] - recent_h1['low']).mean()
        avg_vol = recent_h1['tick_volume'].mean()

        displacement_idx = None
        for k in range(i + 1, i + 1 + DISPLACEMENT_LOOKAHEAD_H1):
            if k >= len(df_h1):
                break
            if is_displacement(df_h1.iloc[k], avg_rng, avg_vol, expected_dir):
                displacement_idx = k
                break
        if displacement_idx is None:
            continue

        window_h1 = df_h1.iloc[i + 1: displacement_idx + 1]
        impulse_end = window_h1['high'].max() if expected_dir == "bullish" else window_h1['low'].min()
        impulse_start = level
        displacement_time = df_h1.iloc[displacement_idx]['time']

        mss_time, mss_idx = detect_mss_after(df_m15, displacement_time, expected_dir)
        if mss_time is None:
            continue

        diff = impulse_end - impulse_start
        if expected_dir == "bullish":
            entry_low = impulse_start + diff * 0.5
            entry_high = impulse_start + diff * 0.618
        else:
            entry_high = impulse_start + diff * 0.5
            entry_low = impulse_start + diff * 0.618
        if entry_low > entry_high:
            entry_low, entry_high = entry_high, entry_low

        fill_idx = find_entry_fill(df_m3, mss_time, entry_low, entry_high, lookahead)
        if fill_idx is None:
            continue

        signal_key = (df_m3.iloc[fill_idx]['time'], expected_dir)
        if signal_key in seen_signals:
            continue
        seen_signals.add(signal_key)

        entry_price = (entry_low + entry_high) / 2
        sl_buffer = avg_rng * SL_WICK_BUFFER_MULT
        sl = wick_extreme - sl_buffer if expected_dir == "bullish" else wick_extreme + sl_buffer
        sl_dist = abs(entry_price - sl)

        tp = find_tp_target(df_h1, i, entry_price, expected_dir, sl_dist)

        outcome, r_multiple = simulate_outcome_m3(df_m3, fill_idx, entry_price, sl, tp, expected_dir)
        results.append({
            "symbol": symbol, "time": df_m3.iloc[fill_idx]['time'], "direction": expected_dir,
            "entry": entry_price, "sl": sl, "tp": tp, "outcome": outcome, "r_multiple": round(r_multiple, 2)
        })

    return results

def main():
    if not mt5.initialize():
        print("MT5 init failed:", mt5.last_error())
        return

    print(f"Backtest range: {START_DATE.date()} to {END_DATE.date()}\n")

    all_results = []
    for pair in PAIRS:
        print(f"Backtesting {pair}...")
        res = backtest_pair(pair)
        print(f"  -> {len(res)} signals found")
        all_results.extend(res)

    mt5.shutdown()

    df = pd.DataFrame(all_results)
    if df.empty:
        print("\nNo signals found in this period.")
        return

    df.to_csv("backtest_freq_results.csv", index=False)

    decided = df[df['outcome'] != 'no_fill']
    wins = decided[decided['outcome'] == 'win']
    win_rate = len(wins) / len(decided) * 100 if len(decided) > 0 else 0

    print(f"\n--- RESULTS ---")
    print(f"Total signals: {len(df)}")
    print(f"Decided (win/loss): {len(decided)}")
    print(f"Win rate: {win_rate:.1f}%")
    print(f"Total R: {decided['r_multiple'].sum():.2f}")
    print(f"\nPer pair breakdown:")
    print(df.groupby('symbol')['outcome'].value_counts())
    print(f"\nFull results saved to backtest_freq_results.csv")

if __name__ == "__main__":
    main()
