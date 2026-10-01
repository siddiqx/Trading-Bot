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

print("Precomputing trade setups across Core Alpha Triad...")
raw_setups = []

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

    for i in range(50, n - 200):
        row = df.iloc[i]
        entry_time = row['time_dt']
        hour = entry_time.hour
        if not (6 <= hour <= 18):
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

        # Cache forward bars (up to 150 bars)
        forward_bars = []
        for j in range(i + 1, min(i + 150, n)):
            b = df.iloc[j]
            h_held = (b['time_dt'] - entry_time).total_seconds() / 3600.0
            forward_bars.append({
                'idx': j,
                'time_dt': b['time_dt'],
                'h_held': h_held,
                'high': b['high'],
                'low': b['low'],
                'close': b['close'],
                'ema20': ema20_vals[j]
            })

        raw_setups.append({
            'pair': pair,
            'entry_idx': i,
            'entry_time': entry_time,
            'is_long': is_long,
            'entry': entry,
            'sl_dist': sl_dist,
            'initial_sl': initial_sl,
            'tp': tp,
            'rr_val': rr_val,
            'forward_bars': forward_bars
        })

print(f"Total raw setups precomputed: {len(raw_setups)}")

def simulate_strategy(setups, be_threshold=None, ema_exit_hours=None, max_hold_hours=None, period="last_month"):
    trades = []
    # Track last exit index per pair to enforce single active trade per pair
    last_exit_idx = {p: -1 for p in PAIRS}

    max_dt = max(s['entry_time'] for s in setups)
    one_month_ago = max_dt - pd.Timedelta(days=30)

    # Sort chronologically
    sorted_setups = sorted(setups, key=lambda s: s['entry_time'])

    for s in sorted_setups:
        pair = s['pair']
        if s['entry_idx'] <= last_exit_idx[pair]:
            continue

        entry_time = s['entry_time']
        is_long = s['is_long']
        entry = s['entry']
        sl_dist = s['sl_dist']
        current_sl = s['initial_sl']
        tp = s['tp']
        rr_val = s['rr_val']

        exit_r = None
        exit_dur = None
        exit_reason = None
        be_active = False

        for b in s['forward_bars']:
            h_held = b['h_held']

            # Breakeven trigger
            if be_threshold is not None and not be_active:
                mfe = ((b['high'] - entry) / sl_dist) if is_long else ((entry - b['low']) / sl_dist)
                if mfe >= be_threshold:
                    be_active = True
                    current_sl = entry + (0.05 * sl_dist) if is_long else entry - (0.05 * sl_dist)

            hit_sl = (b['low'] <= current_sl) if is_long else (b['high'] >= current_sl)
            hit_tp = (b['high'] >= tp) if is_long else (b['low'] <= tp)

            if hit_sl and hit_tp:
                hit_tp = False

            if hit_tp:
                exit_r = rr_val
                exit_dur = h_held
                last_exit_idx[pair] = b['idx']
                exit_reason = "TP"
                break
            elif hit_sl:
                exit_r = 0.05 if be_active else -1.0
                exit_dur = h_held
                last_exit_idx[pair] = b['idx']
                exit_reason = "BE" if be_active else "SL"
                break

            # EMA invalidation exit
            if ema_exit_hours is not None and h_held >= ema_exit_hours:
                ema_cross = (b['close'] < b['ema20']) if is_long else (b['close'] > b['ema20'])
                if ema_cross:
                    exit_price = b['close']
                    exit_r = ((exit_price - entry) / sl_dist) if is_long else ((entry - exit_price) / sl_dist)
                    exit_dur = h_held
                    last_exit_idx[pair] = b['idx']
                    exit_reason = "EMA_EXIT"
                    break

            # Max hold time exit
            if max_hold_hours is not None and h_held >= max_hold_hours:
                exit_price = b['close']
                exit_r = ((exit_price - entry) / sl_dist) if is_long else ((entry - exit_price) / sl_dist)
                exit_dur = h_held
                last_exit_idx[pair] = b['idx']
                exit_reason = "TIME_EXIT"
                break

        if exit_r is not None:
            if period == "last_month" and entry_time < one_month_ago:
                continue
            trades.append({
                'pair': pair,
                'entry_time': entry_time,
                'exit_r': exit_r,
                'dur_h': exit_dur,
                'reason': exit_reason
            })

    if not trades:
        return 0, 0, 0, 0, 0, 0

    net_r = sum(t['exit_r'] for t in trades)
    wins = [t for t in trades if t['exit_r'] > 0.05]
    be_cnt = len([t for t in trades if 0 <= t['exit_r'] <= 0.05])
    losses = [t for t in trades if t['exit_r'] < 0]
    total = len(trades)
    win_rate = len(wins) / total * 100.0
    avg_dur = float(np.mean([t['dur_h'] for t in trades]))
    loss_dur = float(np.mean([t['dur_h'] for t in losses])) if losses else 0.0

    equity = 100.0
    peak = 100.0
    max_dd = 0.0
    for t in trades:
        equity += t['exit_r'] * 0.50
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100.0
        if dd > max_dd:
            max_dd = dd

    return total, win_rate, net_r, max_dd, avg_dur, loss_dur, be_cnt

configs = [
    ("Baseline (No BE, No Time Exit)", None, None, None),
    ("BE @ +1.0R (Move SL to +0.05R)", 1.0, None, None),
    ("BE @ +1.2R (Move SL to +0.05R)", 1.2, None, None),
    ("BE @ +1.0R + EMA Exit after 18h", 1.0, 18, None),
    ("BE @ +1.0R + EMA Exit after 24h", 1.0, 24, None),
    ("BE @ +1.0R + Max Hold 36h", 1.0, None, 36),
    ("BE @ +1.0R + Max Hold 48h", 1.0, None, 48),
    ("EMA Exit after 24h (No BE)", None, 24, None),
    ("Max Hold 36h (No BE)", None, None, 36),
]

print("\n" + "=" * 115)
print("AUDIT: EXIT OPTIMIZATIONS TEST ON LAST MONTH (Aug 26 - Sep 25, 2026)")
print("=" * 115)
for name, be, ema, mx in configs:
    tot, wr, net_r, max_dd, avg_d, loss_d, be_c = simulate_strategy(raw_setups, be, ema, mx, "last_month")
    print(f"{name:<34} | Trades: {tot:>2} (BE:{be_c:>2}) | WR: {wr:>4.1f}% | Net R: {net_r:>+5.2f}R | Max DD: {max_dd:>4.2f}% | Avg: {avg_d:>4.1f}h | Loss: {loss_d:>4.1f}h")

print("\n" + "=" * 115)
print("AUDIT: EXIT OPTIMIZATIONS TEST ON FULL 2-YEAR DATASET (2024 - 2026)")
print("=" * 115)
for name, be, ema, mx in configs:
    tot, wr, net_r, max_dd, avg_d, loss_d, be_c = simulate_strategy(raw_setups, be, ema, mx, "all")
    print(f"{name:<34} | Trades: {tot:>3} (BE:{be_c:>2}) | WR: {wr:>4.1f}% | Net R: {net_r:>+5.1f}R | Max DD: {max_dd:>4.2f}% | Avg: {avg_d:>4.1f}h | Loss: {loss_d:>4.1f}h")
