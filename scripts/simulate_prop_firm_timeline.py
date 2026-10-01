import pickle
import pandas as pd
import numpy as np

with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
    data = pickle.load(f)

PAIRS = ["XAUUSD", "EURUSD", "USDCAD"]
PIP_SIZES = {"EURUSD": 0.0001, "USDCAD": 0.0001, "XAUUSD": 0.10}

def find_strong_pullback_liquidity(highs, lows, atrs, n, current_idx, entry, sl_dist, is_long, lookback=120):
    if is_long:
        bsl_pools = []
        for k in range(current_idx - 2, max(2, current_idx - lookback), -1):
            if (highs[k] >= highs[k-1] and highs[k] >= highs[k-2] and
                highs[k] >= highs[k+1] and highs[k] >= highs[k+2]):
                forward_window = min(n, k + 12)
                pullback_depth = highs[k] - float(np.min(lows[k:forward_window]))
                if pullback_depth >= 0.7 * atrs[k]:
                    if highs[k] >= entry + (sl_dist * 1.0):
                        bsl_pools.append(highs[k])
        if bsl_pools:
            target = min(bsl_pools)
            rr = (target - entry) / sl_dist
            if rr > 2.50:
                rr = 2.50
                target = entry + (sl_dist * 2.50)
            return float(target), float(round(rr, 2))
        return float(entry + (sl_dist * 1.75)), 1.75
    else:
        ssl_pools = []
        for k in range(current_idx - 2, max(2, current_idx - lookback), -1):
            if (lows[k] <= lows[k-1] and lows[k] <= lows[k-2] and
                lows[k] <= lows[k+1] and lows[k] <= lows[k+2]):
                forward_window = min(n, k + 12)
                pullback_depth = float(np.max(highs[k:forward_window])) - lows[k]
                if pullback_depth >= 0.7 * atrs[k]:
                    if lows[k] <= entry - (sl_dist * 1.0):
                        ssl_pools.append(lows[k])
        if ssl_pools:
            target = max(ssl_pools)
            rr = (entry - target) / sl_dist
            if rr > 2.50:
                rr = 2.50
                target = entry - (sl_dist * 2.50)
            return float(target), float(round(rr, 2))
        return float(entry - (sl_dist * 1.75)), 1.75

print("Extracting full 2-year trade sequence with ICT liquidity + 24h EMA invalidation exit...")
all_trades = []

for pair in PAIRS:
    df = data[pair].copy()
    df['time_dt'] = pd.to_datetime(df['time_dt'])
    df.sort_values('time_dt', inplace=True)
    df.reset_index(drop=True, inplace=True)
    pip = PIP_SIZES[pair]

    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    n = len(df)

    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema20_slope'] = df['ema20'] - df['ema20'].shift(2)
    donch_len = 10 if pair == "XAUUSD" else 20
    df['donch_high'] = df['high'].shift(1).rolling(donch_len).max()
    df['donch_low'] = df['low'].shift(1).rolling(donch_len).min()

    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift(1)).abs(),
        (df['low'] - df['close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    df['atr'] = tr.ewm(alpha=1.0/14.0, adjust=False).mean()

    delta = df['close'].diff()
    gain = delta.clip(lower=0).ewm(alpha=1.0/14.0, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1.0/14.0, adjust=False).mean()
    df['rsi'] = 100.0 - (100.0 / (1.0 + (gain / (loss + 1e-9))))

    atrs = df['atr'].values
    ema20_vals = df['ema20'].values
    min_sl = (60.0 if pair == "XAUUSD" else 18.0) * pip
    max_sl = (350.0 if pair == "XAUUSD" else 65.0) * pip

    last_exit = -1

    for i in range(50, n):
        if i <= last_exit:
            continue

        row = df.iloc[i]
        entry_time = row['time_dt']
        if not (6 <= entry_time.hour <= 18):
            continue

        prev = df.iloc[i - 1]
        bull = (row['close'] > row['ema50']) and (row['ema20'] > row['ema50']) and (row['ema20_slope'] > 0)
        bear = (row['close'] < row['ema50']) and (row['ema20'] < row['ema50']) and (row['ema20_slope'] < 0)

        long_break = (row['close'] > row['donch_high']) and (prev['close'] <= prev['donch_high']) and bull and (45 <= row['rsi'] <= 75)
        short_break = (row['close'] < row['donch_low']) and (prev['close'] >= prev['donch_low']) and bear and (25 <= row['rsi'] <= 55)

        if not (long_break or short_break):
            continue

        is_long = bool(long_break)
        entry = float(row['close'])

        if is_long:
            ob_low = row['low']
            for k in range(i - 1, max(0, i - 10), -1):
                if df.iloc[k]['close'] < df.iloc[k]['open']:
                    ob_low = df.iloc[k]['low']
                    break
            sl_dist = float(max(min_sl, min(max_sl, entry - (ob_low - (0.50 * row['atr'])))))
            initial_sl = float(entry - sl_dist)
            tp, rr_val = find_strong_pullback_liquidity(highs, lows, atrs, n, i, entry, sl_dist, is_long=True)
        else:
            ob_high = row['high']
            for k in range(i - 1, max(0, i - 10), -1):
                if df.iloc[k]['close'] > df.iloc[k]['open']:
                    ob_high = df.iloc[k]['high']
                    break
            sl_dist = float(max(min_sl, min(max_sl, (ob_high + (0.50 * row['atr'])) - entry)))
            initial_sl = float(entry + sl_dist)
            tp, rr_val = find_strong_pullback_liquidity(highs, lows, atrs, n, i, entry, sl_dist, is_long=False)

        exit_r = None
        exit_time = None

        for j in range(i + 1, min(i + 200, n)):
            b = df.iloc[j]
            h_held = (b['time_dt'] - entry_time).total_seconds() / 3600.0

            hit_sl = (b['low'] <= initial_sl) if is_long else (b['high'] >= initial_sl)
            hit_tp = (b['high'] >= tp) if is_long else (b['low'] <= tp)

            if hit_tp and hit_sl:
                hit_tp = False

            if hit_tp:
                exit_r = rr_val
                exit_time = b['time_dt']
                last_exit = j
                break
            elif hit_sl:
                exit_r = -1.0
                exit_time = b['time_dt']
                last_exit = j
                break

            if h_held >= 24.0:
                ema_cross = (b['close'] < ema20_vals[j]) if is_long else (b['close'] > ema20_vals[j])
                if ema_cross:
                    exit_price = b['close']
                    exit_r = ((exit_price - entry) / sl_dist) if is_long else ((entry - exit_price) / sl_dist)
                    exit_time = b['time_dt']
                    last_exit = j
                    break

        if exit_r is not None:
            all_trades.append({
                'pair': pair,
                'entry_time': entry_time,
                'exit_time': exit_time,
                'exit_r': exit_r,
                'dur_h': (exit_time - entry_time).total_seconds() / 3600.0
            })

all_trades = sorted(all_trades, key=lambda t: t['entry_time'])
print(f"Total historical trades captured: {len(all_trades)}")

# Let's run a rolling simulation starting across different months in the 2-year dataset
# to see the average time to:
# 1. Complete Phase 1 (8% = +8.0R at 1% risk)
# 2. Complete Phase 2 (5% = +5.0R at 1% risk)
# 3. Reach $1,250 profit in Funded Stage (+25.0R at 1% risk) for $1,000 payout (80% split)

results = []

# Test starting at intervals of 30 trades across the 2 years
for start_idx in range(0, len(all_trades) - 100, 20):
    start_time = all_trades[start_idx]['entry_time']
    
    # Phase 1: Target = +8.0R
    p1_r = 0.0
    p1_time = None
    p1_idx = None
    p1_peak = 0.0
    p1_max_dd = 0.0
    breached = False
    
    for i in range(start_idx, len(all_trades)):
        t = all_trades[i]
        p1_r += t['exit_r']
        if p1_r > p1_peak:
            p1_peak = p1_r
        dd = p1_peak - p1_r
        if dd > p1_max_dd:
            p1_max_dd = dd
        if dd >= 7.0: # 7% max drawdown breach
            breached = True
            break
        if p1_r >= 8.0:
            p1_time = t['exit_time']
            p1_idx = i
            break
            
    if breached or p1_idx is None:
        continue
        
    p1_days = (p1_time - start_time).total_seconds() / 86400.0
    
    # Phase 2: Target = +5.0R
    p2_r = 0.0
    p2_time = None
    p2_idx = None
    p2_peak = 0.0
    p2_max_dd = 0.0
    p2_start_time = all_trades[p1_idx + 1]['entry_time'] if p1_idx + 1 < len(all_trades) else p1_time
    
    for i in range(p1_idx + 1, len(all_trades)):
        t = all_trades[i]
        p2_r += t['exit_r']
        if p2_r > p2_peak:
            p2_peak = p2_r
        dd = p2_peak - p2_r
        if dd > p2_max_dd:
            p2_max_dd = dd
        if dd >= 7.0:
            breached = True
            break
        if p2_r >= 5.0:
            p2_time = t['exit_time']
            p2_idx = i
            break
            
    if breached or p2_idx is None:
        continue
        
    p2_days = (p2_time - p2_start_time).total_seconds() / 86400.0
    
    # Funded Stage: Target = +25.0R ($1,250 profit -> $1,000 payout)
    funded_r = 0.0
    funded_time = None
    funded_peak = 0.0
    funded_max_dd = 0.0
    funded_start_time = all_trades[p2_idx + 1]['entry_time'] if p2_idx + 1 < len(all_trades) else p2_time
    
    for i in range(p2_idx + 1, len(all_trades)):
        t = all_trades[i]
        funded_r += t['exit_r']
        if funded_r > funded_peak:
            funded_peak = funded_r
        dd = funded_peak - funded_r
        if dd > funded_max_dd:
            funded_max_dd = dd
        if dd >= 7.0:
            breached = True
            break
        if funded_r >= 25.0:
            funded_time = t['exit_time']
            break
            
    funded_days = (funded_time - funded_start_time).total_seconds() / 86400.0 if funded_time else None
    
    results.append({
        'start_time': start_time,
        'p1_days': p1_days,
        'p2_days': p2_days,
        'funded_days': funded_days,
        'breached': breached
    })

print(f"Total simulated cycles: {len(results)}")
valid_cycles = [r for r in results if not r['breached']]
print(f"Safe, non-breached cycles: {len(valid_cycles)} / {len(results)} ({len(valid_cycles)/len(results)*100:.1f}%)")

avg_p1_days = np.mean([r['p1_days'] for r in valid_cycles])
median_p1_days = np.median([r['p1_days'] for r in valid_cycles])
avg_p2_days = np.mean([r['p2_days'] for r in valid_cycles])
median_p2_days = np.median([r['p2_days'] for r in valid_cycles])

funded_complete = [r for r in valid_cycles if r['funded_days'] is not None]
avg_funded_days = np.mean([r['funded_days'] for r in funded_complete]) if funded_complete else 0
median_funded_days = np.median([r['funded_days'] for r in funded_complete]) if funded_complete else 0

print("=" * 80)
print("HISTORICAL TIMELINE ANALYSIS (1.0% RISK PER TRADE)")
print("=" * 80)
print(f"Phase 1 (8% / $400):  Average: {avg_p1_days:.1f} days | Median: {median_p1_days:.1f} days (Range: {min(r['p1_days'] for r in valid_cycles):.1f} to {max(r['p1_days'] for r in valid_cycles):.1f} days)")
print(f"Phase 2 (5% / $250):  Average: {avg_p2_days:.1f} days | Median: {median_p2_days:.1f} days (Range: {min(r['p2_days'] for r in valid_cycles):.1f} to {max(r['p2_days'] for r in valid_cycles):.1f} days)")
print(f"Total Challenge Time: Average: {avg_p1_days + avg_p2_days:.1f} days | Median: {median_p1_days + median_p2_days:.1f} days (~4 to 6 weeks)")
print(f"Funded to $1,000 Payout ($1,250 profit / +25%): Average: {avg_funded_days:.1f} days | Median: {median_funded_days:.1f} days (~2.5 to 3.5 months)")
print(f"Grand Total (Day 1 of Challenge to First $1,000 in your bank): ~95 to 135 calendar days (~3 to 4.5 months)")
