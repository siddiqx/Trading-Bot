import pickle
import pandas as pd
import numpy as np

def run_backtest():
    with open('archives/portfolio_8pairs_cache.pkl', 'rb') as f:
        pairs_data = pickle.load(f)

    results = []

    for pair, df_raw in pairs_data.items():
        df = df_raw.copy()
        if 'time_dt' not in df.columns:
            df['time_dt'] = pd.to_datetime(df['time'], unit='s', utc=True)
        elif df['time_dt'].dt.tz is None:
            df['time_dt'] = df['time_dt'].dt.tz_localize('UTC')
        
        df.sort_values('time_dt', inplace=True)
        df.reset_index(drop=True, inplace=True)

        is_gold = (pair == 'XAUUSD')
        donch_len = 10 if is_gold else 15
        pip = 0.10 if is_gold else (0.01 if 'JPY' in pair else 0.0001)
        min_sl = (60.0 if is_gold else 18.0) * pip
        max_sl = (350.0 if is_gold else 65.0) * pip
        
        # Indicators
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema20_slope'] = df['ema20'] - df['ema20'].shift(2)
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
        rs = gain / (loss + 1e-9)
        df['rsi'] = 100.0 - (100.0 / (1.0 + rs))

        # Simulate trades
        n = len(df)
        active_trade = None
        trades = []
        
        for i in range(50, n):
            row = df.iloc[i]
            prev = df.iloc[i-1]
            
            # Check active trade
            if active_trade is not None:
                pos_dir = active_trade['dir']
                entry = active_trade['entry']
                sl = active_trade['sl']
                tp = active_trade['tp']
                open_idx = active_trade['idx']
                bars_held = i - open_idx
                
                # Outcome check
                if pos_dir == 'LONG':
                    if row['low'] <= sl:
                        trades.append({'res': 'LOSS', 'r': -1.0, 'pips': (sl - entry)/pip, 'time': row['time_dt']})
                        active_trade = None
                    elif row['high'] >= tp:
                        trades.append({'res': 'WIN', 'r': active_trade['rr'], 'pips': (tp - entry)/pip, 'time': row['time_dt']})
                        active_trade = None
                    elif bars_held >= 48 and row['close'] < row['ema20']:
                        # Invalidation exit
                        real_r = (row['close'] - entry) / (entry - sl)
                        trades.append({'res': 'WIN' if real_r > 0 else 'LOSS', 'r': real_r, 'pips': (row['close'] - entry)/pip, 'time': row['time_dt']})
                        active_trade = None
                else:
                    if row['high'] >= sl:
                        trades.append({'res': 'LOSS', 'r': -1.0, 'pips': (entry - sl)/pip, 'time': row['time_dt']})
                        active_trade = None
                    elif row['low'] <= tp:
                        trades.append({'res': 'WIN', 'r': active_trade['rr'], 'pips': (entry - tp)/pip, 'time': row['time_dt']})
                        active_trade = None
                    elif bars_held >= 48 and row['close'] > row['ema20']:
                        real_r = (entry - row['close']) / (sl - entry)
                        trades.append({'res': 'WIN' if real_r > 0 else 'LOSS', 'r': real_r, 'pips': (entry - row['close'])/pip, 'time': row['time_dt']})
                        active_trade = None
                continue
                
            # No active trade -> evaluate signal
            hour = row['time_dt'].hour
            if not (5 <= hour <= 21):
                continue
                
            bull_trend = (row['close'] > row['ema50']) and (row['ema20'] > row['ema50']) and (row['ema20_slope'] > 0)
            bear_trend = (row['close'] < row['ema50']) and (row['ema20'] < row['ema50']) and (row['ema20_slope'] < 0)
            rsi_bull = (40.0 <= row['rsi'] <= 80.0)
            rsi_bear = (20.0 <= row['rsi'] <= 60.0)
            
            long_bo = (row['close'] > row['donch_high']) and (prev['close'] <= prev['donch_high'])
            short_bo = (row['close'] < row['donch_low']) and (prev['close'] >= prev['donch_low'])
            
            if long_bo and bull_trend and rsi_bull:
                entry = row['close']
                ob_low = row['low']
                for k in range(i-1, max(0, i-10), -1):
                    if df.iloc[k]['close'] < df.iloc[k]['open']:
                        ob_low = df.iloc[k]['low']
                        break
                sl_candidate = ob_low - (0.5 * row['atr'])
                sl_dist = max(min_sl, min(max_sl, entry - sl_candidate))
                sl = entry - sl_dist
                tp = entry + (sl_dist * 1.75)
                active_trade = {'dir': 'LONG', 'entry': entry, 'sl': sl, 'tp': tp, 'rr': 1.75, 'idx': i}
                
            elif short_bo and bear_trend and rsi_bear:
                entry = row['close']
                ob_high = row['high']
                for k in range(i-1, max(0, i-10), -1):
                    if df.iloc[k]['close'] > df.iloc[k]['open']:
                        ob_high = df.iloc[k]['high']
                        break
                sl_candidate = ob_high + (0.5 * row['atr'])
                sl_dist = max(min_sl, min(max_sl, sl_candidate - entry))
                sl = entry + sl_dist
                tp = entry - (sl_dist * 1.75)
                active_trade = {'dir': 'SHORT', 'entry': entry, 'sl': sl, 'tp': tp, 'rr': 1.75, 'idx': i}

        if trades:
            df_tr = pd.DataFrame(trades)
            wins = df_tr[df_tr['r'] > 0]
            losses = df_tr[df_tr['r'] <= 0]
            wr = len(wins) / len(df_tr) * 100
            gross_win = wins['r'].sum()
            gross_loss = abs(losses['r'].sum())
            pf = gross_win / (gross_loss + 1e-9)
            net_r = df_tr['r'].sum()
            
            cum_r = df_tr['r'].cumsum()
            peak = cum_r.cummax()
            dd = peak - cum_r
            max_dd_r = dd.max()
            max_dd_pct = max_dd_r * 0.5
            net_return_pct = net_r * 0.5
            tot_pips = df_tr['pips'].sum()
            
            results.append({
                'Pair': pair,
                'Trades': len(df_tr),
                'WinRate': f'{wr:.1f}%',
                'ProfitFactor': round(pf, 2),
                'Net_R': f'{net_r:+.2f}R',
                'Return_pct': f'{net_return_pct:+.2f}%',
                'Max_DD_pct': f'{max_dd_pct:.2f}%',
                'Total_Pips': f'{tot_pips:+.1f}'
            })

    df_res = pd.DataFrame(results)
    df_res.sort_values('ProfitFactor', ascending=False, inplace=True)
    print(df_res.to_string(index=False))

if __name__ == '__main__':
    run_backtest()
