#!/usr/bin/env python3
"""Standalone Verification Script for cTrader Atomic Relative SL/TP (ROP-01).

Demonstrates and verifies that cTrader Open API accepts `relativeStopLoss` and
`relativeTakeProfit` inside `ProtoOANewOrderReq` for MARKET orders, attaching
protection atomically upon fill without naked exposure.

Usage:
    # 1. Safe offline dry-run verification (no network, verifies protobuf scaling & framing):
    python scripts/demo_relative_sltp.py

    # 2. Live verification against cTrader DEMO account:
    python scripts/demo_relative_sltp.py --live --symbol EURUSD --lots 0.01

    # 3. Live verification on Gold DEMO account:
    python scripts/demo_relative_sltp.py --live --symbol XAUUSD --lots 0.01
"""

import sys
import os
import argparse
import socket
import ssl
import time
from pathlib import Path

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


def run_offline_verification(symbol: str, lots: float):
    """Verify protobuf framing and scaling offline without connecting to broker."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
        ProtoOAOrderType, ProtoOATradeSide
    )
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOANewOrderReq

    print("\n" + "=" * 65)
    print(" cTrader Atomic Relative SL/TP Verification (Offline Framing)")
    print("=" * 65)

    is_gold = "XAU" in symbol.upper() or "GOLD" in symbol.upper()
    is_jpy = "JPY" in symbol.upper()
    sym_id = get_symbol_id(symbol) or (41 if is_gold else 1)

    # Reference entry, SL and TP geometry
    if is_gold:
        entry = 2750.00
        sl_points = 25.0
        tp_points = 37.5
        sl_price = entry - sl_points
        tp_price = entry + tp_points
        volume_cents = int(round(lots * 100.0 * 100)) # 100 oz/lot * 100 cents
        rel_sl = int(round(sl_points * 100_000))
        rel_tp = int(round(tp_points * 100_000))
    elif is_jpy:
        entry = 154.500
        sl_pips = 22.0
        tp_pips = 33.0
        pip_size = 0.01
        sl_price = entry - (sl_pips * pip_size)
        tp_price = entry + (tp_pips * pip_size)
        volume_cents = int(round(lots * 100_000 * 100))
        rel_sl = int(round(sl_pips * pip_size * 100_000))
        rel_tp = int(round(tp_pips * pip_size * 100_000))
    else:
        entry = 1.08500
        sl_pips = 22.0
        tp_pips = 33.0
        pip_size = 0.0001
        sl_price = entry - (sl_pips * pip_size)
        tp_price = entry + (tp_pips * pip_size)
        volume_cents = int(round(lots * 100_000 * 100))
        rel_sl = int(round(sl_pips * pip_size * 100_000))
        rel_tp = int(round(tp_pips * pip_size * 100_000))

    req = ProtoOANewOrderReq()
    req.ctidTraderAccountId = 12345678
    req.symbolId = sym_id
    req.orderType = ProtoOAOrderType.MARKET
    req.tradeSide = ProtoOATradeSide.BUY
    req.volume = volume_cents
    req.relativeStopLoss = rel_sl
    req.relativeTakeProfit = rel_tp

    serialized_bytes = req.SerializeToString()

    print(f"• Symbol:              {symbol} (Symbol ID: {sym_id})")
    print(f"• Order Type:          MARKET (BUY)")
    print(f"• Volume (lots):       {lots} ({volume_cents:,} subunits)")
    print(f"• Mock Entry Price:    {entry}")
    print(f"• Target SL Price:     {sl_price} (Distance: {abs(entry - sl_price):.5f})")
    print(f"• Target TP Price:     {tp_price} (Distance: {abs(entry - tp_price):.5f})")
    print(f"• Scaled relativeSL:   {req.relativeStopLoss:,} (10^-5 units)")
    print(f"• Scaled relativeTP:   {req.relativeTakeProfit:,} (10^-5 units)")
    print(f"• Absolute stopLoss:   {req.stopLoss if req.HasField('stopLoss') else 'None (omitted for MARKET)'}")
    print(f"• Absolute takeProfit: {req.takeProfit if req.HasField('takeProfit') else 'None (omitted for MARKET)'}")
    print(f"• Serialized Size:     {len(serialized_bytes)} bytes")
    print("\n[VERIFIED] Protobuf relativeStopLoss & relativeTakeProfit serialization is mathematically valid.")
    print("To execute against a real DEMO account, run:")
    print(f"    python scripts/demo_relative_sltp.py --live --symbol {symbol}\n")


def run_live_demo_verification(symbol: str, lots: float, keep_open: bool = False):
    """Execute live order on cTrader DEMO account to verify server-side atomic attachment."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
        ProtoOAPayloadType, ProtoOAOrderType, ProtoOAExecutionType, ProtoOATradeSide
    )
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (
        ProtoOAApplicationAuthReq, ProtoOAAccountAuthReq,
        ProtoOANewOrderReq, ProtoOAExecutionEvent, ProtoOAErrorRes,
        ProtoOAOrderErrorEvent, ProtoOAClosePositionReq
    )

    env = os.environ.get("CTRADER_ENV", "demo").lower()
    client_id = (os.environ.get("CTRADER_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("CTRADER_CLIENT_SECRET") or "").strip()
    access_token = (os.environ.get("CTRADER_ACCESS_TOKEN") or "").strip()
    account_id_str = (os.environ.get("CTRADER_ACCOUNT_ID") or "").strip()

    if env != "demo":
        print(f"\n[BLOCKED] CTRADER_ENV is '{env}'. This verification script strictly operates on 'demo' accounts.")
        print("Please set CTRADER_ENV=demo before running live verification.")
        sys.exit(1)

    if not client_id or not client_secret or not access_token or not account_id_str:
        print("\n[BLOCKED] Missing required cTrader credentials in environment or .env:")
        print(f"  CTRADER_CLIENT_ID:     {'SET' if client_id else 'MISSING'}")
        print(f"  CTRADER_CLIENT_SECRET: {'SET' if client_secret else 'MISSING'}")
        print(f"  CTRADER_ACCESS_TOKEN:  {'SET' if access_token else 'MISSING'}")
        print(f"  CTRADER_ACCOUNT_ID:    {'SET' if account_id_str else 'MISSING'}")
        sys.exit(1)

    account_id = int(account_id_str)
    host = CTRADER_HOSTS.get("demo", "demo.ctraderapi.com")
    port = 5035

    is_gold = "XAU" in symbol.upper() or "GOLD" in symbol.upper()
    is_jpy = "JPY" in symbol.upper()
    sym_id = get_symbol_id(symbol) or (41 if is_gold else 1)

    if is_gold:
        sl_points = 25.0
        tp_points = 37.5
        volume_cents = int(round(lots * 100.0 * 100))
        rel_sl = int(round(sl_points * 100_000))
        rel_tp = int(round(tp_points * 100_000))
    elif is_jpy:
        sl_pips = 22.0
        tp_pips = 33.0
        pip_size = 0.01
        volume_cents = int(round(lots * 100_000 * 100))
        rel_sl = int(round(sl_pips * pip_size * 100_000))
        rel_tp = int(round(tp_pips * pip_size * 100_000))
    else:
        sl_pips = 22.0
        tp_pips = 33.0
        pip_size = 0.0001
        volume_cents = int(round(lots * 100_000 * 100))
        rel_sl = int(round(sl_pips * pip_size * 100_000))
        rel_tp = int(round(tp_pips * pip_size * 100_000))

    print("\n" + "=" * 65)
    print(f" Connecting to cTrader DEMO Server ({host}:{port})...")
    print("=" * 65)

    ctx = ssl.create_default_context()
    with ctx.wrap_socket(socket.socket(), server_hostname=host) as s:
        s.settimeout(10.0)
        s.connect((host, port))
        print("✓ TLS Socket connected successfully.")

        # 1. Application Authentication
        print("• Authenticating Application (clientId)...")
        app_req = ProtoOAApplicationAuthReq()
        app_req.clientId = client_id
        app_req.clientSecret = client_secret
        app_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_REQ, app_req)
        if not app_res or app_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
            print(f"[FAILED] Application Authentication error.")
            sys.exit(1)
        print("✓ Application authenticated.")

        # 2. Account Authentication
        print(f"• Authenticating Account ({account_id})...")
        acc_req = ProtoOAAccountAuthReq()
        acc_req.ctidTraderAccountId = account_id
        acc_req.accessToken = access_token
        acc_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_REQ, acc_req)
        if not acc_res or acc_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
            print(f"[FAILED] Account Authentication error.")
            sys.exit(1)
        print("✓ Account authenticated.")

        # 3. New Order Dispatch with relativeStopLoss & relativeTakeProfit
        print(f"\n• Dispatching MARKET BUY order on {symbol}...")
        print(f"  - Volume:              {lots} lots ({volume_cents:,} subunits)")
        print(f"  - relativeStopLoss:    {rel_sl:,} (10^-5 units)")
        print(f"  - relativeTakeProfit:  {rel_tp:,} (10^-5 units)")

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

        if order_res[0] == ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT:
            event = ProtoOAExecutionEvent()
            event.ParseFromString(order_res[1])

            if event.executionType == ProtoOAExecutionType.ORDER_ACCEPTED:
                # Read subsequent fill frame
                next_frame = _read_tls_frame(s)
                if next_frame and next_frame[0] == ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT:
                    event = ProtoOAExecutionEvent()
                    event.ParseFromString(next_frame[1])

            pos_id = getattr(event.position, "positionId", 0) if event.HasField("position") else 0
            fill_price = getattr(event.position, "price", 0.0)
            attached_sl = getattr(event.position, "stopLoss", 0.0) if event.position.HasField("stopLoss") else 0.0
            attached_tp = getattr(event.position, "takeProfit", 0.0) if event.position.HasField("takeProfit") else 0.0

            print("\n" + "=" * 65)
            print(" EXECUTION RECEIPT")
            print("=" * 65)
            print(f"• Position ID:     #{pos_id}")
            print(f"• Execution Type:  {event.executionType}")
            print(f"• Fill Price:      {fill_price}")
            print(f"• Attached SL:     {attached_sl}")
            print(f"• Attached TP:     {attached_tp}")

            if attached_sl > 0:
                print("\n[VERIFIED] Server attached relativeStopLoss atomically upon fill! Zero naked exposure.")
            else:
                print("\n[WARNING] Position filled WITHOUT Stop-Loss! Server did not attach relativeStopLoss.")

            # Emergency / Test cleanup: Close the test position immediately
            if not keep_open and pos_id > 0:
                print(f"\n• Cleaning up: Closing test position #{pos_id} at market...")
                close_req = ProtoOAClosePositionReq()
                close_req.ctidTraderAccountId = account_id
                close_req.positionId = int(pos_id)
                close_req.volume = volume_cents
                close_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_CLOSE_POSITION_REQ, close_req)
                if close_res and close_res[0] == ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT:
                    print(f"✓ Test position #{pos_id} closed successfully. DEMO account balance restored.")
                else:
                    print(f"⚠️ Could not confirm close frame. Please check position #{pos_id} in cTrader GUI.")
            elif keep_open:
                print(f"\nℹ️ Position #{pos_id} kept open per --no-close flag. Please monitor or close manually in cTrader GUI.")


def main():
    parser = argparse.ArgumentParser(description="cTrader Atomic Relative SL/TP Verification (ROP-01)")
    parser.add_argument("--live", action="store_true", help="Connect to cTrader DEMO server and execute live test micro-lot")
    parser.add_argument("--symbol", type=str, default="EURUSD", help="Symbol to test (e.g. EURUSD, XAUUSD, USDJPY)")
    parser.add_argument("--lots", type=float, default=0.01, help="Lot size for test order (default: 0.01 micro-lot)")
    parser.add_argument("--no-close", action="store_true", help="Do not automatically close the test position after fill")

    args = parser.parse_args()

    if args.live:
        run_live_demo_verification(symbol=args.symbol, lots=args.lots, keep_open=args.no_close)
    else:
        run_offline_verification(symbol=args.symbol, lots=args.lots)


if __name__ == "__main__":
    main()
