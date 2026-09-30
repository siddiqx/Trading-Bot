import pickle
import pandas as pd
import numpy as np

def run_simulation():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        data = pickle.load(f)

    PAIRS = ["EURUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD", "XAUUSD"]
    PIP_SIZES = {
        "EURUSD": 0.0001,
        "USDJPY": 0.01,
        "USDCAD": 0.0001,
        "USDCHF": 0.0001,
        "AUDUSD": 0.0001,
        "XAUUSD": 0.10
    }

    # Step 1: Detect all breakout setups using exact market_scanner logic
    all_setups = []

    for pair in PAIRS:
        if pair not in data:
            continue
        df = data[pair].copy()
        df['time_dt'] = pd.to_datetime(df['time_dt'])
        df.sort_values('time_dt', inplace=True)
        df.reset_index(drop=True, inplace=True)

        pip = PIP_SIZES[pair]

        # Indicators
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
                    'pip': pip,
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
                    'pip': pip,
                    'df': df
                })

    print(f"Total raw breakout setups found across 2 years: {len(all_setups)}")

    # Function to simulate a model variant across all setups
    def simulate_model(model_name, tp_ratio=1.75, be_trigger_r=None, partial_tp1_r=None, partial_tp1_pct=0.5, max_hours=None):
        trades = []
        pair_lock = {} # enforce 1 active trade per pair at a time

        # Sort all setups chronologically
        sorted_setups = sorted(all_setups, key=lambda x: x['entry_time'])

        for setup in sorted_setups:
            pair = setup['pair']
            entry_time = setup['entry_time']
            if pair in pair_lock and pair_lock[pair] > entry_time:
                continue # pair is locked

            df = setup['df']
            entry_idx = setup['entry_idx']
            entry = setup['entry']
            sl = setup['sl']
            sl_dist = setup['sl_dist']
            is_long = (setup['direction'] == 'LONG')

            tp = entry + (sl_dist * tp_ratio) if is_long else entry - (sl_dist * tp_ratio)
            be_price = entry + (sl_dist * be_trigger_r) if (be_trigger_r and is_long) else (entry - (sl_dist * be_trigger_r) if be_trigger_r else None)
            tp1_price = entry + (sl_dist * partial_tp1_r) if (partial_tp1_r and is_long) else (entry - (sl_dist * partial_tp1_r) if partial_tp1_r else None)

            current_sl = sl
            tp1_hit = False
            be_active = False

            exit_r = None
            exit_time = None
            exit_reason = None
            max_mfe_r = 0.0

            # Forward check up to 100 bars (100 hours)
            for j in range(entry_idx + 1, min(entry_idx + 120, len(df))):
                bar = df.iloc[j]
                bar_high = bar['high']
                bar_low = bar['low']
                bar_time = bar['time_dt']
                hours_held = (bar_time - entry_time).total_seconds() / 3600.0

                mfe = ((bar_high - entry) / sl_dist) if is_long else ((entry - bar_low) / sl_dist)
                if mfe > max_mfe_r:
                    max_mfe_r = mfe

                # Check partial TP1
                if partial_tp1_r and not tp1_hit:
                    hit_tp1 = (bar_high >= tp1_price) if is_long else (bar_low <= tp1_price)
                    if hit_tp1:
                        tp1_hit = True
                        be_active = True
                        current_sl = entry # move SL of remainder to break-even

                # Check Break-Even trigger
                if be_trigger_r and not be_active:
                    hit_be = (bar_high >= be_price) if is_long else (bar_low <= be_price)
                    if hit_be:
                        be_active = True
                        current_sl = entry # move SL to break-even

                # Check Max Holding Time Stop
                if max_hours and hours_held >= max_hours:
                    close_price = bar['close']
                    final_r = ((close_price - entry) / sl_dist) if is_long else ((entry - close_price) / sl_dist)
                    if tp1_hit:
                        exit_r = (partial_tp1_r * partial_tp1_pct) + (final_r * (1 - partial_tp1_pct))
                    else:
                        exit_r = final_r
                    exit_time = bar_time
                    exit_reason = 'TIME_STOP'
                    break

                # Check Stop Loss / Break Even
                hit_sl = (bar_low <= current_sl) if is_long else (bar_high >= current_sl)
                # Check Take Profit
                hit_tp = (bar_high >= tp) if is_long else (bar_low <= tp)

                if hit_sl and hit_tp:
                    # Conservative: assume SL hit first
                    hit_tp = False

                if hit_sl:
                    if be_active:
                        if tp1_hit:
                            exit_r = partial_tp1_r * partial_tp1_pct # remainder closed at 0
                            exit_reason = 'PARTIAL_WIN_BE'
                        else:
                            exit_r = 0.0
                            exit_reason = 'BE_EXIT'
                    else:
                        exit_r = -1.0
                        exit_reason = 'FULL_SL'
                    exit_time = bar_time
                    break

                elif hit_tp:
                    if tp1_hit:
                        exit_r = (partial_tp1_r * partial_tp1_pct) + (tp_ratio * (1 - partial_tp1_pct))
                        exit_reason = 'FULL_TP_PARTIAL'
                    else:
                        exit_r = tp_ratio
                        exit_reason = 'FULL_TP'
                    exit_time = bar_time
                    break

            if exit_r is None:
                # If still open at end of data
                exit_r = 0.0
                exit_time = df.iloc[-1]['time_dt']
                exit_reason = 'DATA_END'

            duration_h = (exit_time - entry_time).total_seconds() / 3600.0
            pair_lock[pair] = exit_time

            trades.append({
                'pair': pair,
                'direction': setup['direction'],
                'entry_time': entry_time,
                'exit_time': exit_time,
                'duration_hours': duration_h,
                'exit_r': exit_r,
                'exit_reason': exit_reason,
                'max_mfe_r': max_mfe_r
            })

        # Calculate metrics
        r_list = [t['exit_r'] for t in trades]
        durations = [t['duration_hours'] for t in trades]
        total_r = sum(r_list)
        wins = [r for r in r_list if r > 0.05]
        losses = [r for r in r_list if r < -0.05]
        bes = [r for r in r_list if -0.05 <= r <= 0.05]

        win_rate = (len(wins) / (len(wins) + len(losses))) * 100 if (len(wins) + len(losses)) > 0 else 0
        profit_factor = sum(wins) / abs(sum(losses)) if abs(sum(losses)) > 0 else 999.0

        # Max drawdown in R (assuming 1% risk per trade = % drawdown)
        cum_r = np.cumsum(r_list)
        peak_r = np.maximum.accumulate(cum_r)
        dd_r = peak_r - cum_r
        max_dd_r = np.max(dd_r) if len(dd_r) > 0 else 0.0

        # Number of trades that reached +1.0R MFE but ended as FULL LOSS (-1.0R)
        choke_trades = [t for t in trades if t['max_mfe_r'] >= 1.0 and t['exit_r'] <= -0.9]

        avg_dur = np.mean(durations) if durations else 0

        return {
            'model': model_name,
            'total_trades': len(trades),
            'total_r': round(total_r, 1),
            'win_rate': round(win_rate, 1),
            'profit_factor': round(profit_factor, 2),
            'max_dd_pct': round(max_dd_r, 1), # with 1% risk, max_dd_r = max_dd_%
            'avg_duration_h': round(avg_dur, 1),
            'choked_wins': len(choke_trades),
            'wins_count': len(wins),
            'loss_count': len(losses),
            'be_count': len(bes)
        }

    # Run comparisons
    models = [
        ("1. Current Baseline (TP 1.75R, No BE)", 1.75, None, None, 0.5, None),
        ("2. Lower Fixed TP (1.25R, No BE)", 1.25, None, None, 0.5, None),
        ("3. Lower Fixed TP (1.35R, No BE)", 1.35, None, None, 0.5, None),
        ("4. Lower Fixed TP (1.50R, No BE)", 1.50, None, None, 0.5, None),
        ("5. Dynamic BE at +1.0R (TP 1.75R)", 1.75, 1.0, None, 0.5, None),
        ("6. Partial TP (50% @ 1.0R + BE, 50% @ 1.75R)", 1.75, None, 1.0, 0.5, None),
        ("7. Partial TP + 12h Time Stop", 1.75, None, 1.0, 0.5, 12.0),
        ("8. Partial TP + 16h Time Stop", 1.75, None, 1.0, 0.5, 16.0),
        ("9. Dynamic BE at +1.0R + 12h Time Stop", 1.75, 1.0, None, 0.5, 12.0),
    ]

    results = []
    for name, tp_r, be_r, ptp_r, ptp_pct, max_h in models:
        res = simulate_model(name, tp_r, be_r, ptp_r, ptp_pct, max_h)
        results.append(res)

    print("\n==========================================================================================================")
    print(f"{'Model Strategy':<45} | {'Return':<7} | {'WinRate':<7} | {'PF':<5} | {'MaxDD %':<7} | {'Avg Dur':<7} | {'Choked'}")
    print("==========================================================================================================")
    for r in results:
        print(f"{r['model']:<45} | {r['total_r']:>6}R | {r['win_rate']:>6}% | {r['profit_factor']:>5} | {r['max_dd_pct']:>6}% | {r['avg_duration_h']:>6}h | {r['choked_wins']}")
    print("==========================================================================================================")

if __name__ == '__main__':
    run_simulation()
