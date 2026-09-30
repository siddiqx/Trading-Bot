import pickle
import pandas as pd
import numpy as np

def run_deep_quant_research():
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

    # 1. Per-Pair Baseline Performance
    print("=" * 80)
    print("STEP 1: PER-PAIR QUANTITATIVE BREAKDOWN (2-YEAR BASELINE: 1.75R TP, SL OB+0.5ATR)")
    print("=" * 80)

    pair_results = {}

    for pair in PAIRS:
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

        trades = []
        last_exit_idx = -1

        for i in range(50, len(df)):
            if i <= last_exit_idx:
                continue

            row = df.iloc[i]
            prev = df.iloc[i - 1]

            bullish_trend = (row['close'] > row['ema50']) and (row['ema20'] > row['ema50']) and (row['ema20_slope'] > 0)
            bearish_trend = (row['close'] < row['ema50']) and (row['ema20'] < row['ema50']) and (row['ema20_slope'] < 0)

            rsi_bull = 45.0 <= row['rsi'] <= 75.0
            rsi_bear = 25.0 <= row['rsi'] <= 55.0

            long_break = (row['close'] > row['donch_high']) and (prev['close'] <= prev['donch_high'])
            short_break = (row['close'] < row['donch_low']) and (prev['close'] >= prev['donch_low'])

            if not ((long_break and bullish_trend and rsi_bull) or (short_break and bearish_trend and rsi_bear)):
                continue

            is_long = long_break
            entry = row['close']

            if is_long:
                ob_low = row['low']
                for k in range(i - 1, max(0, i - 10), -1):
                    c = df.iloc[k]
                    if c['close'] < c['open']:
                        ob_low = c['low']
                        break
                sl_cand = ob_low - (0.50 * row['atr'])
                sl_dist = max(min_sl, min(max_sl, entry - sl_cand))
                sl = entry - sl_dist
                tp = entry + (sl_dist * 1.75)
            else:
                ob_high = row['high']
                for k in range(i - 1, max(0, i - 10), -1):
                    c = df.iloc[k]
                    if c['close'] > c['open']:
                        ob_high = c['high']
                        break
                sl_cand = ob_high + (0.50 * row['atr'])
                sl_dist = max(min_sl, min(max_sl, sl_cand - entry))
                sl = entry + sl_dist
                tp = entry - (sl_dist * 1.75)

            # Evaluate forward bars
            exit_r = None
            max_mfe = 0.0

            for j in range(i + 1, min(i + 150, len(df))):
                bar = df.iloc[j]
                mfe = ((bar['high'] - entry) / sl_dist) if is_long else ((entry - bar['low']) / sl_dist)
                if mfe > max_mfe:
                    max_mfe = mfe

                hit_sl = (bar['low'] <= sl) if is_long else (bar['high'] >= sl)
                hit_tp = (bar['high'] >= tp) if is_long else (bar['low'] <= tp)

                if hit_sl and hit_tp:
                    hit_tp = False

                if hit_tp:
                    exit_r = 1.75
                    last_exit_idx = j
                    break
                elif hit_sl:
                    exit_r = -1.00
                    last_exit_idx = j
                    break

            if exit_r is None:
                exit_r = 0.0
                last_exit_idx = len(df) - 1

            dur_h = (df.iloc[last_exit_idx]['time_dt'] - row['time_dt']).total_seconds() / 3600.0
            trades.append({
                'entry_time': row['time_dt'],
                'exit_time': df.iloc[last_exit_idx]['time_dt'],
                'exit_r': exit_r,
                'max_mfe': max_mfe,
                'dur_h': dur_h
            })

        r_list = [t['exit_r'] for t in trades]
        wins = [r for r in r_list if r > 0]
        losses = [r for r in r_list if r < 0]
        total_r = sum(r_list)
        wr = (len(wins) / len(r_list) * 100) if r_list else 0
        pf = (sum(wins) / abs(sum(losses))) if losses else 0
        cum_r = np.cumsum(r_list)
        peak_r = np.maximum.accumulate(cum_r)
        max_dd = np.max(peak_r - cum_r) if len(cum_r) > 0 else 0
        choked = len([t for t in trades if t['max_mfe'] >= 1.0 and t['exit_r'] <= -0.9])
        avg_dur = np.mean([t['dur_h'] for t in trades]) if trades else 0

        pair_results[pair] = {
            'trades': len(trades),
            'win_rate': round(wr, 1),
            'net_r': round(total_r, 1),
            'pf': round(pf, 2),
            'max_dd_r': round(max_dd, 1),
            'avg_dur': round(avg_dur, 1),
            'choked': choked
        }

    for p, stats in pair_results.items():
        print(f"{p:<8} | Trades: {stats['trades']:<4} | WinRate: {stats['win_rate']:>5}% | Net R: {stats['net_r']:>6} R | PF: {stats['pf']:>4} | Max DD: {stats['max_dd_r']:>5} R | Avg Dur: {stats['avg_dur']:>5}h | Choked: {stats['choked']}")

if __name__ == '__main__':
    run_deep_quant_research()
