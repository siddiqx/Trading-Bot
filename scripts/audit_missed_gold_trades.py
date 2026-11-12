#!/usr/bin/env python3
"""Audit the outcomes of all Gold trades missed due to the lagging 4H moving average filter."""

import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from datetime import datetime, timezone
import pandas as pd
import numpy as np

from satellite.gold_config import (
    GOLD_TICKER, CCRS_USD_THRESHOLD, ACTIVE_TRADING_HOURS,
    CCRS_LOOKBACK_HOURS, CCRS_Z_WINDOW_HOURS, MIN_SL_POINTS, MAX_SL_POINTS,
    ATR_MULTIPLIER, BASE_RISK_REWARD_RATIO, TRANSACTION_COSTS, POINT_VALUE_PER_LOT
)
from satellite.market_scanner_gold import fetch_candles_1h, compute_gold_indicators
from satellite.gold_validator import calculate_gold_position_size
from market_scanner import fetch_candles

print("1. Fetching 60d 1H Forex data for CCRS USD factor...")
forex_pairs = ['EURUSD', 'GBPUSD', 'AUDUSD', 'USDJPY', 'USDCAD', 'USDCHF']
tickers = {'EURUSD': 'EURUSD=X', 'GBPUSD': 'GBPUSD=X', 'AUDUSD': 'AUDUSD=X', 'USDJPY': 'USDJPY=X', 'USDCAD': 'USDCAD=X', 'USDCHF': 'USDCHF=X'}
dfs = {}
for p in forex_pairs:
    d = fetch_candles(tickers[p], '1h', range_days='60d')
    d['time'] = pd.to_datetime(d['time'], utc=True)
    d['close_time'] = d['time'] + pd.Timedelta(hours=1)
    dfs[p] = d.set_index('close_time')['close']
df_fx = pd.DataFrame(dfs).dropna()

lb = CCRS_LOOKBACK_HOURS
z_win = CCRS_Z_WINDOW_HOURS
r_eur = np.log(df_fx['EURUSD'] / df_fx['EURUSD'].shift(lb))
r_gbp = np.log(df_fx['GBPUSD'] / df_fx['GBPUSD'].shift(lb))
r_aud = np.log(df_fx['AUDUSD'] / df_fx['AUDUSD'].shift(lb))
r_jpy = -np.log(df_fx['USDJPY'] / df_fx['USDJPY'].shift(lb))
r_cad = -np.log(df_fx['USDCAD'] / df_fx['USDCAD'].shift(lb))
r_chf = -np.log(df_fx['USDCHF'] / df_fx['USDCHF'].shift(lb))
r_usd = -(r_eur + r_gbp + r_aud + r_jpy + r_cad + r_chf) / 6.0
curr_ret = pd.DataFrame({'EUR': r_eur, 'GBP': r_gbp, 'AUD': r_aud, 'JPY': r_jpy, 'CAD': r_cad, 'CHF': r_chf, 'USD': r_usd})
z_scores = (curr_ret - curr_ret.rolling(z_win).mean()) / (curr_ret.rolling(z_win).std() + 1e-9)
z_usd_series = z_scores['USD']

print("2. Fetching 30d 1H Gold data...")
df_gold = fetch_candles_1h(GOLD_TICKER, range_days='30d')
df_gold_ind = compute_gold_indicators(df_gold)

# Sequential simulation where only 1 Gold trade is open at a time
active_trade = None
completed_trades = []
balance = 5000.0
peak_balance = 5000.0
costs_per_oz = TRANSACTION_COSTS['total_points']  # $0.36/oz

for i in range(50, len(df_gold_ind)):
    cur_bar = df_gold_ind.iloc[i]
    prev_bar = df_gold_ind.iloc[i-1]
    bar_time = cur_bar['time_dt']

    # 1. Manage active trade exits first if any
    if active_trade is not None:
        tr = active_trade
        dir_mult = 1 if tr['dir'] == 'LONG' else -1
        hit_tp = False
        hit_sl = False

        if tr['dir'] == 'LONG':
            if cur_bar['low'] <= tr['sl_price']:
                hit_sl = True
            if cur_bar['high'] >= tr['tp_price']:
                hit_tp = True
        else:
            if cur_bar['high'] >= tr['sl_price']:
                hit_sl = True
            if cur_bar['low'] <= tr['tp_price']:
                hit_tp = True

        if hit_sl and hit_tp:
            hit_tp = False

        hold_hours = (bar_time - tr['entry_time']).total_seconds() / 3600.0
        is_timeout = hold_hours >= 48.0

        if hit_tp:
            exit_price = tr['tp_price']
            outcome = 'WIN'
        elif hit_sl:
            exit_price = tr['sl_price']
            outcome = 'LOSS'
        elif is_timeout:
            exit_price = cur_bar['close']
            outcome = 'WIN' if (exit_price - tr['entry_price']) * dir_mult > 0 else 'LOSS'
        else:
            exit_price = None

        if exit_price is not None:
            price_diff = (exit_price - tr['entry_price']) * dir_mult
            oz = tr['lots'] * 100.0
            gross_pnl = oz * price_diff
            net_pnl = gross_pnl - (oz * costs_per_oz)
            r_val = net_pnl / tr['risk_usd']
            balance += net_pnl
            peak_balance = max(peak_balance, balance)

            completed_trades.append({
                'entry_time': tr['entry_time'],
                'exit_time': bar_time,
                'dir': tr['dir'],
                'entry': tr['entry_price'],
                'exit': exit_price,
                'sl': tr['sl_price'],
                'tp': tr['tp_price'],
                'lots': tr['lots'],
                'risk_usd': tr['risk_usd'],
                'net_pnl': net_pnl,
                'r': r_val,
                'outcome': outcome,
                'trigger': tr['trigger'],
                'hold_h': hold_hours,
                'blocked_by_h4': tr['blocked_by_h4'],
                'balance': balance
            })
            active_trade = None

    # 2. Check for fresh signal entry if no active trade
    if active_trade is None:
        if bar_time.hour not in ACTIVE_TRADING_HOURS:
            continue
        past_z = z_usd_series[z_usd_series.index <= cur_bar['close_time']]
        if past_z.empty:
            continue
        z_usd = past_z.iloc[-1]
        is_long = z_usd <= -CCRS_USD_THRESHOLD
        is_short = z_usd >= CCRS_USD_THRESHOLD
        if not is_long and not is_short:
            continue

        direction = 'LONG' if is_long else 'SHORT'
        cur_c = cur_bar['close']
        cur_o = cur_bar['open']
        cur_l = cur_bar['low']
        cur_h = cur_bar['high']
        cur_atr = cur_bar['atr14']

        trigger = False
        trigger_type = ''
        if is_long:
            tested_ema = (cur_l <= cur_bar['ema20'] * 1.0005) and (cur_c > cur_o)
            swept_low = (cur_l < prev_bar['donch_l10']) and (cur_c > prev_bar['donch_l10'])
            rsi_ok = cur_bar['rsi14'] <= 75.0
            if (tested_ema or swept_low) and rsi_ok:
                trigger = True
                trigger_type = 'EMA20' if tested_ema else 'Donchian'
            blocked_by_h4 = not cur_bar['bull_4h']
        else:
            tested_ema = (cur_h >= cur_bar['ema20'] * 0.9995) and (cur_c < cur_o)
            swept_high = (cur_h > prev_bar['donch_h10']) and (cur_c < prev_bar['donch_h10'])
            rsi_ok = cur_bar['rsi14'] >= 25.0
            if (tested_ema or swept_high) and rsi_ok:
                trigger = True
                trigger_type = 'EMA20' if tested_ema else 'Donchian'
            blocked_by_h4 = not cur_bar['bear_4h']

        if not trigger:
            continue

        sl_points = min(max(cur_atr * ATR_MULTIPLIER, MIN_SL_POINTS), MAX_SL_POINTS)
        tp_points = sl_points * BASE_RISK_REWARD_RATIO

        lots, risk_usd = calculate_gold_position_size(account_equity=balance, risk_pct=0.50, sl_points=sl_points)
        if lots <= 0.0:
            continue

        sl_price = cur_c - sl_points if direction == 'LONG' else cur_c + sl_points
        tp_price = cur_c + tp_points if direction == 'LONG' else cur_c - tp_points

        active_trade = {
            'entry_time': bar_time,
            'dir': direction,
            'entry_price': cur_c,
            'sl_price': sl_price,
            'tp_price': tp_price,
            'sl_points': sl_points,
            'tp_points': tp_points,
            'lots': lots,
            'risk_usd': risk_usd,
            'trigger': trigger_type,
            'blocked_by_h4': blocked_by_h4
        }

df_res = pd.DataFrame(completed_trades)
print("\n" + "="*80)
print(f"TOTAL SEQUENTIAL GOLD TRADES AUDIT (Without Lagging H4 Filter): {len(df_res)}")
print("="*80)
wins = df_res[df_res['outcome'] == 'WIN']
losses = df_res[df_res['outcome'] == 'LOSS']
wr = len(wins) / len(df_res) * 100 if len(df_res) > 0 else 0.0
net_pnl = df_res['net_pnl'].sum() if len(df_res) > 0 else 0.0
gross_win = wins['net_pnl'].sum() if len(wins) > 0 else 0.0
gross_loss = abs(losses['net_pnl'].sum()) if len(losses) > 0 else 0.0
pf = gross_win / gross_loss if gross_loss > 0 else 999.0

print(f"Overall Gold Performance:")
print(f"  Trades: {len(df_res)} | Wins: {len(wins)} | Losses: {len(losses)} | WinRate: {wr:.1f}%")
print(f"  Gross Profit: ${gross_win:.2f} | Gross Loss: ${gross_loss:.2f}")
print(f"  Net PnL: ${net_pnl:+.2f} | Profit Factor: {pf:.2f}")

blocked_trades = df_res[df_res['blocked_by_h4'] == True]
b_wins = blocked_trades[blocked_trades['outcome'] == 'WIN']
b_losses = blocked_trades[blocked_trades['outcome'] == 'LOSS']
b_wr = len(b_wins) / len(blocked_trades) * 100 if len(blocked_trades) > 0 else 0.0
b_net_pnl = blocked_trades['net_pnl'].sum() if len(blocked_trades) > 0 else 0.0
b_gw = b_wins['net_pnl'].sum() if len(b_wins) > 0 else 0.0
b_gl = abs(b_losses['net_pnl'].sum()) if len(b_losses) > 0 else 0.0
b_pf = b_gw / b_gl if b_gl > 0 else 999.0

print("\n" + "="*80)
print(f"RESULTS OF SPECIFICALLY THE TRADES BLOCKED BY H4 FILTER:")
print("="*80)
print(f"  Missed Trades: {len(blocked_trades)} | Wins: {len(b_wins)} | Losses: {len(b_losses)} | WinRate: {b_wr:.1f}%")
print(f"  Gross Profit of Missed Trades: ${b_gw:.2f}")
print(f"  Gross Loss of Missed Trades:   ${b_gl:.2f}")
print(f"  Net PnL of Missed Trades:      ${b_net_pnl:+.2f} | Profit Factor: {b_pf:.2f}")

print("\n" + "-"*80)
print("CHRONOLOGICAL LOG OF ALL MISSED TRADES (BLOCKED BY H4):")
print("-"*80)
for idx, r in blocked_trades.iterrows():
    pnl_str = f"${r['net_pnl']:+6.2f}"
    r_str = f"{r['r']:+5.2f}R"
    print(f"{r['entry_time'].strftime('%Y-%m-%d %H:%M')} -> {r['exit_time'].strftime('%m-%d %H:%M')} | {r['dir']:<5} @ ${r['entry']:.2f} -> ${r['exit']:.2f} | {r['outcome']:<4} | Net: {pnl_str} ({r_str}) | {r['trigger']}")
print("="*80 + "\n")
