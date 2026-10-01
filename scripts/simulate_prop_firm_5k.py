import pickle
import pandas as pd
import numpy as np

def run_prop_firm_simulation():
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

    raw_trades = []

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
            exit_reason = None
            exit_price = None

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
                    exit_price = tp
                    exit_reason = "TP (Liquidity Swept)"
                    last_exit = j
                    break
                elif hit_sl:
                    exit_r = -1.0
                    exit_time = b['time_dt']
                    exit_price = initial_sl
                    exit_reason = "SL (Order Block Hit)"
                    last_exit = j
                    break

                # Implemented Improvement: 20-EMA Invalidation after 24h
                if h_held >= 24.0:
                    ema_cross = (b['close'] < ema20_vals[j]) if is_long else (b['close'] > ema20_vals[j])
                    if ema_cross:
                        exit_price = b['close']
                        exit_r = ((exit_price - entry) / sl_dist) if is_long else ((entry - exit_price) / sl_dist)
                        exit_time = b['time_dt']
                        exit_reason = "EMA Invalidation (Stagnant Exit)"
                        last_exit = j
                        break

            if exit_r is not None and entry_time >= one_month_ago:
                raw_trades.append({
                    'pair': pair,
                    'direction': 'LONG' if is_long else 'SHORT',
                    'entry_time': entry_time,
                    'exit_time': exit_time,
                    'entry': entry,
                    'exit': exit_price,
                    'sl_dist': sl_dist,
                    'exit_r': float(round(exit_r, 2)),
                    'reason': exit_reason,
                    'dur_h': float(round((exit_time - entry_time).total_seconds() / 3600.0, 1))
                })

    raw_trades = sorted(raw_trades, key=lambda t: t['entry_time'])
    return raw_trades

def test_prop_firm(risk_pct=1.0):
    trades = run_prop_firm_simulation()
    
    INITIAL_BALANCE = 5000.0
    DAILY_LOSS_LIMIT_PCT = 3.0  # 3% = $150
    MAX_OVERALL_DD_PCT = 7.0    # 7% = $350 (trailing or fixed from $5000)
    PHASE1_TARGET_PCT = 8.0     # 8% = $400 ($5,400)
    PHASE2_TARGET_PCT = 5.0     # 5% = $250 ($5,250)

    print("=" * 115)
    print(f"PROP FIRM SIMULATION: $5,000 ACCOUNT | RISK PER TRADE: {risk_pct}% (${INITIAL_BALANCE * risk_pct / 100:.2f})")
    print(f"Daily Loss Limit: {DAILY_LOSS_LIMIT_PCT}% ($150.00) | Overall Max Drawdown: {MAX_OVERALL_DD_PCT}% ($350.00)")
    print(f"Phase 1 Target: {PHASE1_TARGET_PCT}% (+$400.00) | Phase 2 Target: {PHASE2_TARGET_PCT}% (+$250.00)")
    print("=" * 115)

    balance = INITIAL_BALANCE
    peak_balance = INITIAL_BALANCE
    max_overall_dd_dollars = 0.0
    max_overall_dd_pct = 0.0
    max_daily_dd_pct = 0.0
    daily_pnl = {}

    phase1_passed = False
    phase1_trade_idx = None
    phase2_passed = False
    phase2_trade_idx = None

    breached = False
    breach_reason = None

    print(f"{'#':<3} | {'Entry Date':<16} | {'Pair':<7} {'Dir':<5} | {'Exit Date':<16} | {'Exit R':<7} | {'Trade PnL':<10} | {'Balance':<10} | {'Exit Reason'}")
    print("-" * 115)

    for idx, t in enumerate(trades, 1):
        risk_dollars = balance * (risk_pct / 100.0)
        pnl = t['exit_r'] * risk_dollars
        balance += pnl

        exit_day = t['exit_time'].strftime('%Y-%m-%d')
        daily_pnl[exit_day] = daily_pnl.get(exit_day, 0.0) + pnl

        if balance > peak_balance:
            peak_balance = balance

        dd_dollars = peak_balance - balance
        dd_pct = (dd_dollars / peak_balance) * 100.0
        if dd_pct > max_overall_dd_pct:
            max_overall_dd_pct = dd_pct
            max_overall_dd_dollars = dd_dollars

        # Check phase completions
        if not phase1_passed and balance >= INITIAL_BALANCE * (1.0 + PHASE1_TARGET_PCT / 100.0):
            phase1_passed = True
            phase1_trade_idx = idx

        if phase1_passed and not phase2_passed and balance >= (INITIAL_BALANCE * (1.0 + (PHASE1_TARGET_PCT + PHASE2_TARGET_PCT) / 100.0)):
            phase2_passed = True
            phase2_trade_idx = idx

        # Check daily drawdown rule
        day_loss_pct = (-daily_pnl[exit_day] / balance) * 100.0 if daily_pnl[exit_day] < 0 else 0.0
        if day_loss_pct > max_daily_dd_pct:
            max_daily_dd_pct = day_loss_pct

        if day_loss_pct >= DAILY_LOSS_LIMIT_PCT:
            breached = True
            breach_reason = f"Daily Loss Limit Breached on {exit_day}: -{day_loss_pct:.2f}%"

        if dd_pct >= MAX_OVERALL_DD_PCT:
            breached = True
            breach_reason = f"Max Overall Drawdown Breached: {dd_pct:.2f}% (${dd_dollars:.2f})"

        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
        r_str = f"+{t['exit_r']:.2f}R" if t['exit_r'] >= 0 else f"{t['exit_r']:.2f}R"
        print(f"{idx:<3} | {t['entry_time'].strftime('%Y-%m-%d %H:%M')} | {t['pair']:<7} {t['direction']:<5} | {t['exit_time'].strftime('%Y-%m-%d %H:%M')} | {r_str:<7} | {pnl_str:<10} | ${balance:<9.2f} | {t['reason']}")

    print("-" * 115)
    print("ACCOUNT PERFORMANCE SUMMARY:")
    print(f"Final Balance: ${balance:.2f} (Net Return: +${balance - INITIAL_BALANCE:.2f} / +{((balance - INITIAL_BALANCE)/INITIAL_BALANCE)*100:.2f}%)")
    print(f"Max Daily Drawdown: {max_daily_dd_pct:.2f}% (Limit: {DAILY_LOSS_LIMIT_PCT}%) -> {'SURVIVED' if max_daily_dd_pct < DAILY_LOSS_LIMIT_PCT else 'BREACHED'}")
    print(f"Max Overall Drawdown: {max_overall_dd_pct:.2f}% (${max_overall_dd_dollars:.2f}) (Limit: {MAX_OVERALL_DD_PCT}%) -> {'SURVIVED' if max_overall_dd_pct < MAX_OVERALL_DD_PCT else 'BREACHED'}")
    print(f"Phase 1 (8% Target = $5,400): {'PASSED at Trade #' + str(phase1_trade_idx) if phase1_passed else 'Not hit in 30 days'}")
    print(f"Phase 2 (5% Additional Target = $5,650): {'PASSED at Trade #' + str(phase2_trade_idx) if phase2_passed else 'Not hit'}")
    print(f"Prop Firm Challenge Survival Status: {'100% SURVIVED & PASSED' if not breached else 'BREACHED: ' + breach_reason}")

if __name__ == '__main__':
    print("RUNNING WITH 1.0% RISK PER TRADE:")
    test_prop_firm(risk_pct=1.0)
    print("\n\nRUNNING WITH 0.5% RISK PER TRADE (CONSERVATIVE):")
    test_prop_firm(risk_pct=0.5)
