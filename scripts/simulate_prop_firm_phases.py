from scripts.simulate_prop_firm_5k import run_prop_firm_simulation

trades = run_prop_firm_simulation()

print("=" * 90)
print("REALISTIC 2-PHASE CHALLENGE & FUNDED PAYOUT PROGRESSION (LAST MONTH)")
print("=" * 90)

# -------------------------------------------------------------
# PHASE 1: Target = +8% (+$400 on $5,000)
# -------------------------------------------------------------
print("\n--- PHASE 1: $5,000 ACCOUNT (Target: +8% / $5,400) ---")
p1_balance = 5000.0
p1_peak = 5000.0
p1_max_dd = 0.0
p1_passed_idx = None

for idx, t in enumerate(trades, 1):
    risk = p1_balance * 0.01  # 1.0% risk per trade
    pnl = t['exit_r'] * risk
    p1_balance += pnl
    if p1_balance > p1_peak:
        p1_peak = p1_balance
    dd = (p1_peak - p1_balance) / p1_peak * 100.0
    if dd > p1_max_dd:
        p1_max_dd = dd
    
    dt_str = t['exit_time'].strftime('%Y-%m-%d %H:%M')
    print(f"Trade #{idx:2d} | {dt_str} | {t['pair']:<7} {t['direction']:<5} | Exit: {t['exit_r']:+5.2f}R | PnL: {pnl:+7.2f} | Balance: ${p1_balance:7.2f}")
    
    if p1_balance >= 5400.0 and p1_passed_idx is None:
        p1_passed_idx = idx
        print(f"\n>>> PHASE 1 PASSED at Trade #{idx} on {dt_str}! Final Balance: ${p1_balance:.2f} (Max DD: {p1_max_dd:.2f}%) <<<\n")
        break

# -------------------------------------------------------------
# PHASE 2: Starts fresh with $5,000. Target = +5% (+$250)
# -------------------------------------------------------------
print("\n--- PHASE 2: $5,000 ACCOUNT (Target: +5% / $5,250) ---")
p2_balance = 5000.0
p2_peak = 5000.0
p2_max_dd = 0.0
p2_passed_idx = None
remaining_trades = trades[p1_passed_idx:]

for offset, t in enumerate(remaining_trades, 1):
    curr_trade_num = p1_passed_idx + offset
    risk = p2_balance * 0.01
    pnl = t['exit_r'] * risk
    p2_balance += pnl
    if p2_balance > p2_peak:
        p2_peak = p2_balance
    dd = (p2_peak - p2_balance) / p2_peak * 100.0
    if dd > p2_max_dd:
        p2_max_dd = dd
    
    dt_str = t['exit_time'].strftime('%Y-%m-%d %H:%M')
    print(f"Trade #{curr_trade_num:2d} | {dt_str} | {t['pair']:<7} {t['direction']:<5} | Exit: {t['exit_r']:+5.2f}R | PnL: {pnl:+7.2f} | Balance: ${p2_balance:7.2f}")
    
    if p2_balance >= 5250.0 and p2_passed_idx is None:
        p2_passed_idx = curr_trade_num
        print(f"\n>>> PHASE 2 PASSED at Trade #{curr_trade_num} on {dt_str}! Final Balance: ${p2_balance:.2f} (Max DD: {p2_max_dd:.2f}%) <<<\n")
        break

# -------------------------------------------------------------
# FUNDED ACCOUNT: Live Payout Stage with $5,000
# -------------------------------------------------------------
if p2_passed_idx and p2_passed_idx < len(trades):
    print("\n--- FUNDED LIVE ACCOUNT: $5,000 CAPITAL (PAYOUT STAGE) ---")
    funded_balance = 5000.0
    funded_peak = 5000.0
    funded_max_dd = 0.0
    funded_trades = trades[p2_passed_idx:]

    for offset, t in enumerate(funded_trades, 1):
        curr_trade_num = p2_passed_idx + offset
        risk = funded_balance * 0.01
        pnl = t['exit_r'] * risk
        funded_balance += pnl
        if funded_balance > funded_peak:
            funded_peak = funded_balance
        dd = (funded_peak - funded_balance) / funded_peak * 100.0
        if dd > funded_max_dd:
            funded_max_dd = dd
        
        dt_str = t['exit_time'].strftime('%Y-%m-%d %H:%M')
        print(f"Live Trade #{curr_trade_num:2d} | {dt_str} | {t['pair']:<7} {t['direction']:<5} | Exit: {t['exit_r']:+5.2f}R | PnL: {pnl:+7.2f} | Balance: ${funded_balance:7.2f}")

    total_profit = funded_balance - 5000.0
    trader_payout_80 = total_profit * 0.80
    trader_payout_90 = total_profit * 0.90
    print("-" * 90)
    print(f"Funded Live Account Balance: ${funded_balance:.2f}")
    print(f"Total Net Profit Generated:  ${total_profit:.2f} (+{(total_profit/5000.0)*100:.2f}%)")
    print(f"Your Payout (80% split):      ${trader_payout_80:.2f}")
    print(f"Your Payout (90% split):      ${trader_payout_90:.2f}")
    print(f"Max Drawdown on Funded:       {funded_max_dd:.2f}% (Limit: 7.0%)")
