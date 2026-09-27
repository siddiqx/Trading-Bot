import sys, os, math
import httpx
import pandas as pd
import numpy as np
from datetime import datetime, timezone

def fetch_gold_data():
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = 'https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1h&range=2y'
    r = httpx.get(url, headers=headers)
    data = r.json()
    chart = data['chart']['result'][0]
    ts = chart['timestamp']
    quotes = chart['indicators']['quote'][0]
    df = pd.DataFrame({
        'time': ts,
        'open': quotes['open'],
        'high': quotes['high'],
        'low': quotes['low'],
        'close': quotes['close'],
        'volume': quotes.get('volume', [0]*len(ts))
    }).dropna().reset_index(drop=True)
    df['time_dt'] = pd.to_datetime(df['time'], unit='s', utc=True)
    return df

def run_rigorous_gold_audit():
    df = fetch_gold_data()
    print(f"Loaded {len(df)} 1H Gold bars from {df['time_dt'].min()} to {df['time_dt'].max()}")
    
    # Calculate Strategy Indicators
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

    # 4H resample
    df_idx = df.set_index('time_dt')
    df_4h = df_idx.resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna().reset_index()
    df_4h['e20'] = df_4h['close'].ewm(span=20, adjust=False).mean()
    df_4h['e50'] = df_4h['close'].ewm(span=50, adjust=False).mean()
    df_4h['ema_bull'] = df_4h['e20'] > df_4h['e50']
    df_4h['ema_bear'] = df_4h['e20'] < df_4h['e50']

    df['h4_time'] = df['time_dt'].dt.floor('4h') - pd.Timedelta(hours=4)
    df['h4_bull'] = df['h4_time'].map(dict(zip(df_4h['time_dt'], df_4h['ema_bull']))).fillna(True)
    df['h4_bear'] = df['h4_time'].map(dict(zip(df_4h['time_dt'], df_4h['ema_bear']))).fillna(True)

    # -------------------------------------------------------------
    # SIMULATION WITH STRICT PROP RULES
    # -------------------------------------------------------------
    # Parameters for Gold:
    # 1 Point on Gold = $1.00 price move
    # 1 Standard Lot = 100 oz. Minimum Lot = 0.01 lot.
    # Trading Costs: $0.36 / oz round-turn ($0.20 spread + $0.06 commission + $0.10 slippage)
    
    # Contract specs
    POINT_VALUE_PER_LOT = 100.0 # $100 per $1.00 move on 1.0 lot
    COST_PER_OZ = 0.36          # $0.36 round-turn per ounce ($36/lot)
    
    # Account Rules:
    STARTING_BALANCE = 5000.0
    RISK_PCT = 0.01             # 1% dynamic risk
    MAX_DAILY_DD_PCT = 0.03     # 3% = $150
    MAX_OVERALL_DD_PCT = 0.08   # 8% = $400
    
    # Test on the last 6 months (recent performance focus)
    START_DATE = '2026-03-15'
    
    # Strategy execution:
    # We test both:
    # 1) UNCORRECTED (with same-candle exit bug where entry candle immediately hits TP/SL)
    # 2) CORRECTED (enforcing realistic execution where a trade cannot exit before subsequent candles,
    #    and if entry candle high >= TP or low <= TP, signal is flagged as late/exhausted)
    
    for mode in ['UNCORRECTED_BUGGY', 'CORRECTED_REALISTIC']:
        print("\n" + "="*90)
        print(f"RUNNING PROP ACCOUNT SIMULATION: MODE = {mode}")
        print("="*90)
        
        # In realistic Gold trading, SL is measured in points ($18 - $25)
        # We test with the standard $18 - $25 SL points
        p_unit = 1.00 
        min_sl_dist = 18.0 * p_unit
        max_sl_dist = 25.0 * p_unit
        rr = 1.75
        sl_mult = 0.5
        
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
        entry_price, sl_price, tp_price = 0, 0, 0
        entry_idx = 0
        hunting = 0
        hunt_level, hunt_ob_h, hunt_ob_l, hunt_fib_50, hunt_atr, hunt_idx = 0,0,0,0,0,0
        lockout_until = 0
        consec_losses = 0
        last_exit_idx = -999
        
        # Track account starting strictly on 2026-03-15 with $5,000
        balance = STARTING_BALANCE
        equity = STARTING_BALANCE
        peak_balance = STARTING_BALANCE
        cur_day = None
        day_start_balance = STARTING_BALANCE
        daily_dd_breached = False
        overall_dd_breached = False
        account_failed = False
        breach_info = ""
        
        # Start index at 2026-03-15
        start_idx = df[df['time_dt'] >= START_DATE].index[0]
        
        for i in range(start_idx, len(df)):
            t_bar = df['time_dt'].iloc[i]
            bar_date = t_bar.date()
            
            # Daily reset
            if bar_date != cur_day:
                cur_day = bar_date
                day_start_balance = balance
                
            # If account failed, we do not allow new trades
            if account_failed:
                break
                
            # Check open position exit
            if state != 0:
                hold = i - entry_idx
                can_exit = (hold >= 1) if mode == 'CORRECTED_REALISTIC' else (hold >= 0)
                
                if can_exit:
                    exit_triggered = False
                    exit_type = None
                    exit_price = 0.0
                    
                    if state == 1:
                        if h[i] >= tp_price and l[i] <= sl_price:
                            exit_triggered = True
                            exit_type = 'LOSS'
                            exit_price = sl_price
                        elif h[i] >= tp_price:
                            exit_triggered = True
                            exit_type = 'WIN'
                            exit_price = tp_price
                        elif l[i] <= sl_price:
                            exit_triggered = True
                            exit_type = 'LOSS'
                            exit_price = sl_price
                        elif hold >= 160:
                            exit_triggered = True
                            exit_price = c[i]
                            exit_type = 'WIN' if exit_price > entry_price else 'LOSS'
                    elif state == -1:
                        if l[i] <= tp_price and h[i] >= sl_price:
                            exit_triggered = True
                            exit_type = 'LOSS'
                            exit_price = sl_price
                        elif l[i] <= tp_price:
                            exit_triggered = True
                            exit_type = 'WIN'
                            exit_price = tp_price
                        elif h[i] >= sl_price:
                            exit_triggered = True
                            exit_type = 'LOSS'
                            exit_price = sl_price
                        elif hold >= 160:
                            exit_triggered = True
                            exit_price = c[i]
                            exit_type = 'WIN' if exit_price < entry_price else 'LOSS'
                            
                    if exit_triggered:
                        dir_mult = 1 if state == 1 else -1
                        price_diff = (exit_price - entry_price) * dir_mult
                        sl_dist = abs(entry_price - sl_price)
                        
                        dollar_risk = balance * RISK_PCT
                        oz_size = (dollar_risk / (sl_dist * POINT_VALUE_PER_LOT)) * 100.0
                        lots = math.floor((oz_size / 100.0) * 100.0) / 100.0
                        if lots < 0.01:
                            lots = 0.01
                        actual_oz = lots * 100.0
                        actual_dollar_risk = actual_oz * sl_dist
                        
                        gross_pnl = actual_oz * price_diff
                        costs = actual_oz * COST_PER_OZ
                        net_pnl = gross_pnl - costs
                        r_multiple = net_pnl / actual_dollar_risk if actual_dollar_risk > 0 else 0.0
                        
                        balance_before = balance
                        balance += net_pnl
                        peak_balance = max(peak_balance, balance)
                        
                        daily_loss = day_start_balance - balance
                        daily_dd_pct = (daily_loss / day_start_balance) * 100.0 if day_start_balance > 0 else 0.0
                        
                        overall_loss = STARTING_BALANCE - balance
                        overall_dd_pct = (overall_loss / STARTING_BALANCE) * 100.0
                        
                        trades.append({
                            'trade_num': len(trades) + 1,
                            'date': str(bar_date),
                            'entry_time': str(df['time_dt'].iloc[entry_idx]),
                            'exit_time': str(t_bar),
                            'type': 'LONG' if state == 1 else 'SHORT',
                            'entry_price': entry_price,
                            'sl_price': sl_price,
                            'tp_price': tp_price,
                            'exit_price': exit_price,
                            'lots': lots,
                            'risk_dollars': actual_dollar_risk,
                            'risk_pct': (actual_dollar_risk / balance_before) * 100.0,
                            'result': exit_type,
                            'gross_pnl': gross_pnl,
                            'costs': costs,
                            'net_pnl': net_pnl,
                            'balance': balance,
                            'daily_dd_pct': max(0.0, daily_dd_pct),
                            'overall_dd_pct': max(0.0, overall_dd_pct),
                            'r_mult': r_multiple,
                            'hold_bars': hold
                        })
                        
                        if daily_loss >= (STARTING_BALANCE * MAX_DAILY_DD_PCT):
                            daily_dd_breached = True
                            account_failed = True
                            breach_info = f"FAILED: Daily Drawdown Limit ($150 / 3%) breached on {t_bar}. Daily loss: ${daily_loss:.2f} ({daily_dd_pct:.2f}%)."
                        if balance <= (STARTING_BALANCE * (1.0 - MAX_OVERALL_DD_PCT)):
                            overall_dd_breached = True
                            account_failed = True
                            breach_info = f"FAILED: Overall Drawdown Limit ($400 / 8%) breached on {t_bar}. Account balance: ${balance:.2f}."
                            
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
                    retest = (l[i] <= hunt_level * 1.0005) or (l[i] <= e20[i]) or (l[i] <= hunt_fib_50) or (l[i] <= hunt_ob_h)
                    rejection = (c[i] > o[i])
                    rsi_ok = (rsi[i] <= 78.0)
                    if retest and rejection and rsi_ok and in_active_hours:
                        raw_sl = min(hunt_ob_l, l[i]) - (hunt_atr * sl_mult)
                        sl_dist = min(max(c[i] - raw_sl, min_sl_dist), max_sl_dist)
                        
                        cand_entry = c[i]
                        cand_sl = cand_entry - sl_dist
                        cand_tp = cand_entry + (sl_dist * rr)
                        
                        # TEST D: Did price ALREADY reach TP on this very trigger candle?
                        # If high[i] >= cand_tp, the move already ran before bar close!
                        if mode == 'CORRECTED_REALISTIC' and h[i] >= cand_tp:
                            # Rejected / Missed trade!
                            hunting = 0
                            continue
                            
                        state = 1
                        hunting = 0
                        entry_price = cand_entry
                        entry_idx = i
                        sl_price = cand_sl
                        tp_price = cand_tp
                elif hunting == -1:
                    retest = (h[i] >= hunt_level * 0.9995) or (h[i] >= e20[i]) or (h[i] >= hunt_fib_50) or (h[i] >= hunt_ob_l)
                    rejection = (c[i] < o[i])
                    rsi_ok = (rsi[i] >= 22.0)
                    if retest and rejection and rsi_ok and in_active_hours:
                        raw_sl = max(hunt_ob_h, h[i]) + (hunt_atr * sl_mult)
                        sl_dist = min(max(raw_sl - c[i], min_sl_dist), max_sl_dist)
                        
                        cand_entry = c[i]
                        cand_sl = cand_entry + sl_dist
                        cand_tp = cand_entry - (sl_dist * rr)
                        
                        # TEST D: Did price ALREADY reach TP on this very trigger candle?
                        if mode == 'CORRECTED_REALISTIC' and l[i] <= cand_tp:
                            # Rejected / Missed trade!
                            hunting = 0
                            continue
                            
                        state = -1
                        hunting = 0
                        entry_price = cand_entry
                        entry_idx = i
                        sl_price = cand_sl
                        tp_price = cand_tp
                        
        df_trades = pd.DataFrame(trades)
        print(f"Total Trades Taken: {len(df_trades)}")
        if len(df_trades) > 0:
            df_trades['entry_dt'] = pd.to_datetime(df_trades['entry_time'])
            df_6m = df_trades[df_trades['entry_dt'] >= START_DATE].copy()
            print(f"Trades in Recent 6 Months ({START_DATE} to Present): {len(df_6m)}")
            wins = df_6m[df_6m['result'] == 'WIN']
            losses = df_6m[df_6m['result'] == 'LOSS']
            n_w = len(wins)
            n_l = len(losses)
            wr = (n_w / len(df_6m)) * 100 if len(df_6m) > 0 else 0
            gross_pnl = df_6m['net_pnl'].sum()
            net_r = df_6m['r_mult'].sum()
            print(f"Wins: {n_w} | Losses: {n_l} | Win Rate: {wr:.1f}%")
            print(f"Net PnL: ${gross_pnl:+.2f} | Net R: {net_r:+.2f}R")
            print(f"Max Daily DD Seen: {df_trades['daily_dd_pct'].max():.2f}%")
            print(f"Max Overall DD Seen: {df_trades['overall_dd_pct'].max():.2f}%")
            print(f"Account Breach Status: {breach_info if account_failed else 'SURVIVED BOTH LIMITS'}")
            
            # Print full trades table
            print("\n" + "="*120)
            print("COMPLETE TRADE LOG (Recent 6 Months, Sequential Prop Simulation)")
            print("="*120)
            cols_show = ['trade_num', 'entry_time', 'type', 'entry_price', 'sl_price', 'tp_price', 'exit_time', 'exit_price', 'lots', 'risk_dollars', 'risk_pct', 'result', 'gross_pnl', 'costs', 'net_pnl', 'balance', 'daily_dd_pct', 'overall_dd_pct', 'r_mult']
            print(df_6m[cols_show].to_string(index=False))

            # Week-by-Week Table
            df_6m['week'] = df_6m['entry_dt'].dt.to_period('W').apply(lambda r: f"{r.start_time.strftime('%Y-%m-%d')}/{r.end_time.strftime('%Y-%m-%d')}")
            
            weekly_rows = []
            running_bal = STARTING_BALANCE
            
            for wk, grp in df_6m.groupby('week', sort=False):
                wk_start_bal = running_bal
                wk_trades = len(grp)
                wk_wins = (grp['result'] == 'WIN').sum()
                wk_losses = (grp['result'] == 'LOSS').sum()
                wk_net_r = grp['r_mult'].sum()
                wk_net_pnl = grp['net_pnl'].sum()
                running_bal += wk_net_pnl
                wk_end_bal = running_bal
                wk_return_pct = (wk_net_pnl / wk_start_bal) * 100.0 if wk_start_bal > 0 else 0.0
                wk_max_dd = grp['daily_dd_pct'].max()
                wk_status = "SURVIVED" if wk_max_dd < 3.0 and wk_end_bal >= 4600.0 else "BREACH"
                
                weekly_rows.append({
                    'Week': wk,
                    'Starting Balance': wk_start_bal,
                    'Trades': wk_trades,
                    'Wins': wk_wins,
                    'Losses': wk_losses,
                    'Net R': wk_net_r,
                    'Net P&L': wk_net_pnl,
                    'Ending Balance': wk_end_bal,
                    'Weekly Return': wk_return_pct,
                    'Max DD': wk_max_dd,
                    'Status': wk_status
                })
                
            df_weekly = pd.DataFrame(weekly_rows)
            print("\n" + "="*120)
            print("WEEK-BY-WEEK PERFORMANCE TABLE")
            print("="*120)
            print(df_weekly.to_string(index=False))

if __name__ == '__main__':
    run_rigorous_gold_audit()
