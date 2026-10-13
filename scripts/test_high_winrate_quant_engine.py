"""
High Win-Rate Quantitative Engine:
Combines D1 EMA50 + H1 EMA200 + H1 EMA20 Slope + 28-bar Retest + 12h Circuit Breaker.
Grid searches TP/SL ratios (1.0R to 1.5R) and Trade Management to find configurations with:
- Win Rate > 50%
- Net Profit > 0 (Positive Expectancy)
- Profit Factor > 1.20
"""

import sys
import pickle
import pandas as pd
import numpy as np

def run_quant_engine():
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        data = pickle.load(f)
    pairs_data = data[1]
    pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'USDCHF']

    for window_name, start_date, end_date in [
        ("6-MONTH WINDOW (2026-04-01 to 2026-10-09)", "2026-04-01", "2026-10-09 23:45:00"),
        ("MULTI-YEAR DATASET (2023 to 2026)", "2023-01-01", "2026-10-09 23:45:00")
    ]:
        print("\n" + "="*90)
        print(f"EVALUATION DATASET: {window_name}")
        print("="*90)

        # Precompute indicators for all pairs
        pair_data = {}
        for pair in pairs:
            if pair not in pairs_data: continue
            m15 = pairs_data[pair]['M15'].copy()
            h1 = pairs_data[pair]['H1'].copy()
            d1 = pairs_data[pair]['D1'].copy()

            is_jpy = 'JPY' in pair
            pip_unit = 0.01 if is_jpy else 0.0001

            # D1 EMA 50
            d1['ema50'] = d1['close'].ewm(span=50, adjust=False).mean()
            d1['time_dt'] = pd.to_datetime(d1['time'], unit='s', utc=True).dt.floor('D')

            # H1 indicators
            h1['time_dt'] = pd.to_datetime(h1['time'], unit='s', utc=True)
            h1['ema200'] = h1['close'].ewm(span=200, adjust=False).mean()
            h1['ema50'] = h1['close'].ewm(span=50, adjust=False).mean()
            h1['ema20'] = h1['close'].ewm(span=20, adjust=False).mean()
            h1['ema20_slope'] = h1['ema20'] - h1['ema20'].shift(2)

            h1['date_only'] = h1['time_dt'].dt.floor('D')
            d1_bull_map = dict(zip(d1['time_dt'], d1['close'] > d1['ema50']))
            h1['d1_bull'] = h1['date_only'].map(d1_bull_map).fillna(False)

            h1['h1_bull'] = (h1['close'] > h1['ema200']) & (h1['ema20'] > h1['ema50']) & (h1['d1_bull']) & (h1['ema20_slope'] > 0)
            h1['h1_bear'] = (h1['close'] < h1['ema200']) & (h1['ema20'] < h1['ema50']) & (~h1['d1_bull']) & (h1['ema20_slope'] < 0)

            m15['time_dt'] = pd.to_datetime(m15['time'], unit='s', utc=True)
            m15['h1_time'] = m15['time_dt'].dt.floor('h') - pd.Timedelta(hours=1)
            h1_bull_map = dict(zip(h1['time_dt'], h1['h1_bull']))
            h1_bear_map = dict(zip(h1['time_dt'], h1['h1_bear']))
            m15['h1_bull'] = m15['h1_time'].map(h1_bull_map).fillna(False).values
            m15['h1_bear'] = m15['h1_time'].map(h1_bear_map).fillna(False).values

            close = m15['close'].values
            open_ = m15['open'].values
            high = m15['high'].values
            low = m15['low'].values
            hours = m15['time_dt'].dt.hour.values
            n = len(close)

            m15_ema20 = m15['close'].ewm(span=20, adjust=False).mean().values
            m15_ema50 = m15['close'].ewm(span=50, adjust=False).mean().values

            tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
            tr[0] = high[0] - low[0]
            atr14 = pd.Series(tr).rolling(14).mean().bfill().values

            don_len = 28
            don_h = pd.Series(high).shift(1).rolling(don_len).max().bfill().values
            don_l = pd.Series(low).shift(1).rolling(don_len).min().bfill().values
            break_high = (close > don_h) & (np.roll(close, 1) <= np.roll(don_h, 1))
            break_low = (close < don_l) & (np.roll(close, 1) >= np.roll(don_l, 1))
            break_high[0] = False
            break_low[0] = False

            prev_is_bear = np.roll(close, 1) < np.roll(open_, 1)
            prev_is_bull = np.roll(close, 1) > np.roll(open_, 1)
            ob_bull_l = np.where(prev_is_bear, np.roll(low, 1), low)
            ob_bear_h = np.where(prev_is_bull, np.roll(high, 1), high)

            spread_pips = 0.8 if pair == "EURUSD" else (1.2 if pair == "USDCAD" else 1.0)
            costs_pips = spread_pips + 0.5 + 0.35 # realistic friction

            pair_data[pair] = {
                'm15': m15, 'close': close, 'open': open_, 'high': high, 'low': low, 'hours': hours,
                'atr14': atr14, 'break_high': break_high, 'break_low': break_low,
                'ob_bull_l': ob_bull_l, 'ob_bear_h': ob_bear_h,
                'h1_bull': m15['h1_bull'].values, 'h1_bear': m15['h1_bear'].values,
                'm15_ema20': m15_ema20, 'm15_ema50': m15_ema50,
                'pip_unit': pip_unit, 'costs_pips': costs_pips
            }

        start_ts = pd.Timestamp(start_date, tz='UTC')
        end_ts = pd.Timestamp(end_date, tz='UTC')

        # Test multiple configurations
        test_configs = [
            ("Variant 1: 1.0R Target (20p SL / 20p TP)", 20.0, 1.0, False),
            ("Variant 2: 1.1R Target (20p SL / 22p TP)", 20.0, 1.1, False),
            ("Variant 3: 1.2R Target (20p SL / 24p TP)", 20.0, 1.2, False),
            ("Variant 4: 1.25R Target (20p SL / 25p TP)", 20.0, 1.25, False),
            ("Variant 5: 1.35R Target (20p SL / 27p TP)", 20.0, 1.35, False),
            ("Variant 6: 1.5R Target (20p SL / 30p TP)", 20.0, 1.5, False),
            ("Variant 7: Model J (Bank 60% at 1.0R, SL to BE, 1.5R TP)", 20.0, 1.5, True),
        ]

        for cfg_name, min_sl_p, rr, use_model_j in test_configs:
            all_trades = []

            for pair in pairs:
                pd_p = pair_data[pair]
                m15 = pd_p['m15']
                close = pd_p['close']
                open_ = pd_p['open']
                high = pd_p['high']
                low = pd_p['low']
                hours = pd_p['hours']
                atr14 = pd_p['atr14']
                break_high = pd_p['break_high']
                break_low = pd_p['break_low']
                ob_bull_l = pd_p['ob_bull_l']
                ob_bear_h = pd_p['ob_bear_h']
                h1_bull = pd_p['h1_bull']
                h1_bear = pd_p['h1_bear']
                m15_ema20 = pd_p['m15_ema20']
                m15_ema50 = pd_p['m15_ema50']
                pip_unit = pd_p['pip_unit']
                costs_pips = pd_p['costs_pips']

                min_sl_dist = min_sl_p * pip_unit
                max_sl_dist = 60.0 * pip_unit
                sl_mult = 0.5
                n = len(close)

                state = 0
                entry_price, sl_price, tp_price = 0.0, 0.0, 0.0
                entry_idx = 0
                hunting = 0
                hunt_idx = 0
                hunt_ob_l, hunt_ob_h, hunt_fib50, hunt_atr = 0.0, 0.0, 0.0, 0.0
                init_sl_dist = 0.0
                consec_losses = 0
                pause_until_idx = -999
                partial_taken = False
                partial_r_banked = 0.0

                for i in range(200, n):
                    bar_dt = m15['time_dt'].iloc[i]
                    if bar_dt < start_ts: continue
                    if bar_dt > end_ts: break

                    c = close[i]
                    h = high[i]
                    l = low[i]
                    o = open_[i]
                    a = atr14[i]
                    hr = hours[i]

                    if state != 0:
                        hold = i - entry_idx
                        # Model J partial check
                        if use_model_j and not partial_taken:
                            if state == 1 and (h - entry_price) >= init_sl_dist:
                                partial_taken = True
                                partial_r_banked = 0.60 # Bank 60% at 1.0R
                                sl_price = entry_price + (1.0 * pip_unit) # BE + 1.0p fee buffer
                            elif state == -1 and (entry_price - l) >= init_sl_dist:
                                partial_taken = True
                                partial_r_banked = 0.60
                                sl_price = entry_price - (1.0 * pip_unit)

                        exit_triggered = False
                        exit_price = 0.0

                        if state == 1:
                            if h >= tp_price and l <= sl_price:
                                exit_triggered = True
                                exit_price = sl_price
                            elif h >= tp_price:
                                exit_triggered = True
                                exit_price = tp_price
                            elif l <= sl_price:
                                exit_triggered = True
                                exit_price = sl_price
                            elif hold >= 160:
                                exit_triggered = True
                                exit_price = c
                        elif state == -1:
                            if l <= tp_price and h >= sl_price:
                                exit_triggered = True
                                exit_price = sl_price
                            elif l <= tp_price:
                                exit_triggered = True
                                exit_price = tp_price
                            elif h >= sl_price:
                                exit_triggered = True
                                exit_price = sl_price
                            elif hold >= 160:
                                exit_triggered = True
                                exit_price = c

                        if exit_triggered:
                            dir_mult = 1 if state == 1 else -1
                            gross_pips = (exit_price - entry_price) * dir_mult / pip_unit
                            net_pips = gross_pips - costs_pips
                            sl_pts = init_sl_dist / pip_unit

                            if use_model_j and partial_taken:
                                rem_pips = net_pips
                                final_pips = (sl_pts * 0.60) + (rem_pips * 0.40)
                                final_r = partial_r_banked + ((rem_pips / sl_pts) * 0.40)
                            else:
                                final_pips = net_pips
                                final_r = net_pips / sl_pts

                            res = 'WIN' if final_r > 0.02 else ('LOSS' if final_r < -0.02 else 'BREAKEVEN')
                            all_trades.append({
                                'pair': pair,
                                'time': m15['time_dt'].iloc[entry_idx],
                                'res': res,
                                'R': final_r,
                                'pips': final_pips
                            })
                            state = 0
                            if res == 'WIN':
                                consec_losses = 0
                            else:
                                consec_losses += 1
                                if consec_losses >= 2:
                                    pause_until_idx = i + 48 # 12h circuit breaker
                                    consec_losses = 0
                            continue

                    if i < pause_until_idx:
                        continue

                    in_session = (7 <= hr <= 16)
                    if not in_session:
                        hunting = 0
                        continue

                    if hunting == 0:
                        long_setup = break_high[i] and h1_bull[i] and (m15_ema20[i] > m15_ema50[i])
                        short_setup = break_low[i] and h1_bear[i] and (m15_ema20[i] < m15_ema50[i])

                        if long_setup:
                            hunting = 1
                            hunt_idx = i
                            hunt_ob_l = ob_bull_l[i]
                            hunt_ob_h = high[i]
                            hunt_fib50 = hunt_ob_h - 0.5 * (hunt_ob_h - hunt_ob_l)
                            hunt_atr = a
                        elif short_setup:
                            hunting = -1
                            hunt_idx = i
                            hunt_ob_h = ob_bear_h[i]
                            hunt_ob_l = low[i]
                            hunt_fib50 = hunt_ob_l + 0.5 * (hunt_ob_h - hunt_ob_l)
                            hunt_atr = a
                    else:
                        if (i - hunt_idx) > 4:
                            hunting = 0
                        elif hunting == 1:
                            retrace = (l <= hunt_fib50) or (l <= hunt_ob_h)
                            rejection = c > o
                            if retrace and rejection and in_session:
                                raw_sl = hunt_ob_l - (hunt_atr * sl_mult)
                                sl_dist = max(c - raw_sl, min_sl_dist)
                                if sl_dist <= max_sl_dist:
                                    state = 1
                                    entry_price = c
                                    entry_idx = i
                                    init_sl_dist = sl_dist
                                    sl_price = entry_price - sl_dist
                                    tp_price = entry_price + (sl_dist * rr)
                                    hunting = 0
                                    partial_taken = False
                                    partial_r_banked = 0.0
                        elif hunting == -1:
                            retrace = (h >= hunt_fib50) or (h >= hunt_ob_l)
                            rejection = c < o
                            if retrace and rejection and in_session:
                                raw_sl = hunt_ob_h + (hunt_atr * sl_mult)
                                sl_dist = max(raw_sl - c, min_sl_dist)
                                if sl_dist <= max_sl_dist:
                                    state = -1
                                    entry_price = c
                                    entry_idx = i
                                    init_sl_dist = sl_dist
                                    sl_price = entry_price + sl_dist
                                    tp_price = entry_price - (sl_dist * rr)
                                    hunting = 0
                                    partial_taken = False
                                    partial_r_banked = 0.0

            df_t = pd.DataFrame(all_trades)
            if df_t.empty: continue
            tot = len(df_t)
            w = len(df_t[df_t['res'] == 'WIN'])
            l = len(df_t[df_t['res'] == 'LOSS'])
            be = len(df_t[df_t['res'] == 'BREAKEVEN'])
            wr = (w / tot) * 100.0
            net_r = df_t['R'].sum()
            net_pips = df_t['pips'].sum()
            gw = df_t[df_t['R'] > 0]['R'].sum()
            gl = abs(df_t[df_t['R'] < 0]['R'].sum())
            pf = (gw / gl) if gl > 0 else 99.0
            exp_r = net_r / tot

            status_str = ">>> PASSES (>50% WR & PROFITABLE) <<<" if (wr >= 50.0 and net_r > 0) else ""
            print(f"{cfg_name:52s} | Tr: {tot:4d} | WR: {wr:5.1f}% | Net R: {net_r:+6.2f}R | PF: {pf:.2f} | Pips: {net_pips:+7.1f}p {status_str}")

if __name__ == '__main__':
    run_quant_engine()
