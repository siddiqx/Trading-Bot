#!/usr/bin/env python3
"""Automated cTrader Multi-Account Fleet Synchronizer.

Discovers, validates, and syncs all trading accounts linked to the cTrader Open API
credentials across both live and demo servers. Provides zero-manual-entry account
progress tracking for Phantom OS.
"""

import os
import sys
import ssl
import socket
import json
import time
from typing import Dict, Any, List

# Add trading-bot root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Load environment variables
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType, ProtoOAAccessRights
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAApplicationAuthReq, ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAGetAccountListByAccessTokenRes, ProtoOAAccountAuthReq,
    ProtoOATraderReq, ProtoOATraderRes, ProtoOAReconcileReq, ProtoOAReconcileRes
)
from core.ctrader_executor import _send_tls_frame

DISCOVERED_OUTPUT_PATH = os.path.join(PROJECT_ROOT, "discovered_accounts.json")
EQUITY_CACHE_PATH = os.path.join(PROJECT_ROOT, "live_equity_cache.json")


def sync_all_ctrader_accounts(timeout: float = 8.0) -> List[Dict[str, Any]]:
    client_id = os.environ.get("CTRADER_CLIENT_ID", "").strip()
    client_secret = os.environ.get("CTRADER_CLIENT_SECRET", "").strip()
    access_token = os.environ.get("CTRADER_ACCESS_TOKEN", "").strip()

    if not client_id or not client_secret or not access_token:
        print("[cTrader Fleet Sync] Missing cTrader Open API credentials in .env.")
        return []

    discovered_accounts: List[Dict[str, Any]] = []
    hosts = [
        ("live.ctraderapi.com", True),
        ("demo.ctraderapi.com", False)
    ]

    for host, is_live_host in hosts:
        try:
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(socket.socket(), server_hostname=host) as s:
                s.settimeout(timeout)
                s.connect((host, 5035))

                # 1. Application Authentication
                app_req = ProtoOAApplicationAuthReq(clientId=client_id, clientSecret=client_secret)
                app_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_REQ, app_req)
                if not app_res or app_res[0] != ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_RES:
                    continue

                # 2. Get Account List for Token
                acc_list_req = ProtoOAGetAccountListByAccessTokenReq(accessToken=access_token)
                list_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_GET_ACCOUNTS_BY_ACCESS_TOKEN_REQ, acc_list_req)
                if not list_res or list_res[0] != ProtoOAPayloadType.PROTO_OA_GET_ACCOUNTS_BY_ACCESS_TOKEN_RES:
                    continue

                res = ProtoOAGetAccountListByAccessTokenRes()
                res.ParseFromString(list_res[1])

                # 3. Authenticate and query each account
                for a in res.ctidTraderAccount:
                    acc_id = a.ctidTraderAccountId
                    acc_auth = ProtoOAAccountAuthReq(ctidTraderAccountId=acc_id, accessToken=access_token)
                    auth_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_REQ, acc_auth)
                    if not auth_res or auth_res[0] != ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_RES:
                        continue

                    trader_req = ProtoOATraderReq(ctidTraderAccountId=acc_id)
                    t_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_TRADER_REQ, trader_req)
                    if not t_res or t_res[0] != ProtoOAPayloadType.PROTO_OA_TRADER_RES:
                        continue

                    t_msg = ProtoOATraderRes()
                    t_msg.ParseFromString(t_res[1])
                    t = t_msg.trader

                    money_digits = t.moneyDigits if t.HasField("moneyDigits") else 2
                    bal = round(t.balance / (10 ** money_digits), 2)
                    broker_raw = t.brokerName if t.HasField("brokerName") else ("ftmo" if "live" in host else "Spotware")
                    t_login = t.traderLogin if t.HasField("traderLogin") else acc_id
                    leverage_val = t.leverageInCents / 100 if t.HasField("leverageInCents") else 100.0

                    # 4. Reconcile Open Positions
                    rec_req = ProtoOAReconcileReq(ctidTraderAccountId=acc_id)
                    rec_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_RECONCILE_REQ, rec_req)
                    open_positions = []
                    unrealized_pnl = 0.0
                    if rec_res and rec_res[0] == ProtoOAPayloadType.PROTO_OA_RECONCILE_RES:
                        r_msg = ProtoOAReconcileRes()
                        r_msg.ParseFromString(rec_res[1])
                        for p in r_msg.position:
                            pos_entry = {
                                "position_id": p.positionId,
                                "symbol_id": p.tradeData.symbolId,
                                "volume": p.tradeData.volume / 100,
                                "trade_side": "BUY" if p.tradeData.tradeSide == 1 else "SELL",
                                "entry_price": p.price,
                            }
                            open_positions.append(pos_entry)

                    equity = round(bal + unrealized_pnl, 2)

                    # 5. Intelligent Automatic Classification
                    broker_clean = broker_raw.strip()
                    broker_lower = broker_clean.lower()
                    
                    # Known user mappings & prop firm rules
                    if "ftmo" in broker_lower:
                        firm_name = "FTMO"
                        # FTMO Free trial detection (demo trial is 10k or user's specific demo login 17257909)
                        if t_login == 17257909 or not a.isLive or "demo" in broker_lower or bal <= 10100:
                            alias = "FTMO-10K-DEMO"
                            classification = "DEMO_TRIAL"
                            status = "trial"
                            is_trial = True
                            can_payout = False
                            size_usd = 10000.0
                            goal = "Forward-testing demo verification via cTrader Open API"
                        else:
                            alias = f"FTMO-{int(bal//1000)}K"
                            classification = "PROP_FUNDED" if a.isLive else "PROP_EVALUATION"
                            status = "funded" if a.isLive else "evaluating"
                            is_trial = False
                            can_payout = a.isLive
                            size_usd = bal
                            goal = "Scale institutional capital allocation"
                    elif "spotware" in broker_lower:
                        firm_name = "Spotware"
                        alias = f"SPOTWARE-{int(bal//1000)}K-DEMO" if bal >= 1000 else f"SPOTWARE-{int(bal)}USD-DEMO"
                        classification = "DEMO_TRIAL"
                        status = "trial"
                        is_trial = True
                        can_payout = False
                        size_usd = max(1000.0, bal)
                        goal = "Direct cTrader Demo Sandbox"
                    elif "5ers" in broker_lower or "5%" in broker_lower:
                        firm_name = "The 5%ers"
                        alias = f"5ERS-{int(bal//1000)}K"
                        classification = "PROP_FUNDED" if a.isLive else "PROP_EVALUATION"
                        status = "funded" if a.isLive else "evaluating"
                        is_trial = False
                        can_payout = a.isLive
                        size_usd = bal
                        goal = "High Stakes Prop Challenge"
                    else:
                        firm_name = broker_clean.upper()
                        alias = f"{firm_name[:6]}-{int(bal//1000)}K"
                        classification = "DEMO_TRIAL" if not a.isLive else "PROP_EVALUATION"
                        status = "trial" if not a.isLive else "evaluating"
                        is_trial = not a.isLive
                        can_payout = a.isLive
                        size_usd = max(1000.0, bal)
                        goal = f"{firm_name} Trading Account"

                    drawdown_pct = 0.0
                    if bal < size_usd:
                        drawdown_pct = round(((size_usd - bal) / size_usd) * 100, 2)

                    account_entry = {
                        "account_id": acc_id,
                        "trader_login": t_login,
                        "account_alias": alias,
                        "firm_name": firm_name,
                        "broker_name": broker_raw,
                        "size_usd": size_usd,
                        "balance_usd": bal,
                        "equity_usd": equity,
                        "unrealized_pnl_usd": unrealized_pnl,
                        "currency": "USD",
                        "leverage": f"1:{int(leverage_val)}",
                        "status": status,
                        "account_classification": classification,
                        "is_trial": is_trial,
                        "is_live": a.isLive,
                        "can_distribute_profit": can_payout,
                        "is_challenge_completed": can_payout,
                        "daily_loss_limit_pct": 5.0,
                        "max_drawdown_limit_pct": 10.0,
                        "profit_target_pct": 10.0 if not can_payout else None,
                        "profit_split_pct": 80.0 if can_payout else 0.0,
                        "open_positions_count": len(open_positions),
                        "open_positions": open_positions,
                        "platform": "cTrader TLS Open API",
                        "account_goal": goal,
                        "gateway_host": host,
                        "last_synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "access_rights": "FULL_ACCESS"
                    }

                    discovered_accounts.append(account_entry)

        except Exception as ex:
            print(f"[cTrader Fleet Sync] Warning on host {host}: {ex}")

    # Save to discovered cache
    with open(DISCOVERED_OUTPUT_PATH, "w") as f:
        json.dump({
            "status": "OK",
            "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_accounts": len(discovered_accounts),
            "accounts": discovered_accounts
        }, f, indent=2)

    # Also update single-account live_equity_cache for the primary account
    primary_acc = next((a for a in discovered_accounts if a["trader_login"] == 17257909), discovered_accounts[0] if discovered_accounts else None)
    if primary_acc:
        with open(EQUITY_CACHE_PATH, "w") as f:
            json.dump({
                "status": "OK",
                "balance": primary_acc["balance_usd"],
                "unrealized_pnl": primary_acc["unrealized_pnl_usd"],
                "equity": primary_acc["equity_usd"],
                "open_positions_count": primary_acc["open_positions_count"],
                "positions": primary_acc["open_positions"],
                "broker_name": primary_acc["broker_name"],
                "trader_login": primary_acc["trader_login"],
                "account_id": primary_acc["account_id"],
                "access_rights": 0,
                "access_rights_name": "FULL_ACCESS",
                "is_trading_allowed": True,
                "money_digits": 2,
                "environment": "live" if "live" in primary_acc["gateway_host"] else "demo"
            }, f, indent=2)

    print(f"[cTrader Fleet Sync] Successfully synchronized {len(discovered_accounts)} accounts from cTrader Open API.")
    return discovered_accounts


if __name__ == "__main__":
    accs = sync_all_ctrader_accounts()
    for acc in accs:
        print(f" -> {acc['account_alias']}: Login #{acc['trader_login']} ({acc['firm_name']}) | Balance: ${acc['balance_usd']:,.2f} | Status: {acc['status']}")
