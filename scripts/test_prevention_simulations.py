import sys, os
import pickle
import pandas as pd
import numpy as np

def run_prevention_study():
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        data = pickle.load(f)
    pairs_data = data[1]
    
    pairs = ['USDCAD', 'USDCHF', 'USDJPY', 'AUDUSD']
    rr = 1.75
    sl_mult = 0.5
    
    def simulate(max_sl_cap=60.0, skip_if_sl_over=999.0, max_ema50_dist_atr=999.0, rsi_bounds=(22, 78)):
        all_trades = []
        for pair in pairs:
            if pair not in pairs_data:
                continue
            m15 = pairs_data[pair]['M15'].copy()
            h1 = pairs_data[pair]['H1'].copy()
            
            pip_unit = 0.01 if 'JPY' in pair else 0.0001
            min_sl_dist = 18.0 * pip_unit
            max_sl_dist = max_sl_cap * pip_unit
            
            m15['time_dt'] = pd.to_datetime(m15['time'], unit='s')
            h1['time_dt'] = pd.to_datetime(h1['time'], unit='s')
            
            h1['e20'] = h1['close'].ewm(span=20, adjust=False).mean()
            h1['e50'] = h1['close'].ewm(span=50, adjust=False).mean()
            h1['e20_slope'] = h1['e20'] - h1['e20'].shift(2)
            
            tr_h1 = np.maximum(h1['high'] - h1['low'], np.maximum(np.abs(h1['high'] - h1['close'].shift(1)), np.abs(h1['low'] - h1['close'].shift(1))))
            h1['atr'] = pd.Series(tr_h1).rolling(14).mean().bfill()
            
            h1_idx = h1.set_index('time_dt')
            h4 = h1_idx.resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna().reset_index()
            h4['e20'] = h4['close'].ewm(span=20, adjust=False).mean()
            h4['e50'] = h4['close'].ewm(span=50, adjust=False).mean()
            h4['ema_bull'] = h4['e20'] > h4['e50']
            h4['ema_bear'] = h4['e20'] < h4['e50']
            
            m15['h1_time'] = m15['time_dt'].dt.floor('h') - pd.Timedelta(hours=1)
            m15['h4_time'] = m15['time_dt'].dt.floor('4h') - pd.Timedelta(hours=4)
            
            m15['h1_e50'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['e50']))).values
            m15['h1_e20'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['e20']))).values
            m15['h1_slope'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['e20_slope']))).values
            m15['h1_atr'] = m15['h1_time'].map(dict(zip(h1['time_dt'], h1['atr']))).values
            
            m15['h4_ema_bull'] = m15['h4_time'].map(dict(zip(h4['time_dt'], h4['ema_bull']))).fillna(True).values
            m15['h4_ema_bear'] = m15['h4_time'].map(dict(zip(h4['time_dt'], h4['ema_bear']))).fillna(True).values
            
            close = m15['close'].values
            open_ = m15['open'].values
            high = m15['high'].values
            low = m15['low'].values
            hours = m15['time_dt'].dt.hour.values
            weekdays = m15['time_dt'].dt.day_name().values
            n = len(close)
            
            m15_e20 = m15['close'].ewm(span=20, adjust=False).mean().values
            m15_e50 = m15['close'].ewm(span=50, adjust=False).mean().values
            
            tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
            tr[0] = high[0] - low[0]
            atr14 = pd.Series(tr).rolling(14).mean().bfill().values
            
            delta = pd.Series(close).diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            rs = gain.rolling(14).mean() / (loss.rolling(14).mean() + 1e-9)
            rsi = (100 - (100 / (1 + rs))).bfill().values
            
            don_h = pd.Series(high).shift(1).rolling(32).max().bfill().values
            don_l = pd.Series(low).shift(1).rolling(32).min().bfill().values
            
            h1_e20 = m15['h1_e20'].values
            h1_e50 = m15['h1_e50'].values
            h1_slope = m15['h1_slope'].values
            h1_atr = m15['h1_atr'].values
            h4_bull = m15['h4_ema_bull'].values
            h4_bear = m15['h4_ema_bear'].values
            
            state = 0
            entry_price, sl_price, tp_price = 0.0, 0.0, 0.0
            entry_idx = 0
            hunting = 0
            hunt_level = 0.0
            hunt_ob_h, hunt_ob_l = 0.0, 0.0
            hunt_fib_50 = 0.0
            hunt_atr = 0.0
            hunt_idx = 0
            lockout_until = 0
            consec_losses = 0
            last_exit_idx = -999
            
            for i in range(50, n):
                if state != 0:
                    hold = i - entry_idx
                    if state == 1:
                        if high[i] >= tp_price:
                            all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'type': 'LONG', 'res': 'WIN', 'pips': (tp_price - entry_price)/pip_unit, 'sl_pips': (entry_price - sl_price)/pip_unit})
                            state = 0
                            last_exit_idx = i
                            consec_losses = 0
                        elif low[i] <= sl_price:
                            all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'type': 'LONG', 'res': 'LOSS', 'pips': (sl_price - entry_price)/pip_unit, 'sl_pips': (entry_price - sl_price)/pip_unit})
                            state = 0
                            last_exit_idx = i
                            consec_losses += 1
                            if consec_losses >= 2:
                                lockout_until = i + 48
                                consec_losses = 0
                        elif hold >= 160:
                            p = (close[i] - entry_price) / pip_unit
                            res = 'WIN' if p > 0 else 'LOSS'
                            all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'type': 'LONG', 'res': res, 'pips': p, 'sl_pips': (entry_price - sl_price)/pip_unit})
                            state = 0
                            last_exit_idx = i
                    elif state == -1:
                        if low[i] <= tp_price:
                            all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'type': 'SHORT', 'res': 'WIN', 'pips': (entry_price - tp_price)/pip_unit, 'sl_pips': (sl_price - entry_price)/pip_unit})
                            state = 0
                            last_exit_idx = i
                            consec_losses = 0
                        elif high[i] >= sl_price:
                            all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'type': 'SHORT', 'res': 'LOSS', 'pips': (entry_price - sl_price)/pip_unit, 'sl_pips': (sl_price - entry_price)/pip_unit})
                            state = 0
                            last_exit_idx = i
                            consec_losses += 1
                            if consec_losses >= 2:
                                lockout_until = i + 48
                                consec_losses = 0
                        elif hold >= 160:
                            p = (entry_price - close[i]) / pip_unit
                            res = 'WIN' if p > 0 else 'LOSS'
                            all_trades.append({'pair': pair, 'time': m15['time_dt'].iloc[entry_idx], 'type': 'SHORT', 'res': res, 'pips': p, 'sl_pips': (sl_price - entry_price)/pip_unit})
                            state = 0
                            last_exit_idx = i
                    continue
                    
                if i < lockout_until or (i - last_exit_idx) < 3:
                    continue
                    
                hr = hours[i]
                wday = weekdays[i]
                is_fri_pm = (wday == 'Friday') and (hr >= 12)
                in_active_hours = (hr != 21) and not is_fri_pm
                
                slope_thresh = 0.10 * h1_atr[i]
                h1_slope_bull = h1_slope[i] >= slope_thresh
                h1_slope_bear = -h1_slope[i] >= slope_thresh
                
                h1_trend_bull = (close[i] > h1_e50[i]) and (h1_e20[i] > h1_e50[i]) and h1_slope_bull and h4_bull[i]
                h1_trend_bear = (close[i] < h1_e50[i]) and (h1_e20[i] < h1_e50[i]) and h1_slope_bear and h4_bear[i]
                
                m15_bull = (close[i] > m15_e50[i]) and (m15_e20[i] > m15_e50[i])
                m15_bear = (close[i] < m15_e50[i]) and (m15_e20[i] < m15_e50[i])
                
                long_setup = h1_trend_bull and m15_bull and (close[i] > don_h[i]) and (close[i-1] <= don_h[i-1]) and in_active_hours
                short_setup = h1_trend_bear and m15_bear and (close[i] < don_l[i]) and (close[i-1] >= don_l[i-1]) and in_active_hours
                
                if hunting == 0:
                    if long_setup:
                        hunting = 1
                        hunt_idx = i
                        hunt_level = don_h[i]
                        hunt_ob_l = low[i-1] if close[i-1] < open_[i-1] else low[i]
                        hunt_ob_h = high[i-1] if close[i-1] < open_[i-1] else high[i]
                        hunt_fib_50 = high[i] - 0.50 * (high[i] - hunt_ob_l)
                        hunt_atr = atr14[i]
                    elif short_setup:
                        hunting = -1
                        hunt_idx = i
                        hunt_level = don_l[i]
                        hunt_ob_h = high[i-1] if close[i-1] > open_[i-1] else high[i]
                        hunt_ob_l = low[i-1] if close[i-1] > open_[i-1] else low[i]
                        hunt_fib_50 = low[i] + 0.50 * (hunt_ob_h - low[i])
                        hunt_atr = atr14[i]
                else:
                    if (i - hunt_idx) > 8:
                        hunting = 0
                    elif hunting == 1:
                        retest = (low[i] <= hunt_level * 1.0005) or (low[i] <= m15_e20[i]) or (low[i] <= hunt_fib_50) or (low[i] <= hunt_ob_h)
                        rejection = (close[i] > open_[i])
                        rsi_ok = (rsi[i] <= rsi_bounds[1])
                        dist_ema50_atr = abs(close[i] - m15_e50[i]) / atr14[i]
                        ema_dist_ok = dist_ema50_atr <= max_ema50_dist_atr
                        if retest and rejection and rsi_ok and ema_dist_ok and in_active_hours:
                            raw_sl = min(hunt_ob_l, low[i]) - (hunt_atr * sl_mult)
                            raw_sl_pips = (close[i] - raw_sl) / pip_unit
                            if raw_sl_pips <= skip_if_sl_over:
                                sl_dist = min(max(close[i] - raw_sl, min_sl_dist), max_sl_dist)
                                state = 1
                                hunting = 0
                                entry_price = close[i]
                                entry_idx = i
                                sl_price = entry_price - sl_dist
                                tp_price = entry_price + (sl_dist * rr)
                    elif hunting == -1:
                        retest = (high[i] >= hunt_level * 0.9995) or (high[i] >= m15_e20[i]) or (high[i] >= hunt_fib_50) or (high[i] >= hunt_ob_l)
                        rejection = (close[i] < open_[i])
                        rsi_ok = (rsi[i] >= rsi_bounds[0])
                        dist_ema50_atr = abs(close[i] - m15_e50[i]) / atr14[i]
                        ema_dist_ok = dist_ema50_atr <= max_ema50_dist_atr
                        if retest and rejection and rsi_ok and ema_dist_ok and in_active_hours:
                            raw_sl = max(hunt_ob_h, high[i]) + (hunt_atr * sl_mult)
                            raw_sl_pips = (raw_sl - close[i]) / pip_unit
                            if raw_sl_pips <= skip_if_sl_over:
                                sl_dist = min(max(raw_sl - close[i], min_sl_dist), max_sl_dist)
                                state = -1
                                hunting = 0
                                entry_price = close[i]
                                entry_idx = i
                                sl_price = entry_price + sl_dist
                                tp_price = entry_price - (sl_dist * rr)
        
        df = pd.DataFrame(all_trades)
        if len(df) == 0:
            return 0, 0, 0, 0, 0, 0
        df['time'] = pd.to_datetime(df['time'])
        df_6m = df[df['time'] >= '2026-03-15'].copy()
        w = df_6m[df_6m['res'] == 'WIN']
        l = df_6m[df_6m['res'] == 'LOSS']
        tot = len(df_6m)
        nw = len(w)
        nl = len(l)
        wr = nw / tot * 100 if tot > 0 else 0
        pips_w = w['pips'].sum()
        pips_l = l['pips'].sum()
        net = pips_w + pips_l
        pf = abs(pips_w / pips_l) if pips_l != 0 else np.nan
        return tot, nw, nl, wr, net, pf

    print("=========================================================================================")
    print("COMPARATIVE SIMULATION: IMPACT ON PERFORMANCE & PRESERVATION OF GOOD TRADES")
    print("=========================================================================================")
    print(f"{'Configuration':<45} | {'Trades':<6} | {'Wins':<4} | {'Loss':<4} | {'WR (%)':<6} | {'Net Pips':<10} | {'PF':<5}")
    print("-" * 90)

    # 1. Baseline
    t, nw, nl, wr, net, pf = simulate()
    print(f"{'1. Current Baseline (Max SL 60p)':<45} | {t:<6} | {nw:<4} | {nl:<4} | {wr:<6.1f} | {net:<+10.1f} | {pf:<5.2f}")

    # 2. Cap Max SL at 25 pips (trades are NOT skipped, wide SL is just capped to 25p)
    t, nw, nl, wr, net, pf = simulate(max_sl_cap=25.0)
    print(f"{'2. Cap Max SL at 25.0p (No trades skipped)':<45} | {t:<6} | {nw:<4} | {nl:<4} | {wr:<6.1f} | {net:<+10.1f} | {pf:<5.2f}")

    # 3. Cap Max SL at 22 pips
    t, nw, nl, wr, net, pf = simulate(max_sl_cap=22.0)
    print(f"{'3. Cap Max SL at 22.0p (No trades skipped)':<45} | {t:<6} | {nw:<4} | {nl:<4} | {wr:<6.1f} | {net:<+10.1f} | {pf:<5.2f}")

    # 4. Skip trades if raw SL > 30 pips
    t, nw, nl, wr, net, pf = simulate(skip_if_sl_over=30.0)
    print(f"{'4. Skip Trades where Raw SL > 30.0p':<45} | {t:<6} | {nw:<4} | {nl:<4} | {wr:<6.1f} | {net:<+10.1f} | {pf:<5.2f}")

    # 5. Overextension Guard: Skip if Entry > 2.5x ATR from 15m EMA50
    t, nw, nl, wr, net, pf = simulate(max_ema50_dist_atr=2.5)
    print(f"{'5. Overextension Guard (Dist EMA50 <= 2.5 ATR)':<45} | {t:<6} | {nw:<4} | {nl:<4} | {wr:<6.1f} | {net:<+10.1f} | {pf:<5.2f}")

    # 6. Combined Non-Invasive Safety: Cap Max SL at 25p + Dist EMA50 <= 2.5 ATR
    t, nw, nl, wr, net, pf = simulate(max_sl_cap=25.0, max_ema50_dist_atr=2.5)
    print(f"{'6. Combined: Cap SL 25p + Dist EMA50 <= 2.5 ATR':<45} | {t:<6} | {nw:<4} | {nl:<4} | {wr:<6.1f} | {net:<+10.1f} | {pf:<5.2f}")

if __name__ == '__main__':
    run_prevention_study()
