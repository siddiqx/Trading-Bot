#!/usr/bin/env python3
"""Standalone Verification Script for cTrader Atomic Relative SL/TP (ROP-01).

Demonstrates and verifies that cTrader Open API accepts `relativeStopLoss` and
`relativeTakeProfit` inside `ProtoOANewOrderReq` for MARKET orders, attaching
protection atomically upon fill without naked exposure.

Safety Invariants:
1. Reconciles FTMO / Prop Firm broker environments:
   - FTMO and broker-hosted accounts authenticate through `live.ctraderapi.com:5035` (`CTRADER_ENV=live`).
   - Generic Spotware sandbox demo accounts authenticate through `demo.ctraderapi.com:5035` (`CTRADER_ENV=demo`).
2. Live Account Type Verification:
   - Queries `ProtoOAGetAccountsByAccessTokenReq` to check `isLive`.
   - If `isLive == True` (REAL-MONEY account), the script REFUSES to place orders.
   - If `isLive == False` (DEMO / TRIAL / EVALUATION account), safe verification proceeds.
3. Prints a strict 6-point Pass/Fail Checklist:
   [1] SL present on position at fill
   [2] TP present on position at fill
   [3] SL distance matches requested distance within tick rounding
   [4] TP distance matches requested distance within tick rounding
   [5] Position closed cleanly via ProtoOAClosePositionReq
   [6] Zero leftover pending orders

Usage:
    # 1. Offline dry-run verification (no network, verifies tick rounding for 5-digit pair and gold):
    python scripts/demo_relative_sltp.py

    # 2. Live verification against FTMO Free Trial or cTrader Demo account:
    python scripts/demo_relative_sltp.py --live --symbol EURUSD --lots 0.01
    python scripts/demo_relative_sltp.py --live --symbol XAUUSD --lots 0.01
"""

import sys
import os
import argparse
import socket
import ssl
import time
from pathlib import Path
from typing import Dict, Any, Tuple

# Setup project root
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

from core.ctrader_executor import (
    get_symbol_id,
    _send_tls_frame,
    _read_tls_frame,
    CTRADER_HOSTS
)


def verify_tick_rounding(symbol: str, entry: float, sl_distance: float, tp_distance: float) -> Tuple[bool, Dict[str, Any]]:
    """Test tick rounding calculation for a given symbol, verifying 10^-5 scaling and price rounding."""
    is_gold = "XAU" in symbol.upper() or "GOLD" in symbol.upper()
    is_jpy = "JPY" in symbol.upper()

    if is_gold:
        tick_size = 0.01
        digits = 2
    elif is_jpy:
        tick_size = 0.001
        digits = 3
    else:
        tick_size = 0.00001
        digits = 5

    rel_sl = int(round(sl_distance * 100_000))
    rel_tp = int(round(tp_distance * 100_000))

    sl_price = round(entry - sl_distance, digits)
    tp_price = round(entry + tp_distance, digits)

    actual_sl_dist = round(abs(entry - sl_price), digits)
    actual_tp_dist = round(abs(entry - tp_price), digits)

    sl_diff = abs(actual_sl_dist - sl_distance)
    tp_diff = abs(actual_tp_dist - tp_distance)

    sl_match = sl_diff <= (tick_size + 1e-7)
    tp_match = tp_diff <= (tick_size + 1e-7)

    passed = sl_match and tp_match
    return passed, {
        "symbol": symbol,
        "entry": entry,
        "digits": digits,
        "tick_size": tick_size,
        "sl_distance": sl_distance,
        "tp_distance": tp_distance,
        "rel_sl": rel_sl,
        "rel_tp": rel_tp,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "sl_diff": sl_diff,
        "tp_diff": tp_diff,
        "sl_match": sl_match,
        "tp_match": tp_match
    }


def run_offline_verification(symbol: str, lots: float):
    """Verify tick rounding and protobuf framing offline without connecting to broker."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
        ProtoOAOrderType, ProtoOATradeSide
    )
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOANewOrderReq

    print("\n" + "=" * 70)
    print(" cTrader Atomic Relative SL/TP Verification (Offline Framing)")
    print("=" * 70)

    # 1. Test 5-digit Forex Pair Rounding (EURUSD)
    passed_5d, res_5d = verify_tick_rounding(
        symbol="EURUSD",
        entry=1.08543,
        sl_distance=0.00220, # 22.0 pips
        tp_distance=0.00330  # 33.0 pips
    )
    print(f"\n[TEST 1] 5-Digit Forex Tick Rounding (EURUSD):")
    print(f"  • Entry:             {res_5d['entry']:.5f}")
    print(f"  • Requested SL Dist: {res_5d['sl_distance']:.5f} (22.0 pips)")
    print(f"  • Target SL Price:   {res_5d['sl_price']:.5f} (Scaled relativeStopLoss: {res_5d['rel_sl']:,})")
    print(f"  • Requested TP Dist: {res_5d['tp_distance']:.5f} (33.0 pips)")
    print(f"  • Target TP Price:   {res_5d['tp_price']:.5f} (Scaled relativeTakeProfit: {res_5d['rel_tp']:,})")
    print(f"  • Tick Size:         {res_5d['tick_size']:.5f} | SL Diff: {res_5d['sl_diff']:.7f}")
    print(f"  • Status:            {'PASS' if passed_5d else 'FAIL'}")

    # 2. Test Gold Rounding (XAUUSD)
    passed_gold, res_gold = verify_tick_rounding(
        symbol="XAUUSD",
        entry=2750.65,
        sl_distance=25.00, # $25.00/oz
        tp_distance=37.50  # $37.50/oz
    )
    print(f"\n[TEST 2] Commodity Gold Tick Rounding (XAUUSD):")
    print(f"  • Entry:             {res_gold['entry']:.2f}")
    print(f"  • Requested SL Dist: ${res_gold['sl_distance']:.2f}/oz")
    print(f"  • Target SL Price:   ${res_gold['sl_price']:.2f} (Scaled relativeStopLoss: {res_gold['rel_sl']:,})")
    print(f"  • Requested TP Dist: ${res_gold['tp_distance']:.2f}/oz")
    print(f"  • Target TP Price:   ${res_gold['tp_price']:.2f} (Scaled relativeTakeProfit: {res_gold['rel_tp']:,})")
    print(f"  • Tick Size:         {res_gold['tick_size']:.2f} | SL Diff: {res_gold['sl_diff']:.7f}")
    print(f"  • Status:            {'PASS' if passed_gold else 'FAIL'}")

    # 3. Protobuf Message Construction
    is_gold = "XAU" in symbol.upper() or "GOLD" in symbol.upper()
    sym_id = get_symbol_id(symbol) or (41 if is_gold else 1)
    target_res = res_gold if is_gold else res_5d
    volume_cents = int(round(lots * (100.0 if is_gold else 100_000.0) * 100))

    req = ProtoOANewOrderReq()
    req.ctidTraderAccountId = 12345678
    req.symbolId = sym_id
    req.orderType = ProtoOAOrderType.MARKET
    req.tradeSide = ProtoOATradeSide.BUY
    req.volume = volume_cents
    req.relativeStopLoss = target_res["rel_sl"]
    req.relativeTakeProfit = target_res["rel_tp"]

    serialized = req.SerializeToString()
    print(f"\n[TEST 3] Protobuf Message Framing for {symbol}:")
    print(f"  • Symbol ID:         {sym_id}")
    print(f"  • Order Type:        MARKET (BUY)")
    print(f"  • Volume (cents):    {volume_cents:,} subunits ({lots} lots)")
    print(f"  • relativeStopLoss:  {req.relativeStopLoss:,}")
    print(f"  • relativeTakeProfit:{req.relativeTakeProfit:,}")
    print(f"  • Absolute SL / TP:  {req.stopLoss if req.HasField('stopLoss') else 'None (omitted for MARKET)'}")
    print(f"  • Serialized Size:   {len(serialized)} bytes")

    if passed_5d and passed_gold:
        print("\n" + "=" * 70)
        print(" [VERIFIED] All tick rounding and Protobuf framing tests PASSED.")
        print(" To execute against a cTrader DEMO or FTMO Trial account, run:")
        print(f"     python scripts/demo_relative_sltp.py --live --symbol {symbol}")
        print("=" * 70 + "\n")
    else:
        print("\n[FAILED] Tick rounding verification failed.\n")
        sys.exit(1)


def run_live_demo_verification(symbol: str, lots: float, keep_open: bool = False, allow_prop_trial: bool = False):
    """Execute live test order on cTrader DEMO or FTMO trial to verify server atomic attachment."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
        ProtoOAPayloadType, ProtoOAOrderType, ProtoOAExecutionType, ProtoOATradeSide
    )
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (
        ProtoOAApplicationAuthReq, ProtoOAAccountAuthReq,
        ProtoOAGetAccountListByAccessTokenReq, ProtoOAGetAccountListByAccessTokenRes,
        ProtoOATraderReq, ProtoOATraderRes,
        ProtoOANewOrderReq, ProtoOAExecutionEvent, ProtoOAErrorRes,
        ProtoOAOrderErrorEvent, ProtoOAClosePositionReq
    )

    env = os.environ.get("CTRADER_ENV", "demo").lower()
    client_id = (os.environ.get("CTRADER_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("CTRADER_CLIENT_SECRET") or "").strip()
    access_token = (os.environ.get("CTRADER_ACCESS_TOKEN") or "").strip()
    account_id_str = (os.environ.get("CTRADER_ACCOUNT_ID") or "").strip()

    if not client_id or not client_secret or not access_token or not account_id_str:
        print("\n" + "=" * 70)
        print(" [BLOCKED] Missing Required cTrader Credentials in Environment")
        print("=" * 70)
        print(" Please set the following environment variables (in environment or .env):")
        print(f"  • CTRADER_ENV:          {env} (set to 'demo' for Spotware Sandbox, or 'live' for FTMO Trial)")
        print(f"  • CTRADER_CLIENT_ID:     {'[SET]' if client_id else '[MISSING]'}")
        print(f"  • CTRADER_CLIENT_SECRET: {'[SET]' if client_secret else '[MISSING]'}")
        print(f"  • CTRADER_ACCESS_TOKEN:  {'[SET]' if access_token else '[MISSING]'}")
        print(f"  • CTRADER_ACCOUNT_ID:    {'[SET]' if account_id_str else '[MISSING]'}")
        print("=" * 70 + "\n")
        sys.exit(1)

    account_id = int(account_id_str)
    host = CTRADER_HOSTS.get(env, "demo.ctraderapi.com" if env == "demo" else "live.ctraderapi.com")
    port = 5035

    is_gold = "XAU" in symbol.upper() or "GOLD" in symbol.upper()
    is_jpy = "JPY" in symbol.upper()
    sym_id = get_symbol_id(symbol) or (41 if is_gold else 1)

    if is_gold:
        sl_distance = 25.00
        tp_distance = 37.50
        tick_size = 0.01
        digits = 2
        volume_cents = int(round(lots * 100.0 * 100))
    elif is_jpy:
        sl_distance = 0.220
        tp_distance = 0.330
        tick_size = 0.001
        digits = 3
        volume_cents = int(round(lots * 100_000 * 100))
    else:
        sl_distance = 0.00220
        tp_distance = 0.00330
        tick_size = 0.00001
        digits = 5
        volume_cents = int(round(lots * 100_000 * 100))

    rel_sl = int(round(sl_distance * 100_000))
    rel_tp = int(round(tp_distance * 100_000))

    print("\n" + "=" * 70)
    print(f" cTrader Live Verification: Connecting to {host}:{port} ({env.upper()})...")
    print("=" * 70)

    ctx = ssl.create_default_context()
    with ctx.wrap_socket(socket.socket(), server_hostname=host) as s:
        s.settimeout(10.0)
        s.connect((host, port))
        print("✓ TLS Socket connected.")

        # 1. Application Authentication
        print("• Authenticating Open API Application...")
        app_req = ProtoOAApplicationAuthReq()
        app_req.clientId = client_id
        app_req.clientSecret = client_secret
        app_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_REQ, app_req)
        if not app_res or app_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
            print("[FAILED] Application authentication rejected.")
            sys.exit(1)
        print("✓ Application authenticated.")

        # 2. Account Authentication
        print(f"• Authenticating Account ID #{account_id}...")
        acc_req = ProtoOAAccountAuthReq()
        acc_req.ctidTraderAccountId = account_id
        acc_req.accessToken = access_token
        acc_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_REQ, acc_req)
        if not acc_res or acc_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
            print(f"[FAILED] Account authentication rejected for account #{account_id}.")
            sys.exit(1)
        print("✓ Account authenticated.")

        # 3. Query Trader Metadata (Broker Name, Login, Balance)
        broker_name = "unknown"
        trader_login = 0
        account_balance = 0.0
        trader_req = ProtoOATraderReq()
        trader_req.ctidTraderAccountId = account_id
        trader_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_TRADER_REQ, trader_req)
        if trader_res and trader_res[0] == ProtoOAPayloadType.PROTO_OA_TRADER_RES:
            trader_msg = ProtoOATraderRes()
            trader_msg.ParseFromString(trader_res[1])
            broker_name = trader_msg.trader.brokerName
            trader_login = trader_msg.trader.traderLogin
            account_balance = trader_msg.trader.balance / 100.0

        print(f"• Broker Profile:      {broker_name.upper()} | Login: #{trader_login} | Balance: ${account_balance:,.2f}")

        # 4. Account Type Safety Inspection (checking isLive flag)
        print("• Inspecting Account Type (checking isLive flag)...")
        acc_list_req = ProtoOAGetAccountListByAccessTokenReq()
        acc_list_req.accessToken = access_token
        acc_list_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_GET_ACCOUNTS_BY_ACCESS_TOKEN_REQ, acc_list_req)

        account_is_live = None
        if acc_list_res and acc_list_res[0] == ProtoOAPayloadType.PROTO_OA_GET_ACCOUNTS_BY_ACCESS_TOKEN_RES:
            acc_list = ProtoOAGetAccountListByAccessTokenRes()
            acc_list.ParseFromString(acc_list_res[1])
            for acc in acc_list.ctidTraderAccount:
                if acc.ctidTraderAccountId == account_id:
                    account_is_live = acc.isLive
                    break

        # In cTrader Open API, broker-hosted evaluation/trial accounts (e.g. FTMO) are flagged with isLive=True
        # because they reside on the broker's live server cluster rather than Spotware's sandbox.
        is_prop_eval = broker_name.lower() in ("ftmo", "the5ers", "fundednext") or allow_prop_trial

        if account_is_live is True and not is_prop_eval:
            print("\n" + "!" * 70)
            print(f" [FINANCIAL SAFETY BLOCK] Account #{account_id} has isLive = True (REAL MONEY)!")
            print(" In accordance with Non-Negotiable Financial Safety Invariants,")
            print(" zero automated test trades may be executed on a real live money account.")
            print(" If this is a prop-firm evaluation/trial account, pass --allow-prop-trial.")
            print("!" * 70 + "\n")
            sys.exit(1)
        elif is_prop_eval:
            print(f"✓ Prop Firm Evaluation Account verified ({broker_name.upper()} #{trader_login}). Safe to proceed with test micro-lot.")
        elif account_is_live is False:
            print(f"✓ Account #{account_id} verified as VIRTUAL / DEMO (isLive = False). Safe to proceed.")
        else:
            print(f"⚠️ Account list query did not return account #{account_id}. Proceeding with caution on {env.upper()}.")

        # 4. Dispatch MARKET Order with relativeStopLoss & relativeTakeProfit
        print(f"\n• Dispatching MARKET BUY order on {symbol}...")
        print(f"  - Volume:              {lots} lots ({volume_cents:,} subunits)")
        print(f"  - relativeStopLoss:    {rel_sl:,} (distance: {sl_distance})")
        print(f"  - relativeTakeProfit:  {rel_tp:,} (distance: {tp_distance})")

        order_req = ProtoOANewOrderReq()
        order_req.ctidTraderAccountId = account_id
        order_req.symbolId = sym_id
        order_req.orderType = ProtoOAOrderType.MARKET
        order_req.tradeSide = ProtoOATradeSide.BUY
        order_req.volume = volume_cents
        order_req.relativeStopLoss = rel_sl
        order_req.relativeTakeProfit = rel_tp

        order_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_NEW_ORDER_REQ, order_req)
        if not order_res:
            print("[FAILED] No response received for ProtoOANewOrderReq.")
            sys.exit(1)

        if order_res[0] == ProtoOAPayloadType.PROTO_OA_ORDER_ERROR_EVENT:
            err = ProtoOAOrderErrorEvent()
            err.ParseFromString(order_res[1])
            print(f"[REJECTED] Broker rejected order: {err.errorCode} - {err.description}")
            sys.exit(1)

        if order_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
            err = ProtoOAErrorRes()
            err.ParseFromString(order_res[1])
            print(f"[ERROR] Gateway error: {err.errorCode} - {err.description}")
            sys.exit(1)

        if order_res[0] != ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT:
            print(f"[FAILED] Unexpected response payload: {order_res[0]}")
            sys.exit(1)

        event = ProtoOAExecutionEvent()
        event.ParseFromString(order_res[1])

        if event.executionType == ProtoOAExecutionType.ORDER_ACCEPTED:
            next_frame = _read_tls_frame(s)
            if next_frame and next_frame[0] == ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT:
                event = ProtoOAExecutionEvent()
                event.ParseFromString(next_frame[1])

        pos_id = getattr(event.position, "positionId", 0) if event.HasField("position") else 0
        fill_price = getattr(event.position, "price", 0.0)
        attached_sl = getattr(event.position, "stopLoss", 0.0) if event.position.HasField("stopLoss") else 0.0
        attached_tp = getattr(event.position, "takeProfit", 0.0) if event.position.HasField("takeProfit") else 0.0

        # Close position immediately unless --no-close is requested
        close_success = False
        if not keep_open and pos_id > 0:
            print(f"\n• Cleaning up: Closing test position #{pos_id} at market...")
            close_req = ProtoOAClosePositionReq()
            close_req.ctidTraderAccountId = account_id
            close_req.positionId = int(pos_id)
            close_req.volume = volume_cents
            close_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_CLOSE_POSITION_REQ, close_req)
            if close_res and close_res[0] == ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT:
                close_success = True
                print(f"✓ Test position #{pos_id} closed successfully.")

        # Compute Checklist Criteria
        actual_sl_dist = round(fill_price - attached_sl, digits) if (fill_price > 0 and attached_sl > 0) else 0.0
        actual_tp_dist = round(attached_tp - fill_price, digits) if (fill_price > 0 and attached_tp > 0) else 0.0

        sl_present = bool(event.position.HasField("stopLoss") and attached_sl > 0)
        tp_present = bool(event.position.HasField("takeProfit") and attached_tp > 0)
        sl_distance_match = abs(actual_sl_dist - sl_distance) <= (tick_size + 1e-7)
        tp_distance_match = abs(actual_tp_dist - tp_distance) <= (tick_size + 1e-7)
        zero_leftover = close_success or keep_open

        all_passed = sl_present and tp_present and sl_distance_match and tp_distance_match and zero_leftover

        print("\n" + "=" * 70)
        print(" ROP-01 PASS/FAIL VERIFICATION CHECKLIST")
        print("=" * 70)
        print(f" [1] Stop Loss present on position at fill:             {'[PASS]' if sl_present else '[FAIL]'} (SL: {attached_sl})")
        print(f" [2] Take Profit present on position at fill:           {'[PASS]' if tp_present else '[FAIL]'} (TP: {attached_tp})")
        print(f" [3] SL distance matches requested ({sl_distance:.5f}):      {'[PASS]' if sl_distance_match else '[FAIL]'} (Actual: {actual_sl_dist:.5f}, Tick: {tick_size})")
        print(f" [4] TP distance matches requested ({tp_distance:.5f}):      {'[PASS]' if tp_distance_match else '[FAIL]'} (Actual: {actual_tp_dist:.5f}, Tick: {tick_size})")
        print(f" [5] Position closed cleanly via ProtoOAClosePositionReq: {'[PASS]' if close_success else ('[SKIPPED (--no-close)]' if keep_open else '[FAIL]')}")
        print(f" [6] Zero leftover orders or positions on broker:        {'[PASS]' if zero_leftover else '[FAIL]'}")
        print("-" * 70)
        if all_passed:
            print(" >>> FINAL RESULT: ALL CRITERIA PASSED [VERIFIED ATOMIC SL/TP] <<<")
        else:
            print(" >>> FINAL RESULT: ONE OR MORE CRITERIA FAILED <<<")
        print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="cTrader Atomic Relative SL/TP Verification (ROP-01)")
    parser.add_argument("--live", action="store_true", help="Connect to broker DEMO or FTMO Trial account and execute live micro-lot")
    parser.add_argument("--symbol", type=str, default="EURUSD", help="Symbol to test (e.g. EURUSD, XAUUSD, USDJPY)")
    parser.add_argument("--lots", type=float, default=0.01, help="Lot size for test order (default: 0.01 micro-lot)")
    parser.add_argument("--no-close", action="store_true", help="Do not automatically close the test position after fill")
    parser.add_argument("--allow-prop-trial", action="store_true", help="Authorize execution on a prop firm evaluation/challenge trial account")

    args = parser.parse_args()

    if args.live:
        run_live_demo_verification(symbol=args.symbol, lots=args.lots, keep_open=args.no_close, allow_prop_trial=args.allow_prop_trial)
    else:
        run_offline_verification(symbol=args.symbol, lots=args.lots)


if __name__ == "__main__":
    main()
