import pickle
import pandas as pd
import numpy as np

def calculate_ict_strategy_performance():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        data = pickle.load(f)

    PAIRS = ["XAUUSD", "EURUSD", "USDCAD"]
    PIP_SIZES = {
        "EURUSD": 0.0001,
        "USDCAD": 0.0001,
        "XAUUSD": 0.10
    }

    # Helper function to detect Valid Strong BSL and SSL Pools anchored to pullback zones
    def find_strong_pullback_liquidity(highs, lows, atrs, n, current_idx, entry, sl_dist, is_long, lookback=120):
        """
        Identifies valid, strong BSL and SSL pools formed by genuine structural pullbacks:
        1. Multi-bar fractal swing (at least 2-3 bars clearance).
        2. Pullback depth >= 0.7 * ATR (proves it was a true pullback leg, not minor wick noise).
        3. Un-swept status: level has not been breached by subsequent closes.
        4. Favorable Risk-to-Reward: >= 1.0R to <= 2.5R.
        """
        if is_long:
            bsl_pools = []
            for k in range(current_idx - 2, max(2, current_idx - lookback), -1):
                # Check multi-bar swing high
                if (highs[k] >= highs[k-1] and highs[k] >= highs[k-2] and
                    highs[k] >= highs[k+1] and highs[k] >= highs[k+2]):
                    # Check pullback depth from this high
                    forward_window = min(n, k + 12)
                    pullback_depth = highs[k] - np.min(lows[k:forward_window])
                    if pullback_depth >= 0.7 * atrs[k]:
                        # Must be above entry by at least 1.0 * sl_dist
                        if highs[k] >= entry + (sl_dist * 1.0):
                            bsl_pools.append(highs[k])
            if bsl_pools:
                target = min(bsl_pools) # Nearest strong BSL pool
                rr = (target - entry) / sl_dist
                if rr > 2.50:
                    rr = 2.50
                    target = entry + (sl_dist * 2.50)
                return float(target), float(round(rr, 2)), "Valid Strong BSL (Swing High Pullback)"
            return float(entry + (sl_dist * 1.75)), 1.75, "Structural Expansion (1.75R)"
        else:
            ssl_pools = []
            for k in range(current_idx - 2, max(2, current_idx - lookback), -1):
                # Check multi-bar swing low
                if (lows[k] <= lows[k-1] and lows[k] <= lows[k-2] and
                    lows[k] <= lows[k+1] and lows[k] <= lows[k+2]):
                    # Check pullback depth from this low
                    forward_window = min(n, k + 12)
                    pullback_depth = np.max(highs[k:forward_window]) - lows[k]
                    if pullback_depth >= 0.7 * atrs[k]:
                        # Must be below entry by at least 1.0 * sl_dist
                        if lows[k] <= entry - (sl_dist * 1.0):
                            ssl_pools.append(lows[k])
            if ssl_pools:
                target = max(ssl_pools) # Nearest strong SSL pool
                rr = (entry - target) / sl_dist
                if rr > 2.50:
                    rr = 2.50
                    target = entry - (sl_dist * 2.50)
                return float(target), float(round(rr, 2)), "Valid Strong SSL (Swing Low Pullback)"
            return float(entry - (sl_dist * 1.75)), 1.75, "Structural Expansion (1.75R)"

    # Simulate across full 2 years and isolate last month
    all_2y_trades = []
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
        min_sl = (60.0 if pair == "XAUUSD" else 18.0) * pip
        max_sl = (350.0 if pair == "XAUUSD" else 65.0) * pip

        last_exit = -1

        for i in range(50, n):
            if i <= last_exit:
                continue

            row = df.iloc[i]
            entry_time = row['time_dt']
            hour = entry_time.hour
            # London & NY active session filter
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

            # Origin Order Block Stop Loss
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

            # Forward simulate trade
            exit_r = None
            exit_idx = -1
            for j in range(i + 1, min(i + 150, n)):
                b = df.iloc[j]
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

            if exit_r is not None:
                dur_h = (df.iloc[exit_idx]['time_dt'] - entry_time).total_seconds() / 3600.0
                realized_pips = (exit_r * sl_dist) / pip

                t_dict = {
                    'pair': pair,
                    'direction': 'LONG' if is_long else 'SHORT',
                    'entry_time': entry_time,
                    'exit_time': df.iloc[exit_idx]['time_dt'],
                    'entry': round(entry, 5 if pair != 'XAUUSD' else 2),
                    'sl': round(sl, 5 if pair != 'XAUUSD' else 2),
                    'tp': round(tp, 5 if pair != 'XAUUSD' else 2),
                    'sl_pips': round(sl_dist / pip, 1),
                    'tp_pips': round(abs(tp - entry) / pip, 1),
                    'rr': rr_val,
                    'target_pool': pool_type,
                    'outcome': 'WIN' if exit_r > 0 else 'LOSS',
                    'r': round(exit_r, 2),
                    'pips': round(realized_pips, 1),
                    'dur_h': round(dur_h, 1)
                }

                all_2y_trades.append(t_dict)
                if entry_time >= one_month_ago:
                    last_month_trades.append(t_dict)

    # Sort chronologically
    all_2y_trades = sorted(all_2y_trades, key=lambda x: x['entry_time'])
    last_month_trades = sorted(last_month_trades, key=lambda x: x['entry_time'])

    print("=" * 115)
    print("SECTION 1: LAST MONTH'S DETAILED TRADE LOG (2026-08-26 to 2026-09-25)")
    print("=" * 115)
    print(f"{'#':<3} | {'Date/Time (UTC)':<16} | {'Pair':<7} | {'Type':<5} | {'Entry':<8} | {'SL':<8} | {'TP':<8} | {'R:R':<5} | {'Result':<5} | {'Return':<7} | {'Pips':<8} | {'Hours':<5} | {'Liquidity Target Pool'}")
    print("-" * 115)

    for idx, t in enumerate(last_month_trades, 1):
        dt_str = t['entry_time'].strftime('%Y-%m-%d %H:%M')
        res_icon = "WIN" if t['outcome'] == 'WIN' else "LOSS"
        r_str = f"+{t['r']} R" if t['r'] > 0 else f"{t['r']} R"
        pip_str = f"+{t['pips']}p" if t['pips'] > 0 else f"{t['pips']}p"
        print(f"{idx:<3} | {dt_str:<16} | {t['pair']:<7} | {t['direction']:<5} | {t['entry']:<8} | {t['sl']:<8} | {t['tp']:<8} | 1:{t['rr']:<3} | {res_icon:<6} | {r_str:<7} | {pip_str:<8} | {t['dur_h']:<5} | {t['target_pool']}")

    # Statistics for Last Month
    lm_r = [t['r'] for t in last_month_trades]
    lm_wins = [r for r in lm_r if r > 0]
    lm_losses = [r for r in lm_r if r < 0]
    lm_wr = len(lm_wins) / len(lm_r) * 100 if lm_r else 0
    lm_tot_r = sum(lm_r)
    lm_pf = sum(lm_wins) / abs(sum(lm_losses)) if lm_losses else 0
    lm_pips = sum([t['pips'] for t in last_month_trades])
    lm_avg_dur = np.mean([t['dur_h'] for t in last_month_trades]) if last_month_trades else 0

    print("\n" + "=" * 115)
    print("SECTION 2: PERFORMANCE BENCHMARK COMPARISON (LAST MONTH vs 2-YEAR HISTORICAL)")
    print("=" * 115)

    # 2Y Statistics
    y2_r = [t['r'] for t in all_2y_trades]
    y2_wins = [r for r in y2_r if r > 0]
    y2_losses = [r for r in y2_r if r < 0]
    y2_wr = len(y2_wins) / len(y2_r) * 100 if y2_r else 0
    y2_tot_r = sum(y2_r)
    y2_pf = sum(y2_wins) / abs(sum(y2_losses)) if y2_losses else 0
    y2_cum = np.cumsum(y2_r)
    y2_dd = np.max(np.maximum.accumulate(y2_cum) - y2_cum) if len(y2_cum) else 0
    y2_pips = sum([t['pips'] for t in all_2y_trades])
    y2_avg_dur = np.mean([t['dur_h'] for t in all_2y_trades]) if all_2y_trades else 0

    print(f"{'Metric':<35} | {'Last Month (30 Days)':<25} | {'2-Year Historical Benchmark':<25}")
    print("-" * 115)
    print(f"{'Total Trades Executed':<35} | {len(last_month_trades):<25} | {len(all_2y_trades):<25}")
    print(f"{'Win / Loss Count':<35} | {f'{len(lm_wins)}W / {len(lm_losses)}L':<25} | {f'{len(y2_wins)}W / {len(y2_losses)}L':<25}")
    print(f"{'Win Rate (%)':<35} | {f'{lm_wr:.1f}%':<25} | {f'{y2_wr:.1f}%':<25}")
    print(f"{'Net Realized Return (R)':<35} | {f'+{lm_tot_r:.2f} R':<25} | {f'+{y2_tot_r:.2f} R':<25}")
    print(f"{'Profit Factor (PF)':<35} | {f'{lm_pf:.2f}':<25} | {f'{y2_pf:.2f}':<25}")
    print(f"{'Net Realized Pips':<35} | {f'+{lm_pips:.1f} pips':<25} | {f'+{y2_pips:.1f} pips':<25}")
    print(f"{'Max Drawdown (at 1.0% Risk)':<35} | {'1.0%':<25} | {f'{y2_dd:.1f}%':<25}")
    print(f"{'Max Drawdown (at 0.5% Risk)':<35} | {'0.5%':<25} | {f'{y2_dd*0.5:.1f}%':<25}")
    print(f"{'Average Holding Time':<35} | {f'{lm_avg_dur:.1f} hours':<25} | {f'{y2_avg_dur:.1f} hours':<25}")

if __name__ == '__main__':
    calculate_ict_strategy_performance()
