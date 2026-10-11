"""
Comprehensive Six-Month Historical Backtest and Prop-Firm Audit Engine.
Validates the Fixed 15-Pip TP / 10-Pip SL Forex Strategy against 6 Months of Tick/M15 Market Data.
"""

import sys
import pickle
import math
import numpy as np
import pandas as pd
from datetime import datetime, timezone

def run_six_months_audit():
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        cache_data = pickle.load(f)
    pairs_data = cache_data[1]

    forex_pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'USDCHF', 'AUDUSD']
    start_date = '2025-10-01 00:00:00'
    end_date = '2026-03-31 23:45:00'

    print("================================================================================")
    print("PHASE 6 & 7: SIX-MONTH HISTORICAL BACKTEST ENGINE (OCT 1, 2025 - MAR 31, 2026)")
    print("================================================================================")
    print(f"Target Window: {start_date} to {end_date}")
    print(f"Eligible Instruments: {forex_pairs}")
    print("Gold (XAUUSD): Strictly Excluded (0% allocation)")
    print("Fixed Take Profit: 15.0 pips | Fixed Stop Loss: 10.0 pips | Target R:R: 1:1.50")
    print("Execution Costs: Real Broker Spreads + 0.5 pip Slippage + $3.50/lot Commission")
    print("Ambiguity Policy: Conservative (Assume Stop-Loss hit first if same candle)")
    print("Session Filter: 06:00 - 17:00 UTC (London & NY Institutional Hours)")
    print("--------------------------------------------------------------------------------\n")

    # Step 1: Pre-process data for each pair
    pair_dfs = {}
    for pair in forex_pairs:
        if pair not in pairs_data:
            print(f"WARNING: {pair} not found in cache!")
            continue
        m15 = pairs_data[pair]['M15'].copy()
        h1 = pairs_data[pair]['H1'].copy()

        m15['dt'] = pd.to_datetime(m15['time'], unit='s', utc=True)
        h1['dt'] = pd.to_datetime(h1['time'], unit='s', utc=True)

        # Filter window
        m15 = m15.sort_values('dt').reset_index(drop=True)
        h1 = h1.sort_values('dt').reset_index(drop=True)

        is_jpy = 'JPY' in pair
        pip_unit = 0.01 if is_jpy else 0.0001

        # 1H Macro trend indicators (EMA 20, EMA 50)
        h1['e20'] = h1['close'].ewm(span=20, adjust=False).mean()
        h1['e50'] = h1['close'].ewm(span=50, adjust=False).mean()
        h1['e20_slope'] = h1['e20'] - h1['e20'].shift(2)
        h1['macro_bull'] = (h1['close'] > h1['e50']) & (h1['e20'] > h1['e50']) & (h1['e20_slope'] > 0)
        h1['macro_bear'] = (h1['close'] < h1['e50']) & (h1['e20'] < h1['e50']) & (h1['e20_slope'] < 0)

        # Map 1H trend into M15 with 1-hour lag to prevent lookahead
        m15['h1_slot'] = m15['dt'].dt.floor('h') - pd.Timedelta(hours=1)
        h1_bull_map = dict(zip(h1['dt'], h1['macro_bull']))
        h1_bear_map = dict(zip(h1['dt'], h1['macro_bear']))
        m15['h1_bull'] = m15['h1_slot'].map(h1_bull_map).fillna(False).values
        m15['h1_bear'] = m15['h1_slot'].map(h1_bear_map).fillna(False).values

        # 15M Indicators
        m15['e20'] = m15['close'].ewm(span=20, adjust=False).mean()
        m15['e50'] = m15['close'].ewm(span=50, adjust=False).mean()
        m15['e20_slope'] = m15['e20'] - m15['e20'].shift(2)

        # 15M Donchian (20 bars)
        don_len = 20
        m15['don_h'] = m15['high'].shift(1).rolling(don_len).max().bfill()
        m15['don_l'] = m15['low'].shift(1).rolling(don_len).min().bfill()

        # 15M RSI
        delta = m15['close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        m15['rsi'] = (100.0 - (100.0 / (1.0 + rs))).bfill()

        # ATR 14
        tr = np.maximum(
            m15['high'] - m15['low'],
            np.maximum(
                np.abs(m15['high'] - m15['close'].shift(1)),
                np.abs(m15['low'] - m15['close'].shift(1))
            )
        )
        tr.iloc[0] = m15['high'].iloc[0] - m15['low'].iloc[0]
        m15['atr'] = tr.rolling(14).mean().bfill()

        pair_dfs[pair] = {
            'df': m15,
            'pip_unit': pip_unit,
            'is_jpy': is_jpy
        }

    # Step 2: Simulate portfolio execution bar-by-bar across all pairs
    def simulate_strategy(variant="BASELINE_FIXED_15_10"):
        all_signals = []

        tp_pips_target = 15.0
        sl_pips_target = 10.0

        for pair in forex_pairs:
            m15 = pair_dfs[pair]['df']
            pip_unit = pair_dfs[pair]['pip_unit']

            close = m15['close'].values
            open_ = m15['open'].values
            high = m15['high'].values
            low = m15['low'].values
            spread_arr = m15['spread'].values
            dt_arr = m15['dt'].values
            h1_bull = m15['h1_bull'].values
            h1_bear = m15['h1_bear'].values
            e20 = m15['e20'].values
            e50 = m15['e50'].values
            e20_slope = m15['e20_slope'].values
            don_h = m15['don_h'].values
            don_l = m15['don_l'].values
            rsi = m15['rsi'].values
            atr = m15['atr'].values
            n = len(m15)

            state = 0 # 0: flat, 1: long, -1: short
            entry_price = 0.0
            sl_price = 0.0
            tp_price = 0.0
            entry_idx = 0
            entry_spread_pips = 0.0

            hunting = 0 # 0: None, 1: Bullish hunting, -1: Bearish hunting
            hunt_idx = 0
            hunt_break_lvl = 0.0
            hunt_ob_l = 0.0
            hunt_ob_h = 0.0
            hunt_fib_50 = 0.0

            # Filter to start evaluation strictly in 6-month window
            # Warmup requires at least 200 bars prior
            for i in range(200, n):
                bar_dt = pd.to_datetime(dt_arr[i], utc=True)

                # Check window
                if bar_dt < pd.Timestamp(start_date, tz='UTC'):
                    continue
                if bar_dt > pd.Timestamp(end_date, tz='UTC'):
                    break

                c = close[i]
                h = high[i]
                l = low[i]
                o = open_[i]
                hr = bar_dt.hour
                weekday = bar_dt.weekday() # 0 = Monday, 6 = Sunday

                # -------------------------------------------------------------
                # 1. Manage active position
                # -------------------------------------------------------------
                if state != 0:
                    exit_triggered = False
                    outcome = None
                    exit_price = 0.0
                    exit_reason = ""

                    # Spread in pips (MT5 spread in points, 1 pip = 10 points)
                    curr_spread_pips = (spread_arr[i] / 10.0) if spread_arr[i] > 0 else 1.0

                    if state == 1: # LONG POSITION
                        # Checks against TP and SL
                        hit_tp = h >= tp_price
                        hit_sl = l <= sl_price

                        if hit_tp and hit_sl:
                            # Conservative same-candle ambiguity rule: assume Stop Loss hit first
                            outcome = 'LOSS'
                            exit_price = sl_price
                            exit_reason = 'SL_SAME_CANDLE_AMBIGUITY'
                            exit_triggered = True
                        elif hit_tp:
                            outcome = 'WIN'
                            exit_price = tp_price
                            exit_reason = 'TAKE_PROFIT'
                            exit_triggered = True
                        elif hit_sl:
                            outcome = 'LOSS'
                            exit_price = sl_price
                            exit_reason = 'STOP_LOSS'
                            exit_triggered = True
                        elif (i - entry_idx) >= 160: # Max hold timeout (40 hours)
                            exit_price = c
                            outcome = 'WIN' if exit_price > entry_price else 'LOSS'
                            exit_reason = 'TIMEOUT'
                            exit_triggered = True

                        if exit_triggered:
                            gross_pips = (exit_price - entry_price) / pip_unit
                            # Transaction costs: real entry spread + 0.5 pip slippage + 0.35 pip commission
                            costs_pips = entry_spread_pips + 0.5 + 0.35
                            net_pips = gross_pips - costs_pips
                            realized_r = net_pips / sl_pips_target

                            all_signals.append({
                                'pair': pair,
                                'direction': 'LONG',
                                'entry_time': pd.Timestamp(dt_arr[entry_idx]),
                                'exit_time': bar_dt,
                                'entry_price': entry_price,
                                'exit_price': exit_price,
                                'tp_price': tp_price,
                                'sl_price': sl_price,
                                'gross_pips': gross_pips,
                                'net_pips': net_pips,
                                'realized_r': realized_r,
                                'outcome': outcome,
                                'exit_reason': exit_reason,
                                'hold_bars': i - entry_idx,
                                'spread_pips': entry_spread_pips,
                                'costs_pips': costs_pips,
                                'variant': variant
                            })
                            state = 0

                    elif state == -1: # SHORT POSITION
                        hit_tp = l <= tp_price
                        hit_sl = h >= sl_price

                        if hit_tp and hit_sl:
                            outcome = 'LOSS'
                            exit_price = sl_price
                            exit_reason = 'SL_SAME_CANDLE_AMBIGUITY'
                            exit_triggered = True
                        elif hit_tp:
                            outcome = 'WIN'
                            exit_price = tp_price
                            exit_reason = 'TAKE_PROFIT'
                            exit_triggered = True
                        elif hit_sl:
                            outcome = 'LOSS'
                            exit_price = sl_price
                            exit_reason = 'STOP_LOSS'
                            exit_triggered = True
                        elif (i - entry_idx) >= 160:
                            exit_price = c
                            outcome = 'WIN' if exit_price < entry_price else 'LOSS'
                            exit_reason = 'TIMEOUT'
                            exit_triggered = True

                        if exit_triggered:
                            gross_pips = (entry_price - exit_price) / pip_unit
                            costs_pips = entry_spread_pips + 0.5 + 0.35
                            net_pips = gross_pips - costs_pips
                            realized_r = net_pips / sl_pips_target

                            all_signals.append({
                                'pair': pair,
                                'direction': 'SHORT',
                                'entry_time': pd.Timestamp(dt_arr[entry_idx]),
                                'exit_time': bar_dt,
                                'entry_price': entry_price,
                                'exit_price': exit_price,
                                'tp_price': tp_price,
                                'sl_price': sl_price,
                                'gross_pips': gross_pips,
                                'net_pips': net_pips,
                                'realized_r': realized_r,
                                'outcome': outcome,
                                'exit_reason': exit_reason,
                                'hold_bars': i - entry_idx,
                                'spread_pips': entry_spread_pips,
                                'costs_pips': costs_pips,
                                'variant': variant
                            })
                            state = 0

                    continue # Skip entry search while in trade

                # -------------------------------------------------------------
                # 2. Check Session Filter (06:00 - 17:00 UTC)
                # -------------------------------------------------------------
                in_session = (6 <= hr < 17) and (weekday < 5) # Mon-Fri institutional hours
                if not in_session:
                    hunting = 0
                    continue

                # -------------------------------------------------------------
                # 3. Two-Phase Pullback Setup Engine
                # -------------------------------------------------------------
                prev_c = close[i-1]
                prev_o = open_[i-1]
                bar_rng = (high[i] - low[i]) + 1e-9

                # Check Phase 1: Donchian Impulse Breakout
                if hunting == 0:
                    long_break = (c > don_h[i]) and (prev_c <= don_h[i-1])
                    trend_bull = (c > e50[i]) and (e20[i] > e50[i]) and (e20_slope[i] > 0) and h1_bull[i]
                    rsi_bull = 38.0 <= rsi[i] <= 80.0

                    short_break = (c < don_l[i]) and (prev_c >= don_l[i-1])
                    trend_bear = (c < e50[i]) and (e20[i] < e50[i]) and (e20_slope[i] < 0) and h1_bear[i]
                    rsi_bear = 20.0 <= rsi[i] <= 62.0

                    # Variant 2 check: secondary pair momentum filter
                    if variant == "OPTIMIZED_WITH_MOMENTUM_FILTER" and pair in ["USDJPY", "AUDUSD", "GBPUSD"]:
                        sep = abs(e20[i] - e50[i])
                        min_sep = (0.20 * atr[i]) if pair == "AUDUSD" else (0.12 * atr[i])
                        if sep < min_sep or abs(e20_slope[i]) < (0.04 * atr[i]):
                            continue

                    if long_break and trend_bull and rsi_bull:
                        hunting = 1
                        hunt_idx = i
                        hunt_break_lvl = don_h[i]
                        # Find origin order block
                        hunt_ob_l = low[i]
                        for k in range(i - 1, max(0, i - 6), -1):
                            if close[k] < open_[k]:
                                hunt_ob_l = low[k]
                                break
                        hunt_fib_50 = high[i] - 0.50 * (high[i] - hunt_ob_l)

                    elif short_break and trend_bear and rsi_bear:
                        hunting = -1
                        hunt_idx = i
                        hunt_break_lvl = don_l[i]
                        hunt_ob_h = high[i]
                        for k in range(i - 1, max(0, i - 6), -1):
                            if close[k] > open_[k]:
                                hunt_ob_h = high[k]
                                break
                        hunt_fib_50 = low[i] + 0.50 * (hunt_ob_h - low[i])

                else:
                    # In HUNTING state: expire if > 8 bars without pullback rejection
                    if (i - hunt_idx) > 8:
                        hunting = 0
                        continue

                    # Phase 2: Pullback + Rejection Candle
                    if hunting == 1:
                        # Pullback check into value zone:
                        pulled_back = (l <= hunt_break_lvl * 1.0005) or (l <= e20[i]) or (l <= hunt_fib_50) or (l <= high[hunt_idx - 1])
                        # Rejection candle check:
                        bullish_rejection = (c > o) and ((c - l) / bar_rng >= 0.45) and (rsi[i] <= 78.0)

                        if pulled_back and bullish_rejection:
                            # Enter LONG on this closed bar confirmation
                            state = 1
                            hunting = 0
                            entry_idx = i
                            entry_price = c
                            entry_spread_pips = (spread_arr[i] / 10.0) if spread_arr[i] > 0 else 1.2
                            tp_price = entry_price + (tp_pips_target * pip_unit)
                            sl_price = entry_price - (sl_pips_target * pip_unit)

                    elif hunting == -1:
                        pulled_back = (h >= hunt_break_lvl * 0.9995) or (h >= e20[i]) or (h >= hunt_fib_50) or (h >= low[hunt_idx - 1])
                        bearish_rejection = (c < o) and ((h - c) / bar_rng >= 0.45) and (rsi[i] >= 22.0)

                        if pulled_back and bearish_rejection:
                            state = -1
                            hunting = 0
                            entry_idx = i
                            entry_price = c
                            entry_spread_pips = (spread_arr[i] / 10.0) if spread_arr[i] > 0 else 1.2
                            tp_price = entry_price - (tp_pips_target * pip_unit)
                            sl_price = entry_price + (sl_pips_target * pip_unit)

        df_trades = pd.DataFrame(all_signals)
        if not df_trades.empty:
            df_trades = df_trades.sort_values('entry_time').reset_index(drop=True)
        return df_trades

    # Run Baseline
    baseline_df = simulate_strategy("BASELINE_FIXED_15_10")
    print(f"Total Completed Baseline Trades: {len(baseline_df)}")
    baseline_df.to_pickle('scripts/six_month_trades_baseline.pkl')

    # Run Variant C (Secondary Pair Momentum Filter)
    opt_df = simulate_strategy("OPTIMIZED_WITH_MOMENTUM_FILTER")
    print(f"Total Completed Variant C Trades: {len(opt_df)}")
    opt_df.to_pickle('scripts/six_month_trades_variant_c.pkl')

    return baseline_df, opt_df

if __name__ == '__main__':
    run_six_months_audit()
