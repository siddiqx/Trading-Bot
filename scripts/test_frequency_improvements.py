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

def simulate_config(session_hours=(6, 18), forex_donch=20, gold_donch=10, rsi_bounds=((45, 75), (25, 55)), require_slope=True, period="all"):
    trades = []
    
    for pair in PAIRS:
        df = data[pair].copy()
        df['time_dt'] = pd.to_datetime(df['time_dt'])
        df.sort_values('time_dt', inplace=True)
        df.reset_index(drop=True, inplace=True)
        pip = PIP_SIZES[pair]

        max_dt = df['time_dt'].max()
        one_month_ago = max_dt - pd.Timedelta(days=30)

        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        n = len(df)

        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema20_slope'] = df['ema20'] - df['ema20'].shift(2)
        
        donch_len = gold_donch if pair == "XAUUSD" else forex_donch
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
            
            # Session filter check
            if session_hours is not None:
                if not (session_hours[0] <= entry_time.hour <= session_hours[1]):
                    continue

            prev = df.iloc[i - 1]
            
            # Trend confluence
            if require_slope:
                bull = (row['close'] > row['ema50']) and (row['ema20'] > row['ema50']) and (row['ema20_slope'] > 0)
                bear = (row['close'] < row['ema50']) and (row['ema20'] < row['ema50']) and (row['ema20_slope'] < 0)
            else:
                bull = (row['close'] > row['ema50']) and (row['ema20'] > row['ema50'])
                bear = (row['close'] < row['ema50']) and (row['ema20'] < row['ema50'])

            rsi_long_min, rsi_long_max = rsi_bounds[0]
            rsi_short_min, rsi_short_max = rsi_bounds[1]

            long_break = (row['close'] > row['donch_high']) and (prev['close'] <= prev['donch_high']) and bull and (rsi_long_min <= row['rsi'] <= rsi_long_max)
            short_break = (row['close'] < row['donch_low']) and (prev['close'] >= prev['donch_low']) and bear and (rsi_short_min <= row['rsi'] <= rsi_short_max)

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

            for j in range(i + 1, min(i + 200, n)):
                b = df.iloc[j]
                h_held = (b['time_dt'] - entry_time).total_seconds() / 3600.0

                hit_sl = (b['low'] <= initial_sl) if is_long else (b['high'] >= initial_sl)
                hit_tp = (b['high'] >= tp) if is_long else (b['low'] <= tp)

                if hit_tp and hit_sl:
                    hit_tp = False

                if hit_tp:
                    exit_r = rr_val
                    last_exit = j
                    break
                elif hit_sl:
                    exit_r = -1.0
                    last_exit = j
                    break

                # 24h EMA Invalidation Exit
                if h_held >= 24.0:
                    ema_cross = (b['close'] < ema20_vals[j]) if is_long else (b['close'] > ema20_vals[j])
                    if ema_cross:
                        exit_price = b['close']
                        exit_r = ((exit_price - entry) / sl_dist) if is_long else ((entry - exit_price) / sl_dist)
                        last_exit = j
                        break

            if exit_r is not None:
                if period == "last_month" and entry_time < one_month_ago:
                    continue
                trades.append({
                    'pair': pair,
                    'entry_time': entry_time,
                    'exit_r': exit_r
                })

    trades = sorted(trades, key=lambda t: t['entry_time'])
    if not trades:
        return 0, 0.0, 0.0, 0.0, 0.0

    net_r = sum(t['exit_r'] for t in trades)
    wins = [t for t in trades if t['exit_r'] > 0.05]
    wr = len(wins) / len(trades) * 100.0
    
    # Drawdown (at 0.5% risk per trade)
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

    gross_win = sum(t['exit_r'] for t in trades if t['exit_r'] > 0)
    gross_loss = abs(sum(t['exit_r'] for t in trades if t['exit_r'] < 0))
    pf = (gross_win / gross_loss) if gross_loss > 0 else 99.0

    return len(trades), wr, net_r, max_dd, pf

print("=" * 110)
print("TESTING STRATEGY FREQUENCY ADJUSTMENTS")
print("=" * 110)

configs = [
    ("Current Strict: 06-18 UTC, Donch 20/10, RSI 45-75/25-55", (6, 18), 20, 10, ((45, 75), (25, 55)), True),
    ("Extended Session: 05-21 UTC (Frankfurt to NY Close)", (5, 21), 20, 10, ((45, 75), (25, 55)), True),
    ("24/7 All Sessions (00-24 UTC)", None, 20, 10, ((45, 75), (25, 55)), True),
    ("Forex Donch 15 / Gold 10 (Slightly more responsive)", (6, 18), 15, 10, ((45, 75), (25, 55)), True),
    ("Extended 05-21 UTC + Forex Donch 15", (5, 21), 15, 10, ((45, 75), (25, 55)), True),
    ("Wider RSI: Long 40-80, Short 20-60 (06-18 UTC)", (6, 18), 20, 10, ((40, 80), (20, 60)), True),
    ("Optimal Hybrid: 05-21 UTC + Forex Donch 15 + RSI 40-80", (5, 21), 15, 10, ((40, 80), (20, 60)), True),
    ("Relaxed Slope: 05-21 UTC + Donch 15 + No Slope", (5, 21), 15, 10, ((40, 80), (20, 60)), False),
]

print("\n--- LAST MONTH (30 DAYS) PERFORMANCE & FREQUENCY ---")
print(f"{'Configuration':<52} | {'Trades':<6} | {'Win Rate':<8} | {'Net Return':<10} | {'Max DD':<7} | {'PF':<5}")
print("-" * 110)
for name, sess, fd, gd, rsi, slp in configs:
    n_t, wr, net_r, dd, pf = simulate_config(sess, fd, gd, rsi, slp, "last_month")
    print(f"{name:<52} | {n_t:>6} | {wr:>7.1f}% | {net_r:>+9.2f}R | {dd:>6.2f}% | {pf:>4.2f}")

print("\n--- FULL 2-YEAR DATASET (ROBUSTNESS CHECK) ---")
print(f"{'Configuration':<52} | {'Trades':<6} | {'Win Rate':<8} | {'Net Return':<10} | {'Max DD':<7} | {'PF':<5}")
print("-" * 110)
for name, sess, fd, gd, rsi, slp in configs:
    n_t, wr, net_r, dd, pf = simulate_config(sess, fd, gd, rsi, slp, "all")
    print(f"{name:<52} | {n_t:>6} | {wr:>7.1f}% | {net_r:>+9.2f}R | {dd:>6.2f}% | {pf:>4.2f}")
