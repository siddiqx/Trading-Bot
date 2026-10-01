import pickle
import pandas as pd
import numpy as np

def run_deep_trade_audit():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        data = pickle.load(f)

    PAIRS = ["XAUUSD", "EURUSD", "USDCAD"]
    PIP_SIZES = {
        "EURUSD": 0.0001,
        "USDCAD": 0.0001,
        "XAUUSD": 0.10
    }

    def find_strong_pullback_liquidity(highs, lows, atrs, n, current_idx, entry, sl_dist, is_long, lookback=120):
        if is_long:
            bsl_pools = []
            for k in range(current_idx - 2, max(2, current_idx - lookback), -1):
                if (highs[k] >= highs[k-1] and highs[k] >= highs[k-2] and
                    highs[k] >= highs[k+1] and highs[k] >= highs[k+2]):
                    forward_window = min(n, k + 12)
                    pullback_depth = highs[k] - np.min(lows[k:forward_window])
                    if pullback_depth >= 0.7 * atrs[k]:
                        if highs[k] >= entry + (sl_dist * 1.0):
                            bsl_pools.append(highs[k])
            if bsl_pools:
                target = min(bsl_pools)
                rr = (target - entry) / sl_dist
                if rr > 2.50:
                    rr = 2.50
                    target = entry + (sl_dist * 2.50)
                return float(target), float(round(rr, 2)), "Valid Strong BSL (Swing High Pullback)"
            return float(entry + (sl_dist * 1.75)), 1.75, "Structural Expansion (1.75R)"
        else:
            ssl_pools = []
            for k in range(current_idx - 2, max(2, current_idx - lookback), -1):
                if (lows[k] <= lows[k-1] and lows[k] <= lows[k-2] and
                    lows[k] <= lows[k+1] and lows[k] <= lows[k+2]):
                    forward_window = min(n, k + 12)
                    pullback_depth = np.max(highs[k:forward_window]) - lows[k]
                    if pullback_depth >= 0.7 * atrs[k]:
                        if lows[k] <= entry - (sl_dist * 1.0):
                            ssl_pools.append(lows[k])
            if ssl_pools:
                target = max(ssl_pools)
                rr = (entry - target) / sl_dist
                if rr > 2.50:
                    rr = 2.50
                    target = entry - (sl_dist * 2.50)
                return float(target), float(round(rr, 2)), "Valid Strong SSL (Swing Low Pullback)"
            return float(entry - (sl_dist * 1.75)), 1.75, "Structural Expansion (1.75R)"

    last_month_trades = []

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
        ema50_vals = df['ema50'].values
        min_sl = (60.0 if pair == "XAUUSD" else 18.0) * pip
        max_sl = (350.0 if pair == "XAUUSD" else 65.0) * pip

        last_exit = -1

        for i in range(50, n):
            if i <= last_exit:
                continue

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

            is_long = long_break
            entry = float(row['close'])

            if is_long:
                ob_low = row['low']
                for k in range(i - 1, max(0, i - 10), -1):
                    if df.iloc[k]['close'] < df.iloc[k]['open']:
                        ob_low = df.iloc[k]['low']
                        break
                sl_dist = float(max(min_sl, min(max_sl, entry - (ob_low - (0.50 * row['atr'])))))
                sl = float(entry - sl_dist)
                tp, rr_val, pool_type = find_strong_pullback_liquidity(highs, lows, atrs, n, i, entry, sl_dist, is_long=True)
            else:
                ob_high = row['high']
                for k in range(i - 1, max(0, i - 10), -1):
                    if df.iloc[k]['close'] > df.iloc[k]['open']:
                        ob_high = df.iloc[k]['high']
                        break
                sl_dist = float(max(min_sl, min(max_sl, (ob_high + (0.50 * row['atr'])) - entry)))
                sl = float(entry + sl_dist)
                tp, rr_val, pool_type = find_strong_pullback_liquidity(highs, lows, atrs, n, i, entry, sl_dist, is_long=False)

            exit_r = None
            exit_idx = -1
            max_mfe_r = 0.0
            max_mfe_hour = 0.0
            max_mae_r = 0.0
            first_ema_cross_hour = None

            for j in range(i + 1, min(i + 200, n)):
                b = df.iloc[j]
                h_held = (b['time_dt'] - entry_time).total_seconds() / 3600.0

                # Calculate excursion metrics
                cur_mfe = ((b['high'] - entry) / sl_dist) if is_long else ((entry - b['low']) / sl_dist)
                cur_mae = ((entry - b['low']) / sl_dist) if is_long else ((b['high'] - entry) / sl_dist)
                if cur_mfe > max_mfe_r:
                    max_mfe_r = cur_mfe
                    max_mfe_hour = h_held
                if cur_mae > max_mae_r:
                    max_mae_r = cur_mae

                # Check EMA cross against trend
                if first_ema_cross_hour is None:
                    if is_long and b['close'] < ema20_vals[j]:
                        first_ema_cross_hour = h_held
                    elif (not is_long) and b['close'] > ema20_vals[j]:
                        first_ema_cross_hour = h_held

                hit_sl = (b['low'] <= sl) if is_long else (b['high'] >= sl)
                hit_tp = (b['high'] >= tp) if is_long else (b['low'] <= tp)

                if hit_sl and hit_tp:
                    hit_tp = False

                if hit_tp:
                    exit_r = rr_val
                    exit_idx = j
                    last_exit = j
                    break
                elif hit_sl:
                    exit_r = -1.0
                    exit_idx = j
                    last_exit = j
                    break

            if exit_r is not None and entry_time >= one_month_ago:
                dur_h = (df.iloc[exit_idx]['time_dt'] - entry_time).total_seconds() / 3600.0
                last_month_trades.append({
                    'pair': pair,
                    'direction': 'LONG' if is_long else 'SHORT',
                    'entry_time': entry_time,
                    'outcome': 'WIN' if exit_r > 0 else 'LOSS',
                    'exit_r': exit_r,
                    'dur_h': dur_h,
                    'max_mfe_r': max_mfe_r,
                    'max_mfe_hour': max_mfe_hour,
                    'max_mae_r': max_mae_r,
                    'ema_cross_h': first_ema_cross_hour
                })

    last_month_trades = sorted(last_month_trades, key=lambda x: x['entry_time'])
    wins = [t for t in last_month_trades if t['outcome'] == 'WIN']
    losses = [t for t in last_month_trades if t['outcome'] == 'LOSS']

    print("=" * 115)
    print("DETAILED MFE / MAE & DURATION ANALYSIS OF LAST MONTH'S TRADES")
    print("=" * 115)
    print(f"Total Wins: {len(wins)} | Total Losses: {len(losses)}")
    print(f"Average Duration - WINS:   {np.mean([t['dur_h'] for t in wins]):.1f} hours")
    print(f"Average Duration - LOSSES: {np.mean([t['dur_h'] for t in losses]):.1f} hours")

    print("\n--- WINNING TRADES BREAKDOWN ---")
    for idx, t in enumerate(wins, 1):
        dt_str = t['entry_time'].strftime('%Y-%m-%d %H:%M')
        print(f"Win #{idx:<2} | {dt_str} | {t['pair']:<7} {t['direction']:<5} | Held: {t['dur_h']:>4.1f}h | Max MFE: +{t['max_mfe_r']:.2f}R @ {t['max_mfe_hour']:.1f}h")

    print("\n--- LOSING TRADES BREAKDOWN (SIMILARITIES & ROOT CAUSES) ---")
    for idx, t in enumerate(losses, 1):
        dt_str = t['entry_time'].strftime('%Y-%m-%d %H:%M')
        ema_str = f"EMA Cross: {t['ema_cross_h']:.1f}h" if t['ema_cross_h'] else "No EMA cross"
        print(f"Loss #{idx:<2} | {dt_str} | {t['pair']:<7} {t['direction']:<5} | Held: {t['dur_h']:>5.1f}h | Peak MFE: +{t['max_mfe_r']:.2f}R @ {t['max_mfe_hour']:>4.1f}h | {ema_str}")

if __name__ == '__main__':
    run_deep_trade_audit()
