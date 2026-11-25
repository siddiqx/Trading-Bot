#!/usr/bin/env python3
"""Automated cTrader Account Connector and GitHub Secrets Synchronizer.

Usage:
    python scripts/connect_account.py "http://localhost/?code=YOUR_CODE_HERE"
    or
    python scripts/connect_account.py "YOUR_CODE_HERE"
"""

import os
import sys
import ssl
import socket
import struct
import urllib.parse
import subprocess
import base64
from typing import Dict, Any, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import httpx
from nacl import public

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.ctrader_executor import (
    CTRADER_CLIENT_ID,
    CTRADER_CLIENT_SECRET,
    CTRADER_HOSTS,
    CTRADER_PORT,
    _read_exact,
    _read_tls_frame,
    _send_tls_frame
)
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
    ProtoOAPayloadType,
    ProtoOAClientPermissionScope,
    ProtoOAAccessRights,
)
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAApplicationAuthReq,
    ProtoOAAccountAuthReq,
    ProtoOATraderReq,
    ProtoOATraderRes,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAGetAccountListByAccessTokenRes,
    ProtoOAErrorRes
)

TARGET_LOGIN = 17257909
TARGET_EQUITY = 10000.0


def extract_code(raw_input: str) -> str:
    raw = raw_input.strip()
    if "code=" in raw:
        parsed = urllib.parse.urlparse(raw)
        qs = urllib.parse.parse_qs(parsed.query)
        if "code" in qs:
            return qs["code"][0].strip()
    return raw


def exchange_code_for_token(code: str) -> Dict[str, Any]:
    token_url = "https://openapi.ctrader.com/apps/token"
    candidate_uris = [
        "http://localhost",
        "http://localhost/",
        "https://localhost",
        "https://localhost/",
        "http://127.0.0.1",
        "http://127.0.0.1/",
        "localhost"
    ]
    for r_uri in candidate_uris:
        params = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": r_uri,
            "client_id": CTRADER_CLIENT_ID,
            "client_secret": CTRADER_CLIENT_SECRET
        }
        try:
            r = httpx.get(token_url, params=params, timeout=15.0)
            if r.status_code == 200:
                data = r.json()
                if "accessToken" in data:
                    print(f"  ✓ Token exchanged successfully with redirect_uri: {r_uri}")
                    return data
            r_post = httpx.post(token_url, params=params, timeout=15.0)
            if r_post.status_code == 200:
                data = r_post.json()
                if "accessToken" in data:
                    print(f"  ✓ Token exchanged successfully via POST with redirect_uri: {r_uri}")
                    return data
        except Exception as e:
            continue
    raise RuntimeError("Failed to exchange authorization code for access token with all candidate URIs.")


def inspect_and_authorize_account(access_token: str, target_login: int) -> Dict[str, Any]:
    # Check both live and demo hosts
    for env in ["live", "demo"]:
        host = CTRADER_HOSTS.get(env, "live.ctraderapi.com")
        ctx = ssl.create_default_context()
        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_sock.settimeout(12.0)
        try:
            s = ctx.wrap_socket(raw_sock, server_hostname=host)
            s.connect((host, CTRADER_PORT))
        except Exception as ex:
            print(f"  ⚠️ Could not connect to {host}:{CTRADER_PORT}: {ex}")
            continue

        try:
            # 1. App Auth
            app_req = ProtoOAApplicationAuthReq(clientId=CTRADER_CLIENT_ID, clientSecret=CTRADER_CLIENT_SECRET)
            app_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_REQ, app_req)
            if not app_res or app_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
                s.close()
                continue

            # 2. Account list
            tok_req = ProtoOAGetAccountListByAccessTokenReq(accessToken=access_token)
            tok_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_GET_ACCOUNTS_BY_ACCESS_TOKEN_REQ, tok_req)
            if not tok_res or tok_res[0] != ProtoOAPayloadType.PROTO_OA_GET_ACCOUNTS_BY_ACCESS_TOKEN_RES:
                s.close()
                continue

            msg = ProtoOAGetAccountListByAccessTokenRes()
            msg.ParseFromString(tok_res[1])

            target_acc = None
            if target_login:
                for acc in msg.ctidTraderAccount:
                    if acc.traderLogin == target_login:
                        target_acc = acc
                        break

            if not target_acc:
                # Prefer isLive == True account, otherwise newest account in token
                live_accs = [a for a in msg.ctidTraderAccount if a.isLive]
                if live_accs:
                    target_acc = live_accs[-1]
                elif len(msg.ctidTraderAccount) > 0:
                    target_acc = msg.ctidTraderAccount[-1]

            if not target_acc:
                s.close()
                continue

            acc_id = target_acc.ctidTraderAccountId
            acc_env = "live" if target_acc.isLive else "demo"

            # 3. Account Auth
            acc_req = ProtoOAAccountAuthReq(ctidTraderAccountId=acc_id, accessToken=access_token)
            acc_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_REQ, acc_req)
            if not acc_res or acc_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
                s.close()
                continue

            # 4. Trader Query
            trader_req = ProtoOATraderReq(ctidTraderAccountId=acc_id)
            trader_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_TRADER_REQ, trader_req)
            if not trader_res or trader_res[0] != ProtoOAPayloadType.PROTO_OA_TRADER_RES:
                s.close()
                continue

            t_msg = ProtoOATraderRes()
            t_msg.ParseFromString(trader_res[1])
            trader = t_msg.trader
            money_digits = trader.moneyDigits if trader.HasField("moneyDigits") else 2
            balance = trader.balance / (10 ** money_digits)
            broker_name = trader.brokerName if trader.HasField("brokerName") else "Unknown"
            access_rights = trader.accessRights if trader.HasField("accessRights") else 0
            try:
                rights_name = ProtoOAAccessRights.Name(access_rights)
            except Exception:
                rights_name = str(access_rights)

            s.close()
            return {
                "account_id": acc_id,
                "trader_login": trader.traderLogin,
                "env": acc_env,
                "balance": balance,
                "broker_name": broker_name,
                "access_rights": access_rights,
                "rights_name": rights_name,
                "is_trading_allowed": (access_rights == ProtoOAAccessRights.FULL_ACCESS)
            }
        except Exception as ex:
            try:
                s.close()
            except Exception:
                pass
            continue

    raise RuntimeError(f"Could not find or authorize target trader login {target_login} on live or demo hosts.")


def update_local_env(updates: Dict[str, str]):
    env_path = os.path.join(project_root, ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()

    keys_to_update = set(updates.keys())
    new_lines = []
    for l in lines:
        matched = False
        for k in keys_to_update:
            if l.startswith(f"{k}="):
                new_lines.append(f"{k}={updates[k]}\n")
                keys_to_update.remove(k)
                matched = True
                break
        if not matched:
            new_lines.append(l)

    for k in keys_to_update:
        new_lines.append(f"{k}={updates[k]}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)
    print("  ✓ Local .env updated successfully.")


def update_github_secrets(updates: Dict[str, str]):
    proc = subprocess.Popen(['git', 'credential', 'fill'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, _ = proc.communicate('protocol=https\nhost=github.com\n\n')
    gh_token = None
    for line in out.splitlines():
        if line.startswith('password='):
            gh_token = line.split('password=', 1)[1].strip()

    if not gh_token:
        print("  ⚠️ GitHub token not found via git credentials; skipping GitHub Secrets update.")
        return

    headers = {
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {gh_token}',
        'X-GitHub-Api-Version': '2022-11-28'
    }
    r_pk = httpx.get('https://api.github.com/repos/siddiqx/Trading-Bot/actions/secrets/public-key', headers=headers)
    if r_pk.status_code != 200:
        print(f"  ⚠️ Failed to fetch GitHub public key: {r_pk.status_code}")
        return

    pk_data = r_pk.json()
    key_id = pk_data['key_id']
    public_key_b64 = pk_data['key']
    public_key_bytes = base64.b64decode(public_key_b64)
    public_key_obj = public.PublicKey(public_key_bytes)
    sealed_box = public.SealedBox(public_key_obj)

    for k, v in updates.items():
        enc_val = base64.b64encode(sealed_box.encrypt(v.encode('utf-8'))).decode('utf-8')
        payload = {'encrypted_value': enc_val, 'key_id': key_id}
        r_put = httpx.put(f'https://api.github.com/repos/siddiqx/Trading-Bot/actions/secrets/{k}', headers=headers, json=payload)
        if r_put.status_code in (201, 204):
            print(f"  ✓ Secret '{k}' uploaded to GitHub Actions Secrets!")
        else:
            print(f"  ❌ Failed to upload secret '{k}': {r_put.status_code}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/connect_account.py <authorization_code_or_url_or_token>")
        sys.exit(1)

    raw_arg = sys.argv[1].strip()
    access_token = None

    if raw_arg.startswith("token:"):
        access_token = raw_arg.split("token:", 1)[1].strip()
        print("\n[1/4] Using provided direct Access Token...")
    else:
        code = extract_code(raw_arg)
        print("\n[1/4] Exchanging Authorization Code for Token...")
        try:
            token_data = exchange_code_for_token(code)
            access_token = token_data["accessToken"]
            print("  ✓ Access token received.")
        except Exception as ex:
            print(f"  ⚠️ Code exchange notice: {ex}")
            print("  Attempting to use input directly as an Access Token...")
            access_token = code

    target_login = TARGET_LOGIN
    if len(sys.argv) > 2 and sys.argv[2].strip().isdigit():
        target_login = int(sys.argv[2].strip())

    print(f"\n[2/4] Inspecting cTrader Accounts (Target Login: {target_login or 'Auto-Detect'})...")
    acc_info = inspect_and_authorize_account(access_token, target_login)
    print(f"  ✓ Found Account ID:    {acc_info['account_id']}")
    print(f"  • Trader Login ID:     {acc_info['trader_login']}")
    print(f"  • Environment:         {acc_info['env'].upper()}")
    print(f"  • Broker:              {acc_info['broker_name'].upper()}")
    print(f"  • Balance:             ${acc_info['balance']:,.2f}")
    print(f"  • Access Rights:       {acc_info['rights_name']} (Trading Allowed: {acc_info['is_trading_allowed']})")

    resolved_equity = acc_info["balance"] if acc_info.get("balance", 0) > 0 else TARGET_EQUITY
    updates = {
        "CTRADER_ACCESS_TOKEN": access_token,
        "CTRADER_ACCOUNT_ID": str(acc_info["account_id"]),
        "CTRADER_ENV": acc_info["env"],
        "ACCOUNT_EQUITY": str(resolved_equity),
        "ENABLE_CTRADER_EXECUTION": "true" if acc_info["is_trading_allowed"] else "false"
    }

    print("\n[3/4] Updating Local Environment (.env)...")
    update_local_env(updates)

    print("\n[4/4] Synchronizing GitHub Actions Secrets...")
    update_github_secrets(updates)

    print("\n" + "=" * 70)
    if acc_info["is_trading_allowed"]:
        print("🎉 SUCCESS: cTrader account connected and fully authorized for 24/7 trading!")
    else:
        print(f"⚠️ NOTICE: Account connected, but access rights are {acc_info['rights_name']}.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
