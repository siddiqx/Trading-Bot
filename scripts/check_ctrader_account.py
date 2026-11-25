#!/usr/bin/env python3
"""cTrader Account Permissions & Diagnostic Health Check Utility.

Performs deep institutional-grade validation of cTrader Open API credentials,
token permission scopes (SCOPE_TRADE vs SCOPE_VIEW), broker account link status,
and broker-side access rights (FULL_ACCESS, CLOSE_ONLY, NO_TRADING).

Usage:
    python scripts/check_ctrader_account.py
"""

import os
import sys
import ssl
import socket
import struct
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.ctrader_executor import (
    CTRADER_ENV,
    CTRADER_HOSTS,
    CTRADER_PORT,
    CTRADER_CLIENT_ID,
    CTRADER_CLIENT_SECRET,
    CTRADER_ACCESS_TOKEN,
    CTRADER_ACCOUNT_ID,
    ENABLE_CTRADER_EXECUTION,
    _read_exact,
    _read_tls_frame,
    _send_tls_frame
)


def run_diagnostics() -> Dict[str, Any]:
    print("=" * 70)
    print("      cTrader Open API Account Diagnostic & Permissions Check      ")
    print("=" * 70)

    # 1. Inspect Environment & Credentials
    print("\n[1/5] Checking Environment Configuration...")
    print(f"  • CTRADER_ENV:              {CTRADER_ENV} (Host: {CTRADER_HOSTS.get(CTRADER_ENV, 'demo.ctraderapi.com')})")
    print(f"  • ENABLE_CTRADER_EXECUTION: {ENABLE_CTRADER_EXECUTION}")
    print(f"  • CTRADER_ACCOUNT_ID:       {CTRADER_ACCOUNT_ID or '<NOT SET>'}")
    print(f"  • CTRADER_CLIENT_ID:        {'Present (' + CTRADER_CLIENT_ID[:12] + '...)' if CTRADER_CLIENT_ID else '<NOT SET>'}")
    print(f"  • CTRADER_CLIENT_SECRET:    {'Present (hidden)' if CTRADER_CLIENT_SECRET else '<NOT SET>'}")
    print(f"  • CTRADER_ACCESS_TOKEN:     {'Present (' + CTRADER_ACCESS_TOKEN[:8] + '...)' if CTRADER_ACCESS_TOKEN else '<NOT SET>'}")

    if not (CTRADER_CLIENT_ID and CTRADER_CLIENT_SECRET and CTRADER_ACCESS_TOKEN):
        print("\n❌ FAILED: Missing required cTrader credentials in environment (.env or secrets).")
        print("   Required variables: CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET, CTRADER_ACCESS_TOKEN")
        return {"status": "MISSING_CREDENTIALS"}

    acc_id = None
    if CTRADER_ACCOUNT_ID and CTRADER_ACCOUNT_ID.strip().isdigit():
        acc_id = int(CTRADER_ACCOUNT_ID.strip())
    elif CTRADER_ACCOUNT_ID and CTRADER_ACCOUNT_ID.strip():
        print(f"\n❌ FAILED: CTRADER_ACCOUNT_ID must be numeric, got: '{CTRADER_ACCOUNT_ID}'")
        return {"status": "INVALID_ACCOUNT_ID"}

    host = CTRADER_HOSTS.get(CTRADER_ENV, "demo.ctraderapi.com")

    # 2. Establish TLS Connection
    print(f"\n[2/5] Establishing TLS connection to {host}:{CTRADER_PORT}...")
    ctx = ssl.create_default_context()
    raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw_sock.settimeout(12.0)

    try:
        s = ctx.wrap_socket(raw_sock, server_hostname=host)
        s.connect((host, CTRADER_PORT))
        print("  ✓ TLS socket connected successfully.")
    except Exception as ex:
        print(f"\n❌ FAILED to connect to {host}:{CTRADER_PORT}: {ex}")
        return {"status": "CONNECTION_FAILED", "error": str(ex)}

    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
        ProtoOAPayloadType,
        ProtoOAClientPermissionScope,
        ProtoOAAccessRights,
        ProtoOAAccountType
    )
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (
        ProtoOAApplicationAuthReq,
        ProtoOAApplicationAuthRes,
        ProtoOAAccountAuthReq,
        ProtoOAAccountAuthRes,
        ProtoOATraderReq,
        ProtoOATraderRes,
        ProtoOAGetAccountListByAccessTokenReq,
        ProtoOAGetAccountListByAccessTokenRes,
        ProtoOAGetPositionUnrealizedPnLReq,
        ProtoOAGetPositionUnrealizedPnLRes,
        ProtoOAErrorRes
    )

    try:
        # 3. Application Authentication
        print("\n[3/5] Authenticating Application Client Credentials...")
        app_req = ProtoOAApplicationAuthReq(clientId=CTRADER_CLIENT_ID, clientSecret=CTRADER_CLIENT_SECRET)
        app_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_REQ, app_req)
        if not app_res:
            print("  ❌ No response to ApplicationAuthReq")
            return {"status": "APP_AUTH_FAILED", "error": "Timeout"}
        if app_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
            err = ProtoOAErrorRes()
            err.ParseFromString(app_res[1])
            print(f"  ❌ Application Auth Error: {err.errorCode} - {err.description}")
            return {"status": "APP_AUTH_FAILED", "error": err.description}
        print("  ✓ Application credentials authorized by Spotware.")

        # 4. Token Scope & Linked Accounts
        print("\n[4/5] Inspecting Access Token Scopes & Linked Accounts...")
        tok_req = ProtoOAGetAccountListByAccessTokenReq(accessToken=CTRADER_ACCESS_TOKEN)
        tok_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_GET_ACCOUNTS_BY_ACCESS_TOKEN_REQ, tok_req)

        scope_name = "UNKNOWN"
        token_can_trade = True
        linked_accounts = []

        if tok_res and tok_res[0] == ProtoOAPayloadType.PROTO_OA_GET_ACCOUNTS_BY_ACCESS_TOKEN_RES:
            tok_msg = ProtoOAGetAccountListByAccessTokenRes()
            tok_msg.ParseFromString(tok_res[1])
            if tok_msg.HasField("permissionScope"):
                scope_val = tok_msg.permissionScope
                scope_name = ProtoOAClientPermissionScope.Name(scope_val) if hasattr(ProtoOAClientPermissionScope, "Name") else str(scope_val)
                token_can_trade = (scope_val == ProtoOAClientPermissionScope.SCOPE_TRADE)
                scope_mark = "✓" if token_can_trade else "❌"
                print(f"  {scope_mark} Token Scope: {scope_name} (Code: {scope_val})")
                if not token_can_trade:
                    print("    ⚠️ Token is restricted to SCOPE_VIEW. It cannot submit live trade orders!")

            print(f"  • Authorized Accounts ({len(tok_msg.ctidTraderAccount)} total):")
            found_target = False
            for acc in tok_msg.ctidTraderAccount:
                is_target = (acc.ctidTraderAccountId == acc_id)
                if is_target:
                    found_target = True
                marker = "==>" if is_target else "   "
                print(f"    {marker} Account ID: {acc.ctidTraderAccountId} | isLive: {acc.isLive} | Trader Login: {acc.traderLogin}")
                linked_accounts.append({
                    "account_id": acc.ctidTraderAccountId,
                    "is_live": acc.isLive,
                    "trader_login": acc.traderLogin
                })

            if acc_id is None and linked_accounts:
                env_matches = [a["account_id"] for a in linked_accounts if a["is_live"] == (CTRADER_ENV == "live")]
                acc_id = env_matches[0] if env_matches else linked_accounts[0]["account_id"]
                print(f"  ✓ Auto-selected active account ID: {acc_id}")
                found_target = True
            elif not found_target and acc_id:
                print(f"    ❌ Warning: Configured CTRADER_ACCOUNT_ID ({acc_id}) was NOT found in this token's authorized accounts list!")
        else:
            print("  ⚠️ Could not query account list by token.")

        # 5. Account Authentication & Permissions
        print(f"\n[5/5] Querying Broker Permissions for Account {acc_id}...")
        acc_req = ProtoOAAccountAuthReq(ctidTraderAccountId=acc_id, accessToken=CTRADER_ACCESS_TOKEN)
        acc_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_REQ, acc_req)
        if not acc_res:
            print("  ❌ No response to AccountAuthReq")
            return {"status": "ACCOUNT_AUTH_FAILED", "error": "Timeout"}
        if acc_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
            err = ProtoOAErrorRes()
            err.ParseFromString(acc_res[1])
            print(f"  ❌ Account Auth Error: {err.errorCode} - {err.description}")
            return {"status": "ACCOUNT_AUTH_FAILED", "error": err.description}
        print(f"  ✓ Account {acc_id} authorized.")

        trader_req = ProtoOATraderReq(ctidTraderAccountId=acc_id)
        trader_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_TRADER_REQ, trader_req)
        if not trader_res or trader_res[0] != ProtoOAPayloadType.PROTO_OA_TRADER_RES:
            print("  ❌ Failed to query ProtoOATraderRes.")
            return {"status": "TRADER_QUERY_FAILED"}

        t_msg = ProtoOATraderRes()
        t_msg.ParseFromString(trader_res[1])
        trader = t_msg.trader

        money_digits = trader.moneyDigits if trader.HasField("moneyDigits") else 2
        balance = trader.balance / (10 ** money_digits)
        broker_name = trader.brokerName if trader.HasField("brokerName") else "Unknown"
        trader_login = trader.traderLogin if trader.HasField("traderLogin") else acc_id
        access_rights = trader.accessRights if trader.HasField("accessRights") else 0
        try:
            rights_name = ProtoOAAccessRights.Name(access_rights)
        except Exception:
            rights_name = str(access_rights)

        print(f"  • Broker Name:         {broker_name.upper()}")
        print(f"  • Trader Login ID:     {trader_login}")
        print(f"  • Account Balance:     ${balance:,.2f}")
        print(f"  • Leverage:            1:{int(trader.leverageInCents / 100) if trader.HasField('leverageInCents') else 'N/A'}")

        # Check Access Rights
        print("\n" + "=" * 70)
        print("                       VERIFICATION SUMMARY                        ")
        print("=" * 70)

        trading_allowed = (access_rights == ProtoOAAccessRights.FULL_ACCESS) and token_can_trade

        if access_rights == ProtoOAAccessRights.FULL_ACCESS:
            print(f"  ✓ Broker Access Rights: FULL_ACCESS (Code: {access_rights}) -> TRADING PERMITTED")
        elif access_rights == ProtoOAAccessRights.CLOSE_ONLY:
            print(f"  ❌ Broker Access Rights: CLOSE_ONLY (Code: {access_rights}) -> NEW TRADES BLOCKED BY BROKER")
            print("     Reason: Broker allows closing existing positions only. Opening new positions")
            print("             returns 'TRADING_NOT_ALLOWED: Trading is not allowed for trader id ...'")
        elif access_rights == ProtoOAAccessRights.NO_TRADING:
            print(f"  ❌ Broker Access Rights: NO_TRADING (Code: {access_rights}) -> ALL TRADING DISABLED")
        elif access_rights == ProtoOAAccessRights.NO_LOGIN:
            print(f"  ❌ Broker Access Rights: NO_LOGIN (Code: {access_rights}) -> LOGIN DISABLED")
        else:
            print(f"  ⚠️ Broker Access Rights: {rights_name} (Code: {access_rights})")

        if not token_can_trade:
            print("  ❌ Token Scope: SCOPE_VIEW -> TOKEN LACKS TRADE SCOPE")

        print("-" * 70)
        if trading_allowed:
            print("  🎉 HEALTH CHECK PASSED: Account is fully ready for automated live execution!")
        else:
            print("  ⚠️ HEALTH CHECK BLOCKED: Broker or token restriction prevents new orders.")
            print("\n  Remediation Checklist:")
            if access_rights == ProtoOAAccessRights.CLOSE_ONLY:
                print(f"   1. Log into your {broker_name.upper()} client portal / MetriX dashboard.")
                print(f"   2. Verify the status of account login {trader_login}:")
                print("      - Has the evaluation/challenge concluded (passed, failed, or expired)?")
                print("      - Was there a weekend holding breach on a non-Swing evaluation account?")
                print(f"   3. If {broker_name.upper()} assigned you a new Challenge / Phase 2 account:")
                print("      - Note down the new cTrader account number.")
                print("      - Update CTRADER_ACCOUNT_ID in your .env file and GitHub Repository Secrets.")
            if not token_can_trade:
                print("   • Regenerate your cTrader Access Token at openapi.ctrader.com with 'Trading' permissions.")
        print("=" * 70)

        return {
            "status": "OK" if trading_allowed else "RESTRICTED",
            "broker": broker_name,
            "account_id": acc_id,
            "trader_login": trader_login,
            "balance": balance,
            "access_rights": rights_name,
            "access_rights_code": access_rights,
            "token_scope": scope_name,
            "trading_allowed": trading_allowed
        }

    finally:
        s.close()


if __name__ == "__main__":
    result = run_diagnostics()
    if result.get("status") not in ("OK", "RESTRICTED"):
        sys.exit(1)
