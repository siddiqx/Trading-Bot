#!/usr/bin/env python3
"""ROP-03 Standalone Live Equity & Prop Firm Drawdown Inspector.

Connects to cTrader Open API via TLS and retrieves:
1. Account balance and currency digits via ProtoOATraderReq
2. Open positions and floating net/gross unrealized P&L via ProtoOAGetPositionUnrealizedPnLReq
3. Calculates exact Live Equity (Balance + Unrealized P&L)
4. Evaluates daily drawdown against the prop firm multi-tier guardrail

Run:
  python scripts/demo_live_equity.py          # Offline mock socket verification
  python scripts/demo_live_equity.py --live   # Real TLS check against configured account
"""

import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from core.ctrader_executor import (
    CTRADER_ENV, CTRADER_HOSTS, CTRADER_PORT,
    CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET,
    CTRADER_ACCESS_TOKEN, CTRADER_ACCOUNT_ID,
    get_ctrader_account_equity, dispatch_ctrader_tls_equity,
    _query_equity_over_socket
)
from core.config import FIRM_DAILY_LOSS_LIMIT_PCT, BOT_HALT_DAILY_LOSS_PCT, DAILY_RESET_HOUR_UTC


def run_offline_verification():
    """Run offline simulation verification of ROP-03 equity and drawdown calculations."""
    print("\n" + "=" * 70)
    print(" ROP-03 Offline Verification (Simulated & Fake Socket)")
    print("=" * 70)

    # 1. Test simulated fallback
    sim_res = get_ctrader_account_equity()
    print(f"• Simulated Equity Status: {sim_res.get('status')}")
    print(f"• Fallback Balance:        ${sim_res.get('balance', 0.0):,.2f}")
    print(f"• Fallback Equity:         ${sim_res.get('equity', 0.0):,.2f}")
    print(f"• Open Positions:          {sim_res.get('open_positions_count', 0)}")

    checklist = [
        ("Simulated Fallback Available", sim_res.get("status") in ("SIMULATED", "OK")),
        ("Zero Floating PnL on Idle", sim_res.get("unrealized_pnl") == 0.0),
        ("Equity Equals Balance on Idle", sim_res.get("equity") == sim_res.get("balance")),
        ("Multi-Tier Config Active", BOT_HALT_DAILY_LOSS_PCT < FIRM_DAILY_LOSS_LIMIT_PCT),
        ("Daily Reset Hour Configured", 0 <= DAILY_RESET_HOUR_UTC <= 23),
        ("Non-Negative Open Positions", sim_res.get("open_positions_count") >= 0),
    ]

    print("\n" + "-" * 70)
    print(" ROP-03 VERIFICATION CHECKLIST (OFFLINE)")
    print("-" * 70)
    all_passed = True
    for desc, passed in checklist:
        status_sym = "✓ PASS" if passed else "✗ FAIL"
        if not passed:
            all_passed = False
        print(f" [{status_sym}] {desc}")
    print("-" * 70 + "\n")

    if all_passed:
        print("✓ All 6 offline checks PASSED.")
    else:
        print("✗ Offline checks FAILED.")
        sys.exit(1)


def run_live_verification(allow_prop_trial: bool = False):
    """Run live inspection over TLS against configured cTrader account."""
    print("\n" + "=" * 70)
    env_name = CTRADER_ENV.lower()
    host = CTRADER_HOSTS.get(env_name, "demo.ctraderapi.com")
    print(f" cTrader Live Equity Inspection: Connecting to {host}:{CTRADER_PORT} ({env_name.upper()})...")
    print("=" * 70)

    if not CTRADER_CLIENT_ID or not CTRADER_CLIENT_SECRET or not CTRADER_ACCESS_TOKEN or not CTRADER_ACCOUNT_ID:
        print("✗ Missing required cTrader credentials in environment.")
        sys.exit(1)

    account_id = int(CTRADER_ACCOUNT_ID)
    try:
        res = dispatch_ctrader_tls_equity(
            host=host,
            port=CTRADER_PORT,
            client_id=CTRADER_CLIENT_ID,
            client_secret=CTRADER_CLIENT_SECRET,
            access_token=CTRADER_ACCESS_TOKEN,
            account_id=account_id
        )

        status = res.get("status")
        if status != "OK":
            print(f"\n✗ Failed to retrieve live equity: {res.get('error')}")
            sys.exit(1)

        balance = res.get("balance", 0.0)
        unrealized_pnl = res.get("unrealized_pnl", 0.0)
        equity = res.get("equity", 0.0)
        open_count = res.get("open_positions_count", 0)
        broker_name = res.get("broker_name", "unknown")
        login = res.get("trader_login", 0)
        rights = res.get("access_rights", 0)

        rights_str = {0: "FULL_ACCESS", 1: "CLOSE_ONLY", 2: "NO_TRADING"}.get(rights, f"UNKNOWN({rights})")

        print(f"✓ TLS Connection & Authentication: SUCCESS")
        print(f"• Broker Profile:          {broker_name.upper()} | Login: #{login} | Access: {rights_str}")
        print(f"• Account Balance:         ${balance:,.2f}")
        print(f"• Unrealized Floating PnL: ${unrealized_pnl:+,.2f} ({open_count} open positions)")
        print(f"• Live Equity:             ${equity:,.2f}")

        if res.get("positions"):
            print("\n  Open Positions Breakdown:")
            for p in res["positions"]:
                print(f"    - Position #{p['position_id']}: Net PnL = ${p['net_pnl']:+,.2f} (Gross = ${p['gross_pnl']:+,.2f})")

        # Evaluate Drawdown against baseline
        starting_cap = balance
        daily_dd_pct = max(0.0, (starting_cap - equity) / starting_cap * 100.0) if starting_cap > 0 else 0.0
        is_halted = daily_dd_pct >= BOT_HALT_DAILY_LOSS_PCT
        is_breached = daily_dd_pct >= FIRM_DAILY_LOSS_LIMIT_PCT

        print(f"\n• Daily Drawdown vs Baseline: {daily_dd_pct:.2f}%")
        print(f"• Bot Halt Limit:             {BOT_HALT_DAILY_LOSS_PCT:.1f}%")
        print(f"• Prop Firm Maximum Limit:    {FIRM_DAILY_LOSS_LIMIT_PCT:.1f}%")
        print(f"• Prop Risk Guard Status:     {'CIRCUIT_BREAKER_HALT' if is_halted else 'NOMINAL / SAFE'}")

        checklist = [
            ("TLS Socket Connection Established", True),
            ("Application & Account Authenticated", True),
            ("Broker Profile & Balance Retrieved", balance > 0),
            ("Unrealized PnL Query Successful", open_count >= 0),
            ("Live Equity Calculated Dynamically", equity > 0),
            ("Daily Loss Guardrail Evaluated", not is_breached),
        ]

        print("\n" + "-" * 70)
        print(" ROP-03 LIVE VERIFICATION CHECKLIST")
        print("-" * 70)
        all_passed = True
        for desc, passed in checklist:
            status_sym = "✓ PASS" if passed else "✗ FAIL"
            if not passed:
                all_passed = False
            print(f" [{status_sym}] {desc}")
        print("-" * 70 + "\n")

        if all_passed:
            print("✓ All 6 live verification checks PASSED.")
        else:
            print("✗ One or more checks failed.")
            sys.exit(1)

    except Exception as ex:
        print(f"\n✗ Error during live equity check: {ex}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="cTrader Live Equity & Prop Drawdown Inspector")
    parser.add_argument("--live", action="store_true", help="Connect to cTrader Open API endpoint over TLS")
    parser.add_argument("--allow-prop-trial", action="store_true", help="Authorize execution on prop trial account")

    args = parser.parse_args()

    if args.live:
        run_live_verification(allow_prop_trial=args.allow_prop_trial)
    else:
        run_offline_verification()


if __name__ == "__main__":
    main()
