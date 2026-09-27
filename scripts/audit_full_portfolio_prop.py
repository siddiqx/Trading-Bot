import sys, os, math, pickle
from datetime import datetime, timezone
import pandas as pd
import numpy as np

def run_comprehensive_portfolio_audit():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        all_data = pickle.load(f)
        
    pairs = ['USDCAD', 'USDCHF', 'USDJPY', 'AUDUSD', 'XAUUSD', 'EURUSD', 'GBPUSD', 'NZDUSD']
    whitelisted_set = {'USDCAD', 'USDCHF', 'USDJPY', 'AUDUSD', 'XAUUSD'}
    
    pair_specs = {
        'EURUSD': {'type': 'FOREX', 'pip_unit': 0.0001, 'min_sl_pips': 18.0, 'max_sl_pips': 25.0, 'cost_pips': 2.0, 'usd_quote': True, 'usd_dir': -1},
        'GBPUSD': {'type': 'FOREX', 'pip_unit': 0.0001, 'min_sl_pips': 18.0, 'max_sl_pips': 25.0, 'cost_pips': 2.0, 'usd_quote': True, 'usd_dir': -1},
        'AUDUSD': {'type': 'FOREX', 'pip_unit': 0.0001, 'min_sl_pips': 18.0, 'max_sl_pips': 25.0, 'cost_pips': 2.0, 'usd_quote': True, 'usd_dir': -1},
        'NZDUSD': {'type': 'FOREX', 'pip_unit': 0.0001, 'min_sl_pips': 18.0, 'max_sl_pips': 25.0, 'cost_pips': 2.5, 'usd_quote': True, 'usd_dir': -1},
        'USDCAD': {'type': 'FOREX', 'pip_unit': 0.0001, 'min_sl_pips': 18.0, 'max_sl_pips': 25.0, 'cost_pips': 2.0, 'usd_quote': False, 'usd_dir': 1},
        'USDCHF': {'type': 'FOREX', 'pip_unit': 0.0001, 'min_sl_pips': 18.0, 'max_sl_pips': 25.0, 'cost_pips': 2.5, 'usd_quote': False, 'usd_dir': 1},
        'USDJPY': {'type': 'FOREX', 'pip_unit': 0.01,   'min_sl_pips': 18.0, 'max_sl_pips': 25.0, 'cost_pips': 2.5, 'usd_quote': False, 'usd_dir': 1, 'jpy': True},
        'XAUUSD': {'type': 'COMMODITY', 'pip_unit': 1.00, 'min_sl_pips': 18.0, 'max_sl_pips': 25.0, 'cost_oz': 0.36, 'gold': True, 'usd_dir': -1}
    }
    
    START_DATE = '2026-03-15'
    STARTING_BALANCE = 5000.0
    RISK_PCT = 0.01
    RR_RATIO = 1.75
    MAX_DAILY_DD_PCT = 0.03 # 3% = $150
    MAX_OVERALL_DD_PCT = 0.08 # 8% = $400
    LEVERAGE = 100.0
    
    # -------------------------------------------------------------
    # 1. GENERATE RAW STRATEGY SIGNALS PER PAIR
    # -------------------------------------------------------------
    pair_signals = {}
    pair_dfs = {}
    
    for pair in pairs:
        df = all_data[pair].copy()
        if df['time_dt'].dt.tz is not None:
            df['time_dt'] = df['time_dt'].dt.tz_localize(None)
        
        # Indicator calculations
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
        
        df['don_h'] = df['high'].shift(1).rolling(20).max()
        df['don_l'] = df['low'].shift(1).rolling(20).min()
        
        # 4H macro trend
        df_idx = df.set_index('time_dt')
        df_4h = df_idx.resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna().reset_index()
        df_4h['e20'] = df_4h['close'].ewm(span=20, adjust=False).mean()
        df_4h['e50'] = df_4h['close'].ewm(span=50, adjust=False).mean()
        df_4h['ema_bull'] = df_4h['e20'] > df_4h['e50']
        df_4h['ema_bear'] = df_4h['e20'] < df_4h['e50']
        
        df['h4_time'] = df['time_dt'].dt.floor('4h') - pd.Timedelta(hours=4)
        df['h4_bull'] = df['h4_time'].map(dict(zip(df_4h['time_dt'], df_4h['ema_bull']))).fillna(True)
        df['h4_bear'] = df['h4_time'].map(dict(zip(df_4h['time_dt'], df_4h['ema_bear']))).fillna(True)
        
        pair_dfs[pair] = df
        
        spec = pair_specs[pair]
        p_unit = spec['pip_unit']
        min_sl_dist = spec['min_sl_pips'] * p_unit
        max_sl_dist = spec['max_sl_pips'] * p_unit
        
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
        times = df['time_dt'].values
        
        raw_trades = []
        state = 0
        entry_price, sl_price, tp_price = 0, 0, 0
        entry_idx = 0
        hunting = 0
        hunt_level, hunt_ob_h, hunt_ob_l, hunt_fib_50, hunt_atr, hunt_idx = 0,0,0,0,0,0
        lockout_until = 0
        consec_losses = 0
        last_exit_idx = -999
        
        start_idx = df[df['time_dt'] >= START_DATE].index[0]
        
        for i in range(start_idx, len(df)):
            if state != 0:
                hold = i - entry_idx
                # Subsequent bar exits only (Bug fix)
                if hold >= 1:
                    exit_trig = False
                    exit_type = None
                    exit_price = 0.0
                    
                    if state == 1:
                        if h[i] >= tp_price and l[i] <= sl_price:
                            exit_trig = True
                            exit_type = 'LOSS'
                            exit_price = sl_price
                        elif h[i] >= tp_price:
                            exit_trig = True
                            exit_type = 'WIN'
                            exit_price = tp_price
                        elif l[i] <= sl_price:
                            exit_trig = True
                            exit_type = 'LOSS'
                            exit_price = sl_price
                        elif hold >= 160:
                            exit_trig = True
                            exit_price = c[i]
                            exit_type = 'WIN' if exit_price > entry_price else 'LOSS'
                    elif state == -1:
                        if l[i] <= tp_price and h[i] >= sl_price:
                            exit_trig = True
                            exit_type = 'LOSS'
                            exit_price = sl_price
                        elif l[i] <= tp_price:
                            exit_trig = True
                            exit_type = 'WIN'
                            exit_price = tp_price
                        elif h[i] >= sl_price:
                            exit_trig = True
                            exit_type = 'LOSS'
                            exit_price = sl_price
                        elif hold >= 160:
                            exit_trig = True
                            exit_price = c[i]
                            exit_type = 'WIN' if exit_price < entry_price else 'LOSS'
                            
                    if exit_trig:
                        sl_dist = abs(entry_price - sl_price)
                        sl_pips = sl_dist / p_unit
                        raw_trades.append({
                            'pair': pair,
                            'direction': 'LONG' if state == 1 else 'SHORT',
                            'entry_idx': entry_idx,
                            'entry_time': pd.Timestamp(times[entry_idx]).tz_localize(None) if pd.Timestamp(times[entry_idx]).tzinfo else pd.Timestamp(times[entry_idx]),
                            'entry_price': entry_price,
                            'sl_price': sl_price,
                            'tp_price': tp_price,
                            'exit_idx': i,
                            'exit_time': pd.Timestamp(times[i]).tz_localize(None) if pd.Timestamp(times[i]).tzinfo else pd.Timestamp(times[i]),
                            'exit_price': exit_price,
                            'result': exit_type,
                            'sl_dist': sl_dist,
                            'sl_pips': sl_pips,
                            'hold_bars': hold
                        })
                        state = 0
                        last_exit_idx = i
                        if exit_type == 'WIN':
                            consec_losses = 0
                        else:
                            consec_losses += 1
                            if consec_losses >= 2:
                                lockout_until = i + 48
                                consec_losses = 0
                        continue
                        
            if i < lockout_until or (i - last_exit_idx) < 3:
                continue
                
            hr = hours[i]
            wday = weekdays[i]
            is_fri_pm = (wday == 'Friday') and (hr >= 12)
            in_active_hours = (hr != 21) and not is_fri_pm
            
            slope_thresh = 0.10 * atr[i]
            h1_slope_bull = e20_slope[i] >= slope_thresh
            h1_slope_bear = -e20_slope[i] >= slope_thresh
            
            trend_bull = (c[i] > e50[i]) and (e20[i] > e50[i]) and h1_slope_bull and h4_bull[i]
            trend_bear = (c[i] < e50[i]) and (e20[i] < e50[i]) and h1_slope_bear and h4_bear[i]
            
            long_setup = trend_bull and (c[i] > don_h[i]) and (c[i-1] <= don_h[i-1]) and in_active_hours
            short_setup = trend_bear and (c[i] < don_l[i]) and (c[i-1] >= don_l[i-1]) and in_active_hours
            
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
                if (i - hunt_idx) > 8:
                    hunting = 0
                elif hunting == 1:
                    retrace = (l[i] <= hunt_fib_50) or (l[i] <= hunt_ob_h) or (l[i] <= hunt_level * 1.0005) or (l[i] <= e20[i])
                    rejection = c[i] > o[i]
                    rsi_ok = rsi[i] <= 80.0
                    if retrace and rejection and rsi_ok and in_active_hours:
                        raw_sl = hunt_ob_l - (hunt_atr * 0.50)
                        calc_dist = abs(c[i] - raw_sl)
                        act_sl_dist = min(max(calc_dist, min_sl_dist), max_sl_dist)
                        tent_sl = c[i] - act_sl_dist
                        tent_tp = c[i] + (act_sl_dist * RR_RATIO)
                        
                        # Pre-reached TP guard
                        if h[i] < tent_tp:
                            state = 1
                            hunting = 0
                            entry_price = c[i]
                            entry_idx = i
                            sl_price = tent_sl
                            tp_price = tent_tp
                        else:
                            hunting = 0 # Exhausted
                elif hunting == -1:
                    retrace = (h[i] >= hunt_fib_50) or (h[i] >= hunt_ob_l) or (h[i] >= hunt_level * 0.9995) or (h[i] >= e20[i])
                    rejection = c[i] < o[i]
                    rsi_ok = rsi[i] >= 20.0
                    if retrace and rejection and rsi_ok and in_active_hours:
                        raw_sl = hunt_ob_h + (hunt_atr * 0.50)
                        calc_dist = abs(raw_sl - c[i])
                        act_sl_dist = min(max(calc_dist, min_sl_dist), max_sl_dist)
                        tent_sl = c[i] + act_sl_dist
                        tent_tp = c[i] - (act_sl_dist * RR_RATIO)
                        
                        # Pre-reached TP guard
                        if l[i] > tent_tp:
                            state = -1
                            hunting = 0
                            entry_price = c[i]
                            entry_idx = i
                            sl_price = tent_sl
                            tp_price = tent_tp
                        else:
                            hunting = 0 # Exhausted
                            
        pair_signals[pair] = raw_trades
        
    # Helper: calculate lot size and monetary risk
    def calculate_lots_and_risk(pair, balance, entry_price, sl_dist, sl_pips):
        dollar_risk = balance * RISK_PCT
        spec = pair_specs[pair]
        
        if spec.get('gold'):
            # Gold: $100 / lot per $1 move
            # lots = dollar_risk / (sl_dist * 100)
            lots = math.floor((dollar_risk / (sl_dist * 100.0)) * 100.0) / 100.0
            lots = max(0.01, lots)
            actual_risk = lots * 100.0 * sl_dist
            nominal_value = lots * 100.0 * entry_price
        elif spec.get('usd_quote'):
            # Quote USD (EURUSD, GBPUSD, AUDUSD, NZDUSD): $10 / pip / lot
            # lots = dollar_risk / (sl_pips * 10)
            lots = math.floor((dollar_risk / (sl_pips * 10.0)) * 100.0) / 100.0
            lots = max(0.01, lots)
            actual_risk = lots * sl_pips * 10.0
            nominal_value = lots * 100000.0 * entry_price
        elif spec.get('jpy'):
            # USDJPY: pip = 0.01, value = 1000 / USDJPY rate
            pip_val = 1000.0 / entry_price
            lots = math.floor((dollar_risk / (sl_pips * pip_val)) * 100.0) / 100.0
            lots = max(0.01, lots)
            actual_risk = lots * sl_pips * pip_val
            nominal_value = lots * 100000.0
        else:
            # USDCAD, USDCHF: pip = 0.0001, value = 10 / rate
            pip_val = 10.0 / entry_price
            lots = math.floor((dollar_risk / (sl_pips * pip_val)) * 100.0) / 100.0
            lots = max(0.01, lots)
            actual_risk = lots * sl_pips * pip_val
            nominal_value = lots * 100000.0
            
        return lots, actual_risk, nominal_value

    def calculate_trade_pnl(pair, trade, lots, entry_price, exit_price):
        spec = pair_specs[pair]
        dir_mult = 1.0 if trade['direction'] == 'LONG' else -1.0
        price_diff = (exit_price - entry_price) * dir_mult
        
        if spec.get('gold'):
            gross_pnl = lots * 100.0 * price_diff
            costs = lots * 100.0 * spec['cost_oz']
        elif spec.get('usd_quote'):
            pips = price_diff / spec['pip_unit']
            gross_pnl = lots * pips * 10.0
            costs = lots * spec['cost_pips'] * 10.0
        elif spec.get('jpy'):
            pips = price_diff / spec['pip_unit']
            pip_val = 1000.0 / exit_price
            gross_pnl = lots * pips * pip_val
            costs = lots * spec['cost_pips'] * pip_val
        else:
            pips = price_diff / spec['pip_unit']
            pip_val = 10.0 / exit_price
            gross_pnl = lots * pips * pip_val
            costs = lots * spec['cost_pips'] * pip_val
            
        net_pnl = gross_pnl - costs
        return gross_pnl, costs, net_pnl

    # -------------------------------------------------------------
    # 2. MODEL A: INDEPENDENT PAIR SIMULATION ($5,000 PER PAIR)
    # -------------------------------------------------------------
    model_a_results = {}
    for pair in pairs:
        trades = pair_signals[pair]
        bal = STARTING_BALANCE
        peak_bal = STARTING_BALANCE
        cur_day = None
        day_start = STARTING_BALANCE
        max_daily_dd = 0.0
        max_overall_dd = 0.0
        wins, losses = 0, 0
        pnl_list = []
        r_list = []
        
        for tr in trades:
            b_date = tr['exit_time'].date()
            if b_date != cur_day:
                cur_day = b_date
                day_start = bal
                
            lots, risk_dlr, _ = calculate_lots_and_risk(pair, bal, tr['entry_price'], tr['sl_dist'], tr['sl_pips'])
            gross, cost, net = calculate_trade_pnl(pair, tr, lots, tr['entry_price'], tr['exit_price'])
            
            bal += net
            peak_bal = max(peak_bal, bal)
            r_mult = net / risk_dlr if risk_dlr > 0 else 0
            
            d_dd = (day_start - bal) / day_start if day_start > 0 else 0
            max_daily_dd = max(max_daily_dd, d_dd)
            
            ov_dd = (peak_bal - bal) / peak_bal if peak_bal > 0 else 0
            max_overall_dd = max(max_overall_dd, ov_dd)
            
            if tr['result'] == 'WIN':
                wins += 1
            else:
                losses += 1
            pnl_list.append(net)
            r_list.append(r_mult)
            
        model_a_results[pair] = {
            'trades': len(trades),
            'wins': wins,
            'losses': losses,
            'win_rate': (wins / len(trades) * 100) if trades else 0,
            'net_pnl': bal - STARTING_BALANCE,
            'ending_bal': bal,
            'return_pct': ((bal - STARTING_BALANCE) / STARTING_BALANCE) * 100,
            'net_r': sum(r_list),
            'max_daily_dd_pct': max_daily_dd * 100,
            'max_overall_dd_pct': max_overall_dd * 100,
            'profit_factor': (sum(p for p in pnl_list if p > 0) / abs(sum(p for p in pnl_list if p < 0))) if any(p < 0 for p in pnl_list) else 99.0
        }

    # -------------------------------------------------------------
    # 3. MODEL B: UNIFIED PORTFOLIO SIMULATION (ONE $5,000 ACCOUNT)
    # -------------------------------------------------------------
    # Build complete chronological event stream across all pairs
    # Events can be:
    # 'ENTRY': A pair triggers an entry
    # 'EXIT': A pair triggers an exit
    
    # We also evaluate hourly floating mark-to-market across all active pairs
    # Create synchronized hourly time grid from START_DATE to end
    all_times = sorted(list(set(pair_dfs['EURUSD'][pair_dfs['EURUSD']['time_dt'] >= START_DATE]['time_dt'])))
    
    def simulate_unified_portfolio(pair_subset, stress_cost_mult=1.0, slippage_pips=0.0):
        # We step hour by hour through all_times
        balance = STARTING_BALANCE
        equity = STARTING_BALANCE
        peak_equity = STARTING_BALANCE
        peak_balance = STARTING_BALANCE
        
        cur_day = None
        day_start_balance = STARTING_BALANCE
        day_start_equity = STARTING_BALANCE
        
        open_positions = {} # pair -> dict of position info
        closed_trades_ledger = []
        hourly_records = []
        
        daily_dd_breached = False
        overall_dd_breached = False
        account_failed = False
        failure_time = None
        failure_reason = ""
        pre_failure_trade_count = 0
        
        # Pre-index pair trades by entry_time and exit_time
        entries_by_time = {}
        for pair in pair_subset:
            for tr in pair_signals[pair]:
                t_ent = tr['entry_time']
                entries_by_time.setdefault(t_ent, []).append(tr)
                
        for t_curr in all_times:
            bar_date = t_curr.date()
            if bar_date != cur_day:
                cur_day = bar_date
                day_start_balance = balance
                day_start_equity = equity
                
            # 1. Check EXITS at this candle
            pairs_to_remove = []
            for pair, pos in open_positions.items():
                if pos['exit_time'] == t_curr:
                    # Execute Exit
                    tr = pos['raw_trade']
                    exit_price = tr['exit_price']
                    
                    # Apply slippage if stress testing
                    if slippage_pips > 0:
                        spec = pair_specs[pair]
                        slip_dist = slippage_pips * spec['pip_unit']
                        dir_mult = 1.0 if pos['direction'] == 'LONG' else -1.0
                        exit_price = exit_price - (slip_dist * dir_mult) # Adverse
                        
                    gross_pnl, base_costs, _ = calculate_trade_pnl(pair, tr, pos['lots'], pos['entry_price'], exit_price)
                    total_costs = base_costs * stress_cost_mult
                    net_pnl = gross_pnl - total_costs
                    r_mult = net_pnl / pos['actual_risk'] if pos['actual_risk'] > 0 else 0
                    
                    balance_before = balance
                    balance += net_pnl
                    peak_balance = max(peak_balance, balance)
                    
                    d_dd_bal = max(0.0, (day_start_balance - balance) / day_start_balance * 100.0) if day_start_balance > 0 else 0.0
                    ov_dd_bal = max(0.0, (5000.0 - balance) / 5000.0 * 100.0)
                    
                    closed_trades_ledger.append({
                        'trade_idx': len(closed_trades_ledger) + 1,
                        'timestamp': str(pos['entry_time']),
                        'pair': pair,
                        'direction': pos['direction'],
                        'entry': pos['entry_price'],
                        'sl': pos['sl_price'],
                        'tp': pos['tp_price'],
                        'lots': pos['lots'],
                        'risk_dollars': pos['actual_risk'],
                        'exit_time': str(t_curr),
                        'exit_price': exit_price,
                        'result': tr['result'],
                        'gross_pnl': gross_pnl,
                        'costs': total_costs,
                        'net_pnl': net_pnl,
                        'balance': balance,
                        'equity': balance, # at exit moment before new opens
                        'open_pos_count': len(open_positions) - 1,
                        'daily_dd_pct': d_dd_bal,
                        'overall_dd_pct': ov_dd_bal,
                        'r_mult': r_mult,
                        'account_failed': account_failed
                    })
                    
                    pairs_to_remove.append(pair)
                    
            for p in pairs_to_remove:
                del open_positions[p]
                
            # 2. Check ENTRIES at this candle
            if t_curr in entries_by_time:
                for tr in entries_by_time[t_curr]:
                    pair = tr['pair']
                    if pair not in open_positions: # One trade per pair
                        lots, actual_risk, nominal_val = calculate_lots_and_risk(pair, balance, tr['entry_price'], tr['sl_dist'], tr['sl_pips'])
                        open_positions[pair] = {
                            'pair': pair,
                            'direction': tr['direction'],
                            'entry_time': tr['entry_time'],
                            'entry_price': tr['entry_price'],
                            'sl_price': tr['sl_price'],
                            'tp_price': tr['tp_price'],
                            'exit_time': tr['exit_time'],
                            'lots': lots,
                            'actual_risk': actual_risk,
                            'nominal_val': nominal_val,
                            'raw_trade': tr
                        }
                        
            # 3. Calculate HOURLY MARK-TO-MARKET & OPEN RISK METRICS
            floating_pnl = 0.0
            total_open_risk = 0.0
            total_nominal_exp = 0.0
            net_usd_exposure = 0.0 # Positive = Long USD, Negative = Short USD
            
            for pair, pos in open_positions.items():
                df_p = pair_dfs[pair]
                row = df_p[df_p['time_dt'] == t_curr]
                c_now = row['close'].values[0] if len(row) > 0 else pos['entry_price']
                
                # Floating gross pnl
                gross_float, c_float, _ = calculate_trade_pnl(pair, pos['raw_trade'], pos['lots'], pos['entry_price'], c_now)
                floating_pnl += (gross_float - c_float * stress_cost_mult)
                total_open_risk += pos['actual_risk']
                total_nominal_exp += pos['nominal_val']
                
                # USD exposure
                spec = pair_specs[pair]
                dir_factor = 1.0 if pos['direction'] == 'LONG' else -1.0
                usd_contribution = spec['usd_dir'] * dir_factor * pos['nominal_val']
                net_usd_exposure += usd_contribution
                
            equity = balance + floating_pnl
            peak_equity = max(peak_equity, equity)
            margin_used = total_nominal_exp / LEVERAGE
            
            daily_loss_bal = day_start_balance - balance
            daily_loss_eq = day_start_equity - equity
            
            daily_dd_bal_pct = (daily_loss_bal / day_start_balance * 100.0) if day_start_balance > 0 else 0.0
            daily_dd_eq_pct = (daily_loss_eq / day_start_equity * 100.0) if day_start_equity > 0 else 0.0
            
            overall_loss_bal = 5000.0 - balance
            overall_loss_eq = 5000.0 - equity
            overall_dd_bal_pct = (overall_loss_bal / 5000.0 * 100.0)
            overall_dd_eq_pct = (overall_loss_eq / 5000.0 * 100.0)
            
            # Check hard drawdown breaches
            if not account_failed:
                if daily_dd_eq_pct >= 3.0:
                    daily_dd_breached = True
                    account_failed = True
                    failure_time = t_curr
                    failure_reason = f"DAILY DRAWDOWN BREACH: Equity dropped {daily_dd_eq_pct:.2f}% (Loss: ${daily_loss_eq:.2f} > $150 limit) on {t_curr}"
                    pre_failure_trade_count = len(closed_trades_ledger)
                elif overall_dd_eq_pct >= 8.0:
                    overall_dd_breached = True
                    account_failed = True
                    failure_time = t_curr
                    failure_reason = f"OVERALL DRAWDOWN BREACH: Equity dropped {overall_dd_eq_pct:.2f}% (Balance: ${balance:.2f}, Equity: ${equity:.2f} < $4,600 floor) on {t_curr}"
                    pre_failure_trade_count = len(closed_trades_ledger)
                    
            hourly_records.append({
                'time': t_curr,
                'balance': balance,
                'equity': equity,
                'floating_pnl': floating_pnl,
                'open_positions': len(open_positions),
                'total_open_risk': total_open_risk,
                'open_risk_pct': (total_open_risk / balance * 100.0) if balance > 0 else 0,
                'nominal_exposure': total_nominal_exp,
                'margin_used': margin_used,
                'margin_level_pct': (equity / margin_used * 100.0) if margin_used > 0 else 9999.0,
                'net_usd_exposure': net_usd_exposure,
                'daily_dd_bal_pct': max(0.0, daily_dd_bal_pct),
                'daily_dd_eq_pct': max(0.0, daily_dd_eq_pct),
                'overall_dd_bal_pct': max(0.0, overall_dd_bal_pct),
                'overall_dd_eq_pct': max(0.0, overall_dd_eq_pct)
            })
            
        df_hourly = pd.DataFrame(hourly_records)
        df_ledger = pd.DataFrame(closed_trades_ledger)
        
        return {
            'ledger': df_ledger,
            'hourly': df_hourly,
            'ending_balance': balance,
            'ending_equity': equity,
            'net_profit': balance - STARTING_BALANCE,
            'return_pct': ((balance - STARTING_BALANCE) / STARTING_BALANCE) * 100.0,
            'total_trades': len(df_ledger),
            'pre_failure_trades': pre_failure_trade_count,
            'account_failed': account_failed,
            'failure_time': failure_time,
            'failure_reason': failure_reason,
            'max_balance_dd_pct': df_hourly['overall_dd_bal_pct'].max(),
            'max_equity_dd_pct': df_hourly['overall_dd_eq_pct'].max(),
            'max_daily_bal_dd_pct': df_hourly['daily_dd_bal_pct'].max(),
            'max_daily_eq_dd_pct': df_hourly['daily_dd_eq_pct'].max(),
            'peak_simultaneous_trades': df_hourly['open_positions'].max(),
            'avg_simultaneous_trades': df_hourly['open_positions'].mean(),
            'peak_open_risk_pct': df_hourly['open_risk_pct'].max(),
            'avg_open_risk_pct': df_hourly[df_hourly['open_positions'] > 0]['open_risk_pct'].mean(),
            'peak_nominal_exposure': df_hourly['nominal_exposure'].max(),
            'peak_margin_used': df_hourly['margin_used'].max(),
            'peak_net_usd_exposure': df_hourly['net_usd_exposure'].abs().max()
        }

    # Run Model B for:
    # 1) Full 8-Pair Portfolio (All Pairs Listed)
    res_8pairs = simulate_unified_portfolio(pairs)
    # 2) Whitelisted 5-Pair Portfolio (Institutional Whitelist)
    res_5pairs = simulate_unified_portfolio(list(whitelisted_set))
    
    # Run Stress Tests on 8-Pair Portfolio
    stress_results = {
        'Scenario A (Normal)': res_8pairs,
        'Scenario B (Spread +50%)': simulate_unified_portfolio(pairs, stress_cost_mult=1.5),
        'Scenario C (Slippage 0.5p)': simulate_unified_portfolio(pairs, slippage_pips=0.5),
        'Scenario D (Spread +50% & Slip)': simulate_unified_portfolio(pairs, stress_cost_mult=1.5, slippage_pips=0.5)
    }
    
    return {
        'pair_signals': pair_signals,
        'pair_specs': pair_specs,
        'model_a': model_a_results,
        'res_8pairs': res_8pairs,
        'res_5pairs': res_5pairs,
        'stress': stress_results
    }

if __name__ == '__main__':
    out = run_comprehensive_portfolio_audit()
    print("Simulation complete! Saving cache...")
    with open('archives/portfolio_simulation_output.pkl', 'wb') as f:
        pickle.dump(out, f)
    print("Saved archives/portfolio_simulation_output.pkl successfully.")
