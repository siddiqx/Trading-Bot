import pickle
import pandas as pd
import numpy as np

def run_pullback_liquidity_research():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        data = pickle.load(f)

    PAIRS = ["XAUUSD", "EURUSD", "USDCAD"]
    PIP_SIZES = {
        "EURUSD": 0.0001,
        "USDCAD": 0.0001,
        "XAUUSD": 0.10
    }

    print("=" * 115)
    print("QUANTITATIVE AUDIT: VALID STRONG BSL & SSL ANCHORED TO NORMAL PULLBACK ZONES")
    print("=" * 115)

    for time_scope in ["2_YEAR_HISTORICAL", "LAST_MONTH"]:
        print(f"\n>>> TIME SCOPE: {time_scope} <<<")
        for mode in ["FIXED_1_75R", "STRONG_PULLBACK_BSL_SSL"]:
            all_trades = []

            for pair in PAIRS:
                df = data[pair].copy()
                df['time_dt'] = pd.to_datetime(df['time_dt'])
                df.sort_values('time_dt', inplace=True)
                df.reset_index(drop=True, inplace=True)
                pip = PIP_SIZES[pair]

                # Filter time scope
                if time_scope == "LAST_MONTH":
                    max_dt = df['time_dt'].max()
                    start_dt = max_dt - pd.Timedelta(days=30)
                    df = df[df['time_dt'] >= start_dt].copy()
                    df.reset_index(drop=True, inplace=True)

                highs = df['high'].values
                lows = df['low'].values
                closes = df['close'].values
                n = len(df)
                if n < 60:
                    continue

                # Technical Indicators
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

                # Vectorized Strong BSL and SSL detection anchored to pullback depth >= 1.0 * ATR
                is_strong_bsl = np.zeros(n, dtype=bool)
                is_strong_ssl = np.zeros(n, dtype=bool)

                for k in range(3, n - 3):
                    atr_k = atrs[k]
                    # Strong BSL: swing high with multi-bar clearance and minimum pullback depth
                    if (highs[k] >= highs[k-1] and highs[k] >= highs[k-2] and highs[k] >= highs[k-3] and
                        highs[k] >= highs[k+1] and highs[k] >= highs[k+2] and highs[k] >= highs[k+3]):
                        # Check pullback depth after swing high (at least 1.0 * ATR retracement)
                        look_ahead = min(n, k + 15)
                        depth = highs[k] - np.min(lows[k:look_ahead])
                        if depth >= 0.8 * atr_k:
                            is_strong_bsl[k] = True

                    # Strong SSL: swing low with multi-bar clearance and minimum pullback depth
                    if (lows[k] <= lows[k-1] and lows[k] <= lows[k-2] and lows[k] <= lows[k-3] and
                        lows[k] <= lows[k+1] and lows[k] <= lows[k+2] and lows[k] <= lows[k+3]):
                        look_ahead = min(n, k + 15)
                        depth = np.max(highs[k:look_ahead]) - lows[k]
                        if depth >= 0.8 * atr_k:
                            is_strong_ssl[k] = True

                last_exit = -1
                pair_trades = []

                for i in range(50, n):
                    if i <= last_exit:
                        continue

                    row = df.iloc[i]
                    if not (6 <= row['time_dt'].hour <= 18):
                        continue

                    prev = df.iloc[i - 1]
                    bull = (row['close'] > row['ema50']) and (row['ema20'] > row['ema50']) and (row['ema20_slope'] > 0)
                    bear = (row['close'] < row['ema50']) and (row['ema20'] < row['ema50']) and (row['ema20_slope'] < 0)

                    long_break = (row['close'] > row['donch_high']) and (prev['close'] <= prev['donch_high']) and bull and (45 <= row['rsi'] <= 75)
                    short_break = (row['close'] < row['donch_low']) and (prev['close'] >= prev['donch_low']) and bear and (25 <= row['rsi'] <= 55)

                    if not (long_break or short_break):
                        continue

                    is_long = long_break
                    entry = row['close']

                    if is_long:
                        ob_low = row['low']
                        for k in range(i - 1, max(0, i - 10), -1):
                            if df.iloc[k]['close'] < df.iloc[k]['open']:
                                ob_low = df.iloc[k]['low']
                                break
                        sl_dist = max(min_sl, min(max_sl, entry - (ob_low - (0.50 * row['atr']))))
                        sl = entry - sl_dist

                        if mode == "FIXED_1_75R":
                            tp = entry + (sl_dist * 1.75)
                            tp_r = 1.75
                        else:
                            # Strong BSL from pullback zone
                            bsl_pools = []
                            for k in range(i - 1, max(0, i - 120), -1):
                                if is_strong_bsl[k] and highs[k] >= entry + (sl_dist * 1.0):
                                    bsl_pools.append(highs[k])
                            if bsl_pools:
                                tp = min(bsl_pools)
                                tp_r = (tp - entry) / sl_dist
                                if tp_r > 2.5:
                                    tp_r = 2.5
                                    tp = entry + (sl_dist * 2.5)
                            else:
                                tp = entry + (sl_dist * 1.75)
                                tp_r = 1.75
                    else:
                        ob_high = row['high']
                        for k in range(i - 1, max(0, i - 10), -1):
                            if df.iloc[k]['close'] > df.iloc[k]['open']:
                                ob_high = df.iloc[k]['high']
                                break
                        sl_dist = max(min_sl, min(max_sl, (ob_high + (0.50 * row['atr'])) - entry))
                        sl = entry + sl_dist

                        if mode == "FIXED_1_75R":
                            tp = entry - (sl_dist * 1.75)
                            tp_r = 1.75
                        else:
                            # Strong SSL from pullback zone
                            ssl_pools = []
                            for k in range(i - 1, max(0, i - 120), -1):
                                if is_strong_ssl[k] and lows[k] <= entry - (sl_dist * 1.0):
                                    ssl_pools.append(lows[k])
                            if ssl_pools:
                                tp = max(ssl_pools)
                                tp_r = (entry - tp) / sl_dist
                                if tp_r > 2.5:
                                    tp_r = 2.5
                                    tp = entry - (sl_dist * 2.5)
                            else:
                                tp = entry - (sl_dist * 1.75)
                                tp_r = 1.75

                    exit_r = None
                    exit_idx = -1
                    for j in range(i + 1, min(i + 150, n)):
                        b = df.iloc[j]
                        hit_sl = (b['low'] <= sl) if is_long else (b['high'] >= sl)
                        hit_tp = (b['high'] >= tp) if is_long else (b['low'] <= tp)

                        if hit_sl and hit_tp:
                            hit_tp = False

                        if hit_tp:
                            exit_r = tp_r
                            exit_idx = j
                            last_exit = j
                            break
                        elif hit_sl:
                            exit_r = -1.0
                            exit_idx = j
                            last_exit = j
                            break

                    if exit_r is not None:
                        dur_h = (df.iloc[exit_idx]['time_dt'] - row['time_dt']).total_seconds() / 3600.0
                        pair_trades.append({
                            'pair': pair,
                            'entry_time': row['time_dt'],
                            'r': exit_r,
                            'dur_h': dur_h,
                            'pips': (exit_r * sl_dist) / pip
                        })

                all_trades.extend(pair_trades)
                p_r = [t['r'] for t in pair_trades]
                p_w = [r for r in p_r if r > 0]
                p_l = [r for r in p_r if r < 0]
                p_wr = (len(p_w) / len(p_r) * 100) if p_r else 0
                p_tot = sum(p_r)
                p_pf = (sum(p_w) / abs(sum(p_l))) if p_l else 0
                print(f"  {pair:<8} | {mode:<25} | Trades: {len(pair_trades):<3} | WinRate: {p_wr:>5.1f}% | Net R: {p_tot:>6.1f} R | PF: {p_pf:>4.2f}")

            # Portfolio aggregation
            r_vals = [t['r'] for t in all_trades]
            wins = [r for r in r_vals if r > 0]
            losses = [r for r in r_vals if r < 0]
            wr = (len(wins) / len(r_vals) * 100) if r_vals else 0
            tot = sum(r_vals)
            pf = (sum(wins) / abs(sum(losses))) if losses else 0
            cum = np.cumsum(r_vals)
            dd = np.max(np.maximum.accumulate(cum) - cum) if len(cum) else 0
            avg_dur = np.mean([t['dur_h'] for t in all_trades]) if all_trades else 0

            print(f"  --> TOTAL PORTFOLIO | {mode:<25} | Trades: {len(all_trades):<3} | WinRate: {wr:>5.1f}% | Net R: {tot:>6.1f} R | PF: {pf:>4.2f} | Max DD (0.5% risk): {dd*0.5:>4.1f}% | Avg Duration: {avg_dur:.1f}h")

if __name__ == '__main__':
    run_pullback_liquidity_research()
