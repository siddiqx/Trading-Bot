import pickle
import pandas as pd
import numpy as np

def run_ict_audit():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        data = pickle.load(f)

    PAIRS = ["XAUUSD", "EURUSD", "USDCAD"]
    PIP_SIZES = {
        "EURUSD": 0.0001,
        "USDCAD": 0.0001,
        "XAUUSD": 0.10
    }

    print("=" * 110)
    print("ICT LIQUIDITY AUDIT: BSL (BUY-SIDE LIQUIDITY) & SSL (SELL-SIDE LIQUIDITY) vs ARBITRARY FIXED TP")
    print("=" * 110)

    for target_mode in ["FIXED_1_75R", "ICT_LIQUIDITY_POOL", "ICT_LIQUIDITY_WITH_MIN_RR"]:
        all_trades = []

        for pair in PAIRS:
            df = data[pair].copy()
            df['time_dt'] = pd.to_datetime(df['time_dt'])
            df.sort_values('time_dt', inplace=True)
            df.reset_index(drop=True, inplace=True)
            pip = PIP_SIZES[pair]

            # Fast Vectorized Fractals for Swing Highs (BSL) and Swing Lows (SSL)
            highs = df['high'].values
            lows = df['low'].values
            closes = df['close'].values
            n = len(df)

            # 5-bar swing detection
            is_swing_high = np.zeros(n, dtype=bool)
            is_swing_low = np.zeros(n, dtype=bool)
            for k in range(3, n - 3):
                if (highs[k] >= highs[k-1] and highs[k] >= highs[k-2] and highs[k] >= highs[k-3] and
                    highs[k] >= highs[k+1] and highs[k] >= highs[k+2] and highs[k] >= highs[k+3]):
                    is_swing_high[k] = True
                if (lows[k] <= lows[k-1] and lows[k] <= lows[k-2] and lows[k] <= lows[k-3] and
                    lows[k] <= lows[k+1] and lows[k] <= lows[k+2] and lows[k] <= lows[k+3]):
                    is_swing_low[k] = True

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

            min_sl = (60.0 if pair == "XAUUSD" else 18.0) * pip
            max_sl = (350.0 if pair == "XAUUSD" else 65.0) * pip

            last_exit_idx = -1

            for i in range(50, n):
                if i <= last_exit_idx:
                    continue

                row = df.iloc[i]
                hour = row['time_dt'].hour
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
                entry = row['close']

                # Stop Loss based on Origin Order Block
                if is_long:
                    ob_low = row['low']
                    for k in range(i - 1, max(0, i - 10), -1):
                        c = df.iloc[k]
                        if c['close'] < c['open']:
                            ob_low = c['low']
                            break
                    sl_dist = max(min_sl, min(max_sl, entry - (ob_low - (0.50 * row['atr']))))
                    sl = entry - sl_dist
                else:
                    ob_high = row['high']
                    for k in range(i - 1, max(0, i - 10), -1):
                        c = df.iloc[k]
                        if c['close'] > c['open']:
                            ob_high = c['high']
                            break
                    sl_dist = max(min_sl, min(max_sl, (ob_high + (0.50 * row['atr'])) - entry))
                    sl = entry + sl_dist

                # Target Calculation
                if target_mode == "FIXED_1_75R":
                    tp = entry + (sl_dist * 1.75) if is_long else entry - (sl_dist * 1.75)
                    tp_r = 1.75
                elif target_mode in ["ICT_LIQUIDITY_POOL", "ICT_LIQUIDITY_WITH_MIN_RR"]:
                    # Find next un-swept liquidity pool in lookback
                    if is_long:
                        # BSL: Search for previous swing highs above entry
                        bsl_candidates = []
                        for lookback_k in range(i - 1, max(0, i - 150), -1):
                            if is_swing_high[lookback_k] and highs[lookback_k] > entry + (sl_dist * 0.5):
                                bsl_candidates.append(highs[lookback_k])
                        if bsl_candidates:
                            # Target the nearest major BSL pool
                            tp = min(bsl_candidates)
                            tp_r = (tp - entry) / sl_dist
                        else:
                            # Default to 1.75R if no overhead pool within lookback
                            tp = entry + (sl_dist * 1.75)
                            tp_r = 1.75
                    else:
                        # SSL: Search for previous swing lows below entry
                        ssl_candidates = []
                        for lookback_k in range(i - 1, max(0, i - 150), -1):
                            if is_swing_low[lookback_k] and lows[lookback_k] < entry - (sl_dist * 0.5):
                                ssl_candidates.append(lows[lookback_k])
                        if ssl_candidates:
                            # Target the nearest major SSL pool
                            tp = max(ssl_candidates)
                            tp_r = (entry - tp) / sl_dist
                        else:
                            tp = entry - (sl_dist * 1.75)
                            tp_r = 1.75

                    if target_mode == "ICT_LIQUIDITY_WITH_MIN_RR":
                        # If the nearest liquidity pool offers < 1.25R, skip the trade (TRAP: unfavorable R:R into opposing liquidity)
                        if tp_r < 1.25:
                            continue
                        # Cap max target at 2.5R for realistic intraday delivery
                        if tp_r > 2.50:
                            tp_r = 2.50
                            tp = entry + (sl_dist * 2.50) if is_long else entry - (sl_dist * 2.50)

                # Forward simulate trade
                exit_r = None
                for j in range(i + 1, min(i + 150, n)):
                    b = df.iloc[j]
                    hit_sl = (b['low'] <= sl) if is_long else (b['high'] >= sl)
                    hit_tp = (b['high'] >= tp) if is_long else (b['low'] <= tp)

                    if hit_sl and hit_tp:
                        hit_tp = False

                    if hit_tp:
                        exit_r = tp_r
                        last_exit_idx = j
                        break
                    elif hit_sl:
                        exit_r = -1.0
                        last_exit_idx = j
                        break

                if exit_r is not None:
                    all_trades.append({
                        'pair': pair,
                        'r': exit_r
                    })

        r_vals = [t['r'] for t in all_trades]
        wins = [r for r in r_vals if r > 0]
        losses = [r for r in r_vals if r < 0]
        tot_r = sum(r_vals)
        wr = (len(wins) / len(r_vals) * 100) if r_vals else 0
        pf = (sum(wins) / abs(sum(losses))) if losses else 0
        cum = np.cumsum(r_vals)
        dd_r = np.max(np.maximum.accumulate(cum) - cum) if len(cum) else 0

        print(f"\nMode: {target_mode}")
        print(f"  Trades: {len(all_trades):<4} | Win Rate: {wr:>5.1f}% | Net Return: {tot_r:>6.1f} R | Profit Factor: {pf:>4.2f}")
        print(f"  Max Drawdown (1.0% risk): {dd_r:>5.1f}% | Max Drawdown (0.5% risk): {dd_r*0.5:>4.1f}%")

if __name__ == '__main__':
    run_ict_audit()
