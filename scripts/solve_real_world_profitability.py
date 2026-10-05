"""
Solve Real World Live Market Profitability
Under True Pessimistic Execution + Full MT5 Spread & Slippage ($0.35 Gold, 1.5p FX)
Tests:
1. Stop Loss: Realistic Order Block + ATR buffer ($10.00 - $25.00 for Gold, 20 - 35 pips for Forex).
2. Take Profit: 1.5R, 1.75R, 2.0R with structural liquidity targets.
3. Partial TP / Breakeven rules: Realistic evaluation (giving trades room to run).
4. Finding the TRUE viable live-market edge.
"""

import pickle
import pandas as pd
import numpy as np

def run_real_world_simulation():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        data_cache = pickle.load(f)
        
    pairs = ['XAUUSD', 'EURUSD', 'USDCAD']
    
    # Grid of realistic configurations
    test_models = [
        # (name, rr, be_at_r, take_partial, gold_sl_usd_min, gold_sl_usd_max, fx_sl_pips_min, fx_sl_pips_max, donch_gold, donch_fx, toxic_filter)
        ("Model 1: Fixed 1.75R TP (No Early BE Chop, Wide Stops)", 1.75, 999.0, False, 10.0, 25.0, 18.0, 40.0, 8, 20, True),
        ("Model 2: Fixed 1.50R TP (Fast Sweep Target)", 1.50, 999.0, False, 10.0, 25.0, 18.0, 40.0, 8, 20, True),
        ("Model 3: BE Lock at +1.2R (No Partial, Let Run to 1.75R)", 1.75, 1.20, False, 10.0, 25.0, 18.0, 40.0, 8, 20, True),
        ("Model 4: Realistic Model J (Bank 50% at +1.2R, BE + 2p, Trail to 1.75R)", 1.75, 1.20, True, 10.0, 25.0, 18.0, 40.0, 8, 20, True),
        ("Model 5: Realistic Model J (Bank 50% at +1.0R, BE + 2p, Trail to 1.75R)", 1.75, 1.00, True, 10.0, 25.0, 18.0, 40.0, 8, 20, True),
        ("Model 6: High-Confluence 10-Bar Donchian, 1.5R TP", 1.50, 999.0, False, 12.0, 30.0, 20.0, 45.0, 10, 20, True),
        ("Model 7: Gold Focus (Donchian 8, Toxic Filter, 1.6R TP)", 1.60, 999.0, False, 10.0, 22.0, 18.0, 35.0, 8, 20, True)
    ]
    
    for (name, rr, be_at_r, take_partial, g_min_sl, g_max_sl, fx_min_sl, fx_max_sl, d_gold, d_fx, toxic_f) in test_models:
        all_trades = []
        
        for pair in pairs:
            df = data_cache[pair].copy()
            if df['time_dt'].dt.tz is not None:
                df['time_dt'] = df['time_dt'].dt.tz_localize(None)
            df = df.sort_values('time_dt').reset_index(drop=True)
            
            is_gold = pair == 'XAUUSD'
            pip = 0.10 if is_gold else 0.0001
            donch_len = d_gold if is_gold else d_fx
            
            # Dollar / pip stop loss scale
            min_sl_dist = g_min_sl if is_gold else (fx_min_sl * pip)
            max_sl_dist = g_max_sl if is_gold else (fx_max_sl * pip)
            sl_mult = 0.50
            max_hunt = 10
            
            spread = 0.35 if is_gold else (1.5 * pip)
            slippage = 0.10 if is_gold else (0.5 * pip)
            total_friction = spread + slippage
            
            # Indicators
            df['e20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['e50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['e20_slope'] = df['e20'] - df['e20'].shift(2)
            
            tr = np.maximum(df['high'] - df['low'], np.maximum(np.abs(df['high'] - df['close'].shift(1)), np.abs(df['low'] - df['close'].shift(1))))
            df['atr'] = pd.Series(tr).rolling(14).mean().bfill()
            
            delta = df['close'].diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            rs = gain.rolling(14).mean() / (loss.rolling(14).mean() + 1e-9)
            df['rsi'] = (100 - (100 / (1 + rs))).bfill()
            
            df['don_h'] = df['high'].shift(1).rolling(donch_len).max()
            df['don_l'] = df['low'].shift(1).rolling(donch_len).min()
            
            df_idx = df.set_index('time_dt')
            df_4h = df_idx.resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna().reset_index()
            df_4h['e20'] = df_4h['close'].ewm(span=20, adjust=False).mean()
            df_4h['e50'] = df_4h['close'].ewm(span=50, adjust=False).mean()
            df_4h['ema_bull'] = df_4h['e20'] > df_4h['e50']
            df_4h['ema_bear'] = df_4h['e20'] < df_4h['e50']
            
            df['h4_time'] = df['time_dt'].dt.floor('4h') - pd.Timedelta(hours=4)
            df['h4_bull'] = df['h4_time'].map(dict(zip(df_4h['time_dt'], df_4h['ema_bull']))).fillna(True)
            df['h4_bear'] = df['h4_time'].map(dict(zip(df_4h['time_dt'], df_4h['ema_bear']))).fillna(True)
            
            c = df['close'].values
            h = df['high'].values
            l = df['low'].values
            o = df['open'].values
            e20 = df['e20'].values
            e50 = df['e50'].values
            e20_slope = df['e20_slope'].values
            atr = df['atr'].values
            rsi = df['rsi'].values
            don_h = df['don_h'].values
            don_l = df['don_l'].values
            h4_bull = df['h4_bull'].values
            h4_bear = df['h4_bear'].values
            hours = df['time_dt'].dt.hour.values
            weekdays = df['time_dt'].dt.day_name().values
            
            trades = []
            state = 0
            entry_price, sl_price, tp_price = 0.0, 0.0, 0.0
            entry_idx = 0
            hunting = 0
            hunt_level, hunt_ob_h, hunt_ob_l, hunt_fib_50, hunt_atr, hunt_idx = 0.0, 0.0, 0.0, 0.0, 0.0, 0
            lockout_until = 0
            consec_losses = 0
            last_exit_idx = -999
            partial_taken = False
            partial_r_banked = 0.0
            initial_sl_dist = 0.0
            
            start_idx = 100
            n = len(df)
            
            for i in range(start_idx, n):
                if state != 0:
                    hold = i - entry_idx
                    if hold >= 1:
                        init_sl_dist = initial_sl_dist
                        
                        # Break-even check
                        if not partial_taken and be_at_r < 900:
                            if state == 1 and (h[i] - entry_price) >= (init_sl_dist * be_at_r):
                                partial_taken = True
                                partial_r_banked = (0.50 * be_at_r) if take_partial else 0.0
                                sl_price = entry_price + (2.0 * pip) # BE + 2 pips covers spread
                            elif state == -1 and (entry_price - l[i]) >= (init_sl_dist * be_at_r):
                                partial_taken = True
                                partial_r_banked = (0.50 * be_at_r) if take_partial else 0.0
                                sl_price = entry_price - (2.0 * pip)
                                
                        # STRICT PESSIMISTIC RESOLUTION:
                        # If low <= sl_price on long, SL executes!
                        touches_sl = (l[i] <= sl_price) if state == 1 else (h[i] >= sl_price)
                        touches_tp = (h[i] >= tp_price) if state == 1 else (l[i] <= tp_price)
                        
                        exit_triggered = False
                        exit_price = 0.0
                        
                        if touches_sl:
                            exit_triggered = True
                            exit_price = sl_price
                        elif touches_tp:
                            exit_triggered = True
                            exit_price = tp_price
                        elif hold >= 72 and ((state == 1 and c[i] < e20[i]) or (state == -1 and c[i] > e20[i])):
                            exit_triggered = True
                            exit_price = c[i]
                            
                        if exit_triggered:
                            dir_mult = 1 if state == 1 else -1
                            raw_diff = (exit_price - entry_price) * dir_mult
                            net_diff = raw_diff - total_friction
                            rem_r = net_diff / (init_sl_dist + 1e-9)
                            
                            if partial_taken and take_partial:
                                final_r = partial_r_banked + (rem_r * 0.50)
                                final_pips = ((be_at_r * init_sl_dist / pip) * 0.50) + ((net_diff / pip) * 0.50)
                            else:
                                final_r = rem_r
                                final_pips = net_diff / pip
                                
                            outcome = 'WIN' if final_r > 0.05 else ('LOSS' if final_r < -0.05 else 'BREAKEVEN')
                            
                            trades.append({
                                'pair': pair,
                                'entry_time': df['time_dt'].iloc[entry_idx],
                                'month_cohort': df['time_dt'].iloc[entry_idx].strftime('%Y-%m'),
                                'type': 'LONG' if state == 1 else 'SHORT',
                                'result': outcome,
                                'realized_r': round(final_r, 2),
                                'realized_pips': round(final_pips, 1),
                                'hold_bars': hold
                            })
                            
                            state = 0
                            last_exit_idx = i
                            partial_taken = False
                            partial_r_banked = 0.0
                            
                            if outcome == 'WIN':
                                consec_losses = 0
                            else:
                                consec_losses += 1
                                if consec_losses >= 2:
                                    lockout_until = i + 12
                                    consec_losses = 0
                            continue
                            
                if i < lockout_until or (i - last_exit_idx) < 1:
                    continue
                    
                hr = hours[i]
                wday = weekdays[i]
                if wday == 'Sunday':
                    continue
                if wday == 'Friday' and hr >= 12:
                    continue
                if toxic_f and is_gold and hr in [0, 4, 15, 16, 19]:
                    continue
                elif not is_gold and (12 <= hr < 16):
                    continue
                    
                slope_thresh = 0.08 * atr[i]
                h1_slope_bull = e20_slope[i] >= slope_thresh
                h1_slope_bear = -e20_slope[i] >= slope_thresh
                
                trend_bull = (c[i] > e50[i]) and (e20[i] > e50[i]) and h1_slope_bull and h4_bull[i]
                trend_bear = (c[i] < e50[i]) and (e20[i] < e50[i]) and h1_slope_bear and h4_bear[i]
                
                long_setup = trend_bull and (c[i] > don_h[i]) and (c[i-1] <= don_h[i-1])
                short_setup = trend_bear and (c[i] < don_l[i]) and (c[i-1] >= don_l[i-1])
                
                if hunting == 0:
                    if long_setup:
                        hunting = 1
                        hunt_idx = i
                        hunt_level = don_h[i]
                        hunt_ob_l = l[i-1] if c[i-1] < o[i-1] else l[i]
                        hunt_ob_h = h[i-1] if c[i-1] < o[i-1] else h[i]
                        hunt_fib_50 = h[i] - 0.50 * (h[i] - hunt_ob_l)
                        hunt_atr = atr[i]
                    elif short_setup:
                        hunting = -1
                        hunt_idx = i
                        hunt_level = don_l[i]
                        hunt_ob_h = h[i-1] if c[i-1] > o[i-1] else h[i]
                        hunt_ob_l = l[i-1] if c[i-1] > o[i-1] else l[i]
                        hunt_fib_50 = l[i] + 0.50 * (hunt_ob_h - l[i])
                        hunt_atr = atr[i]
                else:
                    if (i - hunt_idx) > max_hunt:
                        hunting = 0
                    elif hunting == 1:
                        retest = (l[i] <= hunt_level * 1.0005) or (l[i] <= e20[i]) or (l[i] <= hunt_fib_50) or (l[i] <= hunt_ob_h)
                        rejection = (c[i] > o[i])
                        rsi_ok = (rsi[i] <= 75.0)
                        if retest and rejection and rsi_ok:
                            raw_sl = min(hunt_ob_l, l[i]) - (hunt_atr * sl_mult)
                            sl_dist = min(max(c[i] - raw_sl, min_sl_dist), max_sl_dist)
                            
                            state = 1
                            hunting = 0
                            entry_price = c[i] + slippage
                            entry_idx = i
                            initial_sl_dist = sl_dist
                            sl_price = entry_price - sl_dist
                            tp_price = entry_price + (sl_dist * rr)
                            partial_taken = False
                            partial_r_banked = 0.0
                    elif hunting == -1:
                        retest = (h[i] >= hunt_level * 0.9995) or (h[i] >= e20[i]) or (h[i] >= hunt_fib_50) or (h[i] >= hunt_ob_l)
                        rejection = (c[i] < o[i])
                        rsi_ok = (rsi[i] >= 25.0)
                        if retest and rejection and rsi_ok:
                            raw_sl = max(hunt_ob_h, h[i]) + (hunt_atr * sl_mult)
                            sl_dist = min(max(raw_sl - c[i], min_sl_dist), max_sl_dist)
                            
                            state = -1
                            hunting = 0
                            entry_price = c[i] - slippage
                            entry_idx = i
                            initial_sl_dist = sl_dist
                            sl_price = entry_price + sl_dist
                            tp_price = entry_price - (sl_dist * rr)
                            partial_taken = False
                            partial_r_banked = 0.0
                            
            all_trades.extend(trades)
            
        df_all = pd.DataFrame(all_trades)
        if df_all.empty:
            print(f"[{name}] No trades generated.")
            continue
            
        tot = len(df_all)
        wins = len(df_all[df_all['result'] == 'WIN'])
        losses = len(df_all[df_all['result'] == 'LOSS'])
        wr = (wins / tot) * 100.0
        net_r = df_all['realized_r'].sum()
        net_pips = df_all['realized_pips'].sum()
        gw = df_all[df_all['realized_r'] > 0]['realized_r'].sum()
        gl = abs(df_all[df_all['realized_r'] < 0]['realized_r'].sum())
        pf = gw / (gl + 1e-9)
        m_grp = df_all.groupby('month_cohort')['realized_r'].sum()
        pos_m = len(m_grp[m_grp > 0])
        tot_m = len(m_grp)
        
        print(f"\n{name}")
        print(f"Trades: {tot:>3} ({tot/103.0:.2f}/wk) | WR: {wr:>5.1f}% | Net R: {net_r:>+7.2f}R | PF: {pf:>4.2f} | Pos Months: {pos_m}/{tot_m} ({(pos_m/tot_m)*100:.1f}%)")
        
        p_grp = df_all.groupby('pair').agg(
            trades=('result', 'count'),
            win_rate=('result', lambda x: (x == 'WIN').mean() * 100.0),
            net_r=('realized_r', 'sum'),
            net_pips=('realized_pips', 'sum')
        )
        print(p_grp.to_string())

if __name__ == '__main__':
    run_real_world_simulation()
