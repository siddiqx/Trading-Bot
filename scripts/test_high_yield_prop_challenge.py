"""
High-Yield Prop Challenge Simulation ($5,000 Goat Funded Trader 2-Step Standard):
Simulates the High-Yield Institutional Portfolio (EURUSD, USDCHF, USDCAD, GBPUSD)
over the 6-month evaluation window (April 1 to October 9, 2026).
Official GFT 2-Step Standard rules:
- Starting Balance: $5,000.00
- Phase 1 Target: +10% ($500.00 / $5,500.00 target)
- Phase 2 Target: +5% ($250.00 / $5,250.00 target)
- Daily Drawdown: 5% ($250.00) from 5:00 PM EST daily rollover
- Maximum Overall Loss: 10% Static ($500.00 floor at $4,500.00)
- Minimum Qualifying Days: 3 days per phase with net profit >= $25.00
- Risk per trade: $40.00 (0.80% equity) and $50.00 (1.00% equity)
"""

import sys
import pickle
import pandas as pd
import numpy as np

sys.path.append('scripts')
from deep_quant_winrate_research import load_data, compute_all_indicators, CONFIGS
from test_high_yield_institutional_portfolio import PAIR_SCHEDULES

def run_high_yield_prop():
    d15, d1h = load_data()
    data = compute_all_indicators(d15, d1h)

    # Core Quad (Top 4 Alpha Leaders: EURUSD, USDCHF, USDCAD, GBPUSD)
    quad_pairs = ["EURUSD", "USDCHF", "USDCAD", "GBPUSD"]
    all_trades = []

    for p in quad_pairs:
        p_cfg = PAIR_SCHEDULES[p]
        df = data[p]
        pip = CONFIGS[p]["pip"]
        spread = CONFIGS[p]["spread"]
        costs = spread + 0.5 + 0.35
        sl_pts = p_cfg["sl_pips"]
        tp_rr = p_cfg["tp_rr"]
        bank_pct = p_cfg["bank_pct"]
        allowed_hrs = set(p_cfg["hours"])
        init_sl = sl_pts * pip

        n = len(df)
        state = 0
        entry_idx = 0
        entry_p, sl_p, tp_p = 0.0, 0.0, 0.0
        partial_taken = False
        partial_r_banked = 0.0

        for i in range(30, n):
            c = df.iloc[i]
            prev = df.iloc[i-1]
            t = c["time"]

            if t < pd.Timestamp("2026-04-01", tz="UTC"): continue
            if t > pd.Timestamp("2026-10-09 23:45:00", tz="UTC"): break

            h, l, close, open_p = float(c["high"]), float(c["low"]), float(c["close"]), float(c["open"])
            rng = (h - l) + 1e-9

            if state != 0:
                hold = i - entry_idx
                if not partial_taken:
                    target_1r = init_sl * 1.0
                    if state == 1 and (h - entry_p) >= target_1r:
                        partial_taken = True
                        partial_r_banked = bank_pct * 1.0
                        sl_p = entry_p + (0.5 * pip)
                    elif state == -1 and (entry_p - l) >= target_1r:
                        partial_taken = True
                        partial_r_banked = bank_pct * 1.0
                        sl_p = entry_p - (0.5 * pip)

                exit_triggered = False
                exit_price = 0.0

                if state == 1:
                    if h >= tp_p and l <= sl_p: exit_triggered = True; exit_price = sl_p
                    elif h >= tp_p: exit_triggered = True; exit_price = tp_p
                    elif l <= sl_p: exit_triggered = True; exit_price = sl_p
                    elif hold >= 160: exit_triggered = True; exit_price = close
                elif state == -1:
                    if l <= tp_p and h >= sl_p: exit_triggered = True; exit_price = sl_p
                    elif l <= tp_p: exit_triggered = True; exit_price = tp_p
                    elif h >= sl_p: exit_triggered = True; exit_price = sl_p
                    elif hold >= 160: exit_triggered = True; exit_price = close

                if exit_triggered:
                    dir_mult = 1 if state == 1 else -1
                    gross_pips = (exit_price - entry_p) * dir_mult / pip
                    net_pips = gross_pips - costs

                    if partial_taken:
                        rem_weight = 1.0 - bank_pct
                        final_r = partial_r_banked + ((net_pips / sl_pts) * rem_weight)
                        final_pips = (sl_pts * 1.0 * bank_pct) + (net_pips * rem_weight)
                    else:
                        final_r = net_pips / sl_pts
                        final_pips = net_pips

                    res = "WIN" if final_r > 0.02 else ("LOSS" if final_r < -0.02 else "BREAKEVEN")
                    all_trades.append({
                        "pair": p,
                        "entry_time": df.iloc[entry_idx]["time"],
                        "exit_time": t,
                        "outcome": res,
                        "realized_r": final_r,
                        "net_pips": final_pips
                    })
                    state = 0
                    continue

            # Signal filtering
            if t.weekday() >= 5: continue
            hr = t.hour
            if hr not in allowed_hrs: continue

            atr = float(c["atr"])
            if float(c["adx"]) < 18.0: continue
            if abs(close - open_p) / rng < 0.45: continue

            plus_di, minus_di = float(c["plus_di"]), float(c["minus_di"])
            h1_bull, h1_bear = bool(c["h1_bull"]), bool(c["h1_bear"])
            h4_bull, h4_bear = bool(c["h4_bull"]), bool(c["h4_bear"])

            # Sweep
            long_ict, short_ict = False, False
            if rng >= 0.45 * atr:
                asia_l = c["asia_low"] if pd.notna(c["asia_low"]) else None
                sw10_l = c["sw10_low"] if pd.notna(c["sw10_low"]) else None
                swept_l = min(l, float(prev["low"]))
                if close > open_p and ((close - l) / rng >= 0.45) and ((asia_l and swept_l < asia_l and close > asia_l) or (sw10_l and swept_l < sw10_l and close > sw10_l)):
                    long_ict = True

                asia_h = c["asia_high"] if pd.notna(c["asia_high"]) else None
                sw10_h = c["sw10_high"] if pd.notna(c["sw10_high"]) else None
                swept_h = max(h, float(prev["high"]))
                if close < open_p and ((h - close) / rng >= 0.45) and ((asia_h and swept_h > asia_h and close < asia_h) or (sw10_h and swept_h > sw10_h and close < sw10_h)):
                    short_ict = True

            # Pullback
            bullish_trend = (close > c["ema50"]) and (c["ema20"] > c["ema50"]) and (c["ema20_slope"] > 0)
            bearish_trend = (close < c["ema50"]) and (c["ema20"] < c["ema50"]) and (c["ema20_slope"] < 0)
            lookback = df.iloc[max(0, i-12):i]
            long_pb = bullish_trend and (lookback["close"] > lookback["donch_high"]).any() and (l <= c["ema20"] <= close) and (close > open_p)
            short_pb = bearish_trend and (lookback["close"] < lookback["donch_low"]).any() and (close <= c["ema20"] <= h) and (close < open_p)

            is_long = ((long_ict and c["rsi"] <= 78.0 and plus_di >= minus_di) or (long_pb and bullish_trend and 38 <= c["rsi"] <= 78 and plus_di >= minus_di)) and h1_bull and h4_bull
            is_short = ((short_ict and c["rsi"] >= 22.0 and minus_di >= plus_di) or (short_pb and bearish_trend and 22 <= c["rsi"] <= 62 and minus_di >= plus_di)) and h1_bear and h4_bear

            if is_long:
                state = 1; entry_idx = i; entry_p = close; sl_p = entry_p - init_sl; tp_p = entry_p + (init_sl * tp_rr); partial_taken = False
            elif is_short:
                state = -1; entry_idx = i; entry_p = close; sl_p = entry_p + init_sl; tp_p = entry_p - (init_sl * tp_rr); partial_taken = False

    tdf = pd.DataFrame(all_trades).sort_values("entry_time").reset_index(drop=True)
    print("="*85)
    print("HIGH-YIELD CORE QUAD PORTFOLIO SUMMARY (EURUSD, USDCHF, USDCAD, GBPUSD)")
    print("="*85)
    tot = len(tdf)
    w = (tdf["outcome"] == "WIN").sum()
    l = (tdf["outcome"] == "LOSS").sum()
    wr = (w / tot) * 100.0
    net_r = tdf["realized_r"].sum()
    net_pips = tdf["net_pips"].sum()
    gw = tdf[tdf["realized_r"] > 0]["realized_r"].sum()
    gl = abs(tdf[tdf["realized_r"] < 0]["realized_r"].sum())
    pf = (gw / gl) if gl > 0 else 99.0

    print(f"Total Trades: {tot} | Wins: {w} | Losses: {l}")
    print(f"WIN RATE: {wr:.2f}% | PROFIT FACTOR: {pf:.2f}")
    print(f"NET RETURN: {net_r:+6.2f} R | NET PIPS: {net_pips:+8.1f} pips")

    print("\n" + "="*85)
    print("GFT $5,000 2-STEP STANDARD CHALLENGE SIMULATION")
    print("="*85)

    for risk_usd in [40.0, 50.0]:
        simulate_prop(tdf, risk_usd)

    for risk_usd in [6.0, 7.0, 8.0]:
        simulate_goat_1k_model(tdf, risk_usd=risk_usd)

def simulate_prop(trades_df, risk_usd):
    balance = 5000.0
    peak_equity = 5000.0
    daily_start_equity = 5000.0
    current_day = None

    phase = "PHASE_1"
    p1_target = 5500.0
    p2_target = 5250.0

    p1_pass_info = None
    p2_pass_info = None
    breached = False
    breach_reason = None

    daily_pnl = 0.0
    qualifying_days = set()
    trades_today = 0
    max_daily_dd = 0.0
    max_overall_dd = 0.0

    p1_trades = 0
    p2_trades = 0
    funded_trades = 0
    funded_profit = 0.0

    for idx, t in trades_df.iterrows():
        t_day = t["entry_time"].strftime("%Y-%m-%d")

        if t_day != current_day:
            if current_day is not None:
                if daily_pnl >= 25.0:
                    qualifying_days.add(current_day)
            current_day = t_day
            daily_start_equity = balance
            daily_pnl = 0.0
            trades_today = 0

        # Cap at 2 trades per day across portfolio
        if trades_today >= 2:
            continue

        r = t["realized_r"]
        trade_pnl = r * risk_usd
        trades_today += 1

        balance += trade_pnl
        daily_pnl += trade_pnl

        if balance > peak_equity: peak_equity = balance
        overall_dd = peak_equity - balance
        if overall_dd > max_overall_dd: max_overall_dd = overall_dd

        curr_daily_dd = daily_start_equity - balance
        if curr_daily_dd > max_daily_dd: max_daily_dd = curr_daily_dd

        if curr_daily_dd >= 250.0:
            breached = True
            breach_reason = f"Daily Drawdown Breach (${curr_daily_dd:.2f} >= $250.00)"
            break
        if balance <= 4500.0:
            breached = True
            breach_reason = f"Maximum Overall Loss Breach (${balance:.2f} <= $4,500.00)"
            break

        if phase == "PHASE_1":
            p1_trades += 1
            if balance >= p1_target:
                all_qual = len(qualifying_days) + (1 if daily_pnl >= 25.0 else 0)
                if all_qual >= 3:
                    phase = "PHASE_2"
                    p1_pass_info = (t["exit_time"], p1_trades, all_qual)
                    balance = 5000.0
                    peak_equity = 5000.0
                    daily_start_equity = 5000.0
                    daily_pnl = 0.0
                    qualifying_days = set()
        elif phase == "PHASE_2":
            p2_trades += 1
            if balance >= p2_target:
                all_qual = len(qualifying_days) + (1 if daily_pnl >= 25.0 else 0)
                if all_qual >= 3:
                    phase = "FUNDED"
                    p2_pass_info = (t["exit_time"], p2_trades, all_qual)
                    balance = 5000.0
                    peak_equity = 5000.0
                    daily_start_equity = 5000.0
                    daily_pnl = 0.0
                    qualifying_days = set()
        elif phase == "FUNDED":
            funded_trades += 1
            funded_profit += trade_pnl

    print(f"\n[Risk: ${risk_usd:.2f} per trade ({risk_usd/50:.2f}% equity)]")
    print(f"  Breached: {breached} {('(' + breach_reason + ')') if breached else ''}")
    print(f"  Max Daily Drawdown: ${max_daily_dd:.2f} / $250.00 ({max_daily_dd/250*100:.1f}%)")
    print(f"  Max Overall Drawdown: ${max_overall_dd:.2f} / $500.00 ({max_overall_dd/500*100:.1f}%)")
    if p1_pass_info:
        print(f"  >>> PHASE 1 PASSED! Date: {p1_pass_info[0]} | Trades: {p1_pass_info[1]} | Qual Days: {p1_pass_info[2]}")
    if p2_pass_info:
        print(f"  >>> PHASE 2 PASSED (FUNDED)! Date: {p2_pass_info[0]} | Trades: {p2_pass_info[1]} | Qual Days: {p2_pass_info[2]}")
        print(f"  >>> FUNDED ACCOUNT LIVE PROFIT: +${funded_profit:.2f} ({funded_trades} funded trades taken)")
    elif phase == "PHASE_2":
        print(f"  Phase 2: In Progress (Bal: ${balance:.2f} / $5,250.00)")

def simulate_goat_1k_model(trades_df: pd.DataFrame, risk_usd: float = 8.0):
    balance = 1000.0
    hwm = 1000.0
    daily_start_equity = 1000.0
    current_day = None
    daily_pnl = 0.0
    trades_today = 0
    max_daily_dd = 0.0
    max_trailing_dd = 0.0
    breached = False
    breach_reason = ""
    daily_pnls = {}

    for idx, t in trades_df.iterrows():
        t_day = t["entry_time"].strftime("%Y-%m-%d")
        if t_day != current_day:
            if current_day is not None:
                daily_pnls[current_day] = daily_pnl
                if balance > hwm:
                    hwm = balance
            current_day = t_day
            daily_start_equity = balance
            daily_pnl = 0.0
            trades_today = 0

        if trades_today >= 2:
            continue

        r = t["realized_r"]
        trade_pnl = r * risk_usd
        trades_today += 1

        balance += trade_pnl
        daily_pnl += trade_pnl

        # Daily DD: $30 (3%)
        curr_daily_dd = daily_start_equity - balance
        if curr_daily_dd > max_daily_dd: max_daily_dd = curr_daily_dd

        # Trailing DD from EOD HWM: $60 (6%)
        trailing_dd = hwm - balance
        if trailing_dd > max_trailing_dd: max_trailing_dd = trailing_dd

        if curr_daily_dd >= 30.0:
            breached = True
            breach_reason = f"Daily Drawdown Breach (${curr_daily_dd:.2f} >= $30.00)"
            break
        if trailing_dd >= 60.0:
            breached = True
            breach_reason = f"Trailing Drawdown Breach (${trailing_dd:.2f} >= $60.00)"
            break

    if current_day and current_day not in daily_pnls:
        daily_pnls[current_day] = daily_pnl

    tot_profit = balance - 1000.0
    pos_days = {k: v for k, v in daily_pnls.items() if v >= 5.0}
    max_day_profit = max([v for v in daily_pnls.values() if v > 0], default=0.0)
    consistency_pct = (max_day_profit / tot_profit * 100.0) if tot_profit > 0 else 0.0

    print(f"\n=====================================================================================")
    print(f"GOAT $1,000 MODEL EVALUATION (Risk: ${risk_usd:.2f}/trade = {risk_usd/10:.2f}%)")
    print(f"=====================================================================================")
    print(f"Final Balance: ${balance:.2f} (Net Profit: ${tot_profit:+.2f})")
    print(f"Breached: {breached} {('(' + breach_reason + ')') if breached else ''}")
    print(f"Max Daily DD: ${max_daily_dd:.2f} / $30.00 ({max_daily_dd/30*100:.1f}%)")
    print(f"Max Trailing DD: ${max_trailing_dd:.2f} / $60.00 ({max_trailing_dd/60*100:.1f}%)")
    print(f"Profitable Days >= $5: {len(pos_days)} (Rule requires min 3)")
    print(f"Top Day Profit: ${max_day_profit:.2f} ({consistency_pct:.1f}% of total profit)")

if __name__ == "__main__":
    run_high_yield_prop()

