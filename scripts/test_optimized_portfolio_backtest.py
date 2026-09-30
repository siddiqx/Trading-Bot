import pickle
import pandas as pd
import numpy as np

def run_portfolio_optimization():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        data = pickle.load(f)

    PIP_SIZES = {
        "EURUSD": 0.0001,
        "USDJPY": 0.01,
        "USDCAD": 0.0001,
        "USDCHF": 0.0001,
        "AUDUSD": 0.0001,
        "XAUUSD": 0.10
    }

    # Test different pair combinations and session filters
    experiments = [
        ("A. All 6 Pairs - No Session Filter (Raw Baseline)", ["EURUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD", "XAUUSD"], False, None, 1.75),
        ("B. All 6 Pairs - London/NY Session Only (06-17 UTC)", ["EURUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD", "XAUUSD"], True, None, 1.75),
        ("C. Core Alpha Pairs (XAUUSD + EURUSD + USDCAD) - London/NY", ["XAUUSD", "EURUSD", "USDCAD"], True, None, 1.75),
        ("D. Core Alpha Pairs + Trailing Stop @ +1.2R", ["XAUUSD", "EURUSD", "USDCAD"], True, 1.20, 1.75),
        ("E. Gold-Only Specialist (XAUUSD) - London/NY Only", ["XAUUSD"], True, None, 1.75),
        ("F. Gold + EURUSD Duo - London/NY Only", ["XAUUSD", "EURUSD"], True, None, 1.75),
        ("G. Gold + EURUSD Duo - Trailing Stop @ +1.2R", ["XAUUSD", "EURUSD"], True, 1.20, 1.75),
        ("H. Core Alpha Pairs - BE @ +1.2R (Lock +0.2R)", ["XAUUSD", "EURUSD", "USDCAD"], True, "BE_LOCK_02", 1.75),
    ]

    print("=" * 110)
    print("QUANTITATIVE EXPERIMENT: SOLVING DRAWDOWN (<6-7%) & INTRADAY VELOCITY")
    print("=" * 110)

    for title, pairs, session_filter, trail_rule, tp_ratio in experiments:
        all_setups = []

        for pair in pairs:
            df = data[pair].copy()
            df['time_dt'] = pd.to_datetime(df['time_dt'])
            df.sort_values('time_dt', inplace=True)
            df.reset_index(drop=True, inplace=True)
            pip = PIP_SIZES[pair]

            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['ema20_slope'] = df['ema20'] - df['ema20'].shift(2)
            df['donch_high'] = df['high'].shift(1).rolling(20).max()
            df['donch_low'] = df['low'].shift(1).rolling(20).min()

            tr = pd.concat([
                df['high'] - df['low'],
                (df['high'] - df['close'].shift(1)).abs(),
                (df['low'] - df['close'].shift(1)).abs()
            ], axis=1).max(axis=1)
            df['atr'] = tr.ewm(alpha=1.0/14.0, adjust=False).mean()

            delta = df['close'].diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.ewm(alpha=1.0/14.0, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1.0/14.0, adjust=False).mean()
            rs = avg_gain / (avg_loss + 1e-9)
            df['rsi'] = 100.0 - (100.0 / (1.0 + rs))

            min_sl = (60.0 if pair == "XAUUSD" else 18.0) * pip
            max_sl = (350.0 if pair == "XAUUSD" else 65.0) * pip

            for i in range(50, len(df)):
                row = df.iloc[i]
                prev = df.iloc[i - 1]
                hour = row['time_dt'].hour

                # Session filter: London & NY active volume hours (06:00 to 17:00 UTC)
                if session_filter and not (6 <= hour <= 17):
                    continue

                bullish_trend = (row['close'] > row['ema50']) and (row['ema20'] > row['ema50']) and (row['ema20_slope'] > 0)
                bearish_trend = (row['close'] < row['ema50']) and (row['ema20'] < row['ema50']) and (row['ema20_slope'] < 0)

                rsi_bull = 45.0 <= row['rsi'] <= 75.0
                rsi_bear = 25.0 <= row['rsi'] <= 55.0

                long_break = (row['close'] > row['donch_high']) and (prev['close'] <= prev['donch_high'])
                short_break = (row['close'] < row['donch_low']) and (prev['close'] >= prev['donch_low'])

                if long_break and bullish_trend and rsi_bull:
                    ob_low = row['low']
                    for k in range(i - 1, max(0, i - 10), -1):
                        c = df.iloc[k]
                        if c['close'] < c['open']:
                            ob_low = c['low']
                            break
                    entry = row['close']
                    sl_cand = ob_low - (0.50 * row['atr'])
                    sl_dist = max(min_sl, min(max_sl, entry - sl_cand))
                    sl = entry - sl_dist

                    all_setups.append({
                        'pair': pair,
                        'direction': 'LONG',
                        'entry_idx': i,
                        'entry_time': row['time_dt'],
                        'entry': entry,
                        'sl': sl,
                        'sl_dist': sl_dist,
                        'df': df
                    })

                elif short_break and bearish_trend and rsi_bear:
                    ob_high = row['high']
                    for k in range(i - 1, max(0, i - 10), -1):
                        c = df.iloc[k]
                        if c['close'] > c['open']:
                            ob_high = c['high']
                            break
                    entry = row['close']
                    sl_cand = ob_high + (0.50 * row['atr'])
                    sl_dist = max(min_sl, min(max_sl, sl_cand - entry))
                    sl = entry + sl_dist

                    all_setups.append({
                        'pair': pair,
                        'direction': 'SHORT',
                        'entry_idx': i,
                        'entry_time': row['time_dt'],
                        'entry': entry,
                        'sl': sl,
                        'sl_dist': sl_dist,
                        'df': df
                    })

        # Run portfolio simulation with single-trade per pair lock
        sorted_setups = sorted(all_setups, key=lambda x: x['entry_time'])
        pair_lock = {}
        executed = []

        for s in sorted_setups:
            p = s['pair']
            t_entry = s['entry_time']
            if p in pair_lock and pair_lock[p] > t_entry:
                continue

            df = s['df']
            idx = s['entry_idx']
            entry = s['entry']
            sl = s['sl']
            sl_dist = s['sl_dist']
            is_long = (s['direction'] == 'LONG')
            tp = entry + (sl_dist * tp_ratio) if is_long else entry - (sl_dist * tp_ratio)

            curr_sl = sl
            exit_r = None
            exit_time = None
            max_mfe = 0.0

            for j in range(idx + 1, min(idx + 120, len(df))):
                bar = df.iloc[j]
                mfe = ((bar['high'] - entry) / sl_dist) if is_long else ((entry - bar['low']) / sl_dist)
                if mfe > max_mfe:
                    max_mfe = mfe

                # Trailing / BE logic
                if trail_rule == 1.20:
                    # If price hits +1.2R, trail stop to +0.5R
                    if mfe >= 1.20:
                        locked_sl = entry + (sl_dist * 0.50) if is_long else entry - (sl_dist * 0.50)
                        if is_long:
                            curr_sl = max(curr_sl, locked_sl)
                        else:
                            curr_sl = min(curr_sl, locked_sl)
                elif trail_rule == "BE_LOCK_02":
                    # If price hits +1.2R, move stop to Entry + 0.2R buffer (guaranteed positive exit)
                    if mfe >= 1.20:
                        locked_sl = entry + (sl_dist * 0.20) if is_long else entry - (sl_dist * 0.20)
                        if is_long:
                            curr_sl = max(curr_sl, locked_sl)
                        else:
                            curr_sl = min(curr_sl, locked_sl)

                hit_sl = (bar['low'] <= curr_sl) if is_long else (bar['high'] >= curr_sl)
                hit_tp = (bar['high'] >= tp) if is_long else (bar['low'] <= tp)

                if hit_sl and hit_tp:
                    hit_tp = False

                if hit_sl:
                    if curr_sl == sl:
                        exit_r = -1.00
                    else:
                        exit_r = ((curr_sl - entry) / sl_dist) if is_long else ((entry - curr_sl) / sl_dist)
                    exit_time = bar['time_dt']
                    break
                elif hit_tp:
                    exit_r = tp_ratio
                    exit_time = bar['time_dt']
                    break

            if exit_r is None:
                exit_r = 0.0
                exit_time = df.iloc[-1]['time_dt']

            dur_h = (exit_time - t_entry).total_seconds() / 3600.0
            pair_lock[p] = exit_time
            executed.append({
                'r': exit_r,
                'dur_h': dur_h,
                'mfe': max_mfe
            })

        r_vals = [e['r'] for e in executed]
        tot_r = sum(r_vals)
        wins = [r for r in r_vals if r > 0.05]
        losses = [r for r in r_vals if r < -0.05]
        wr = (len(wins) / (len(wins) + len(losses)) * 100) if (len(wins) + len(losses)) > 0 else 0
        pf = sum(wins) / abs(sum(losses)) if losses else 0
        cum_r = np.cumsum(r_vals)
        peak_r = np.maximum.accumulate(cum_r)
        max_dd_r = np.max(peak_r - cum_r) if len(cum_r) > 0 else 0
        avg_dur = np.mean([e['dur_h'] for e in executed]) if executed else 0

        # Calculate max drawdown at 0.5% risk vs 1.0% risk
        dd_at_half_pct = max_dd_r * 0.5

        print(f"\n{title}")
        print(f"  Trades: {len(executed):<4} | Net Return: {tot_r:>6.1f} R | Win Rate: {wr:>5.1f}% | PF: {pf:>4.2f}")
        print(f"  Max DD (at 1.0% risk): {max_dd_r:>5.1f}% | Max DD (at 0.5% risk): {dd_at_half_pct:>5.1f}%")
        print(f"  Average Holding Time: {avg_dur:>5.1f} hours ({avg_dur/24:.1f} days)")

if __name__ == '__main__':
    run_portfolio_optimization()
