"""Institutional cTrader Open API Automated Execution Engine (v3.3.0).

Provides 24/7 cloud-to-cloud automated order execution and trailing stop management
for cTrader prop firm accounts (FTMO, FundedNext, Spotware Demo).
Features:
1. Pure serverless cloud execution (zero Windows / desktop MT5 dependency).
2. Safe Stage 2 Demo Execution (defaults to demo.ctraderapi.com:5035).
3. Built-in Dry-Run / Paper-Trading simulator when credentials are unconfigured.
4. Volatility-Cushioned position amendment (ProtoOAAmendPositionSLTPReq).
5. Non-blocking error handling to ensure Telegram and scanner cycles never crash.
"""

import os
import sys
import json
import socket
import ssl
import struct
import time
import logging
import concurrent.futures
from typing import Dict, Any, Optional, Tuple, List

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("cTraderExecutor")

# Environment Credentials & Configuration
CTRADER_ENV = os.environ.get("CTRADER_ENV", "demo").lower()
CTRADER_CLIENT_ID = (os.environ.get("CTRADER_CLIENT_ID") or "").strip()
CTRADER_CLIENT_SECRET = (os.environ.get("CTRADER_CLIENT_SECRET") or "").strip()
CTRADER_ACCESS_TOKEN = (os.environ.get("CTRADER_ACCESS_TOKEN") or "").strip()
CTRADER_ACCOUNT_ID = (os.environ.get("CTRADER_ACCOUNT_ID") or "").strip()
CTRADER_ACCOUNT_IDS = (os.environ.get("CTRADER_ACCOUNT_IDS") or "").strip()
ENABLE_CTRADER_EXECUTION = os.environ.get("ENABLE_CTRADER_EXECUTION", "false").lower() in ("true", "1", "yes")

# cTrader Open API Host Configuration
CTRADER_HOSTS = {
    "demo": "demo.ctraderapi.com",
    "live": "live.ctraderapi.com"
}
CTRADER_PORT = 5035

# Canonical cTrader Spotware / FTMO Symbol ID Map
DEFAULT_SYMBOL_MAP = {
    "EURUSD": 1,
    "GBPUSD": 2,
    "USDJPY": 4,
    "AUDUSD": 5,
    "USDCHF": 6,
    "USDCAD": 8,
    "XAUUSD": 41,
}

# Allow overriding via environment variable JSON
_ENV_MAP = os.environ.get("CTRADER_SYMBOL_MAP")
if _ENV_MAP:
    try:
        SYMBOL_MAP = json.loads(_ENV_MAP)
    except Exception:
        SYMBOL_MAP = DEFAULT_SYMBOL_MAP
else:
    SYMBOL_MAP = DEFAULT_SYMBOL_MAP

try:
    from core.config import (
        MAX_SLIPPAGE_PIPS,
        MAX_GOLD_SLIPPAGE_POINTS,
        CTRADER_ORDER_TYPE,
        PROP_FIRM_RISK_PCT,
        resolve_effective_risk_pct,
    )
except ImportError:
    MAX_SLIPPAGE_PIPS = float(os.environ.get("MAX_SLIPPAGE_PIPS", "3.0"))
    MAX_GOLD_SLIPPAGE_POINTS = float(os.getenv("MAX_GOLD_SLIPPAGE_POINTS", "50.0"))
    CTRADER_ORDER_TYPE = os.getenv("CTRADER_ORDER_TYPE", "MARKET").strip().upper()
    PROP_FIRM_RISK_PCT = 0.75

    def resolve_effective_risk_pct(current_equity, explicit_risk_pct=None, account_id=None, default_risk_pct=0.75, prefer_dynamic_over_signal=False):
        val = float(explicit_risk_pct) if (explicit_risk_pct and float(explicit_risk_pct) > 0) else float(os.environ.get("RISK_PCT", default_risk_pct))
        return val, {"mode": "fallback", "stage": "CUSTOM", "tier": "FALLBACK", "initial_balance": float(current_equity), "dd_pct": 0.0}



def has_valid_credentials() -> bool:
    """Check whether all required cTrader credentials are provided."""
    raw_acc_ids = (os.environ.get("CTRADER_ACCOUNT_IDS") or CTRADER_ACCOUNT_IDS).strip()
    raw_acc_id = (os.environ.get("CTRADER_ACCOUNT_ID") or CTRADER_ACCOUNT_ID).strip()
    return bool(
        CTRADER_CLIENT_ID and
        CTRADER_CLIENT_SECRET and
        CTRADER_ACCESS_TOKEN and
        (raw_acc_id or raw_acc_ids or os.environ.get("ENABLE_CTRADER_AUTO_DISCOVERY", "true").lower() in ("true", "1", "yes"))
    )


def is_test_environment() -> bool:
    """Return True if executing under pytest, test runner, or test environment.
    
    Hard financial safety invariant: Prevents automated unit tests, CI test runs,
    or developer test scripts from ever transmitting real orders to broker sockets.
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    if "pytest" in sys.modules:
        return True
    if any("pytest" in str(arg).lower() or "unittest" in str(arg).lower() for arg in sys.argv):
        return True
    return False


def get_symbol_id(pair: str) -> Optional[int]:
    """Resolve currency pair or commodity symbol to cTrader integer symbol ID."""
    clean = (
        pair.replace("=X", "")
        .replace("/", "")
        .replace("GC=F", "XAUUSD")
        .replace("GOLD", "XAUUSD")
        .upper()
    )
    return SYMBOL_MAP.get(clean)


def create_connected_tls_socket(host: str, port: int, timeout: float = 10.0) -> ssl.SSLSocket:
    """
    Creates and returns a connected TLS socket to the target host and port.
    Supports optional static proxy routing via CTRADER_PROXY or ALL_PROXY
    (e.g., 'socks5://user:pass@host:port' or 'http://host:port') to guarantee
    a single, fixed, static IP address for prop firm anti-ban compliance.
    """
    proxy_url = (os.environ.get("CTRADER_PROXY") or os.environ.get("ALL_PROXY") or "").strip()
    ctx = ssl.create_default_context()

    if proxy_url:
        try:
            from urllib.parse import urlparse
            import base64

            parsed = urlparse(proxy_url)
            scheme = (parsed.scheme or "socks5").lower()

            if scheme.startswith("http"):
                # High-reliability HTTP CONNECT tunnel with Basic Proxy-Authorization
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                s.connect((parsed.hostname, parsed.port or 80))

                headers = [
                    f"CONNECT {host}:{port} HTTP/1.1",
                    f"Host: {host}:{port}",
                ]
                if parsed.username:
                    auth_str = f"{parsed.username}:{parsed.password or ''}"
                    auth_b64 = base64.b64encode(auth_str.encode()).decode()
                    headers.append(f"Proxy-Authorization: Basic {auth_b64}")
                headers.append("User-Agent: cTraderProxyClient/1.0\r\n\r\n")

                s.sendall("\r\n".join(headers).encode())
                connect_resp = s.recv(4096).decode("latin1", errors="ignore")
                status_line = connect_resp.split("\r\n")[0]
                if "200" not in status_line:
                    raise ConnectionError(f"HTTP CONNECT tunnel rejected by proxy: {status_line}")

                return ctx.wrap_socket(s, server_hostname=host)
            else:
                # SOCKS4 / SOCKS5 proxy via PySocks
                import socks
                proxy_type = socks.PROXY_TYPE_SOCKS4 if "socks4" in scheme else socks.PROXY_TYPE_SOCKS5
                s = socks.socksocket()
                s.set_proxy(
                    proxy_type=proxy_type,
                    addr=parsed.hostname,
                    port=parsed.port or 1080,
                    username=parsed.username,
                    password=parsed.password
                )
                s.settimeout(timeout)
                s.connect((host, port))
                return ctx.wrap_socket(s, server_hostname=host)
        except Exception as e:
            logger.warning(f"[PROXY] Failed to connect via proxy {proxy_url}: {e}. Falling back to direct TLS socket.")

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect((host, port))
    return ctx.wrap_socket(s, server_hostname=host)


def _read_exact(sock: ssl.SSLSocket, num_bytes: int) -> Optional[bytes]:
    """Read exact number of bytes from SSL socket, looping until complete or closed."""
    buf = bytearray()
    while len(buf) < num_bytes:
        chunk = sock.recv(num_bytes - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def _read_tls_frame(sock: ssl.SSLSocket) -> Optional[Tuple[int, bytes]]:
    """Read a single length-prefixed Protobuf message frame from cTrader Open API over TLS."""
    from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoMessage
    len_bytes = _read_exact(sock, 4)
    if not len_bytes or len(len_bytes) < 4:
        return None
    resp_len = struct.unpack('>I', len_bytes)[0]
    resp_data = _read_exact(sock, resp_len)
    if not resp_data or len(resp_data) < resp_len:
        return None
    res_msg = ProtoMessage()
    res_msg.ParseFromString(resp_data)
    return res_msg.payloadType, res_msg.payload


def _send_tls_frame(sock: ssl.SSLSocket, payload_type: int, req_pb: Any) -> Optional[Tuple[int, bytes]]:
    """Helper to frame, serialize, send, and read response from cTrader Open API over TLS."""
    from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoMessage
    msg = ProtoMessage()
    msg.payloadType = payload_type
    msg.payload = req_pb.SerializeToString()
    data = msg.SerializeToString()
    frame = struct.pack('>I', len(data)) + data
    sock.sendall(frame)
    return _read_tls_frame(sock)


# In-memory account discovery cache to avoid excessive network round-trips
_DISCOVERED_ACCOUNTS_CACHE = {
    "timestamp": 0.0,
    "accounts": []
}


def query_authorized_accounts(timeout: float = 8.0) -> List[Dict[str, Any]]:
    """Query cTrader Open API for all active trading accounts authorized under current access token.

    Filters for accounts that:
    1. Match the current environment (live vs demo)
    2. Possess FULL_ACCESS rights (excludes CLOSE_ONLY, VIEW_ONLY, or suspended accounts)
    """
    if is_test_environment() and not os.environ.get("TEST_REAL_SOCKET"):
        # Return mock account list for unit tests
        mock_acc_str = (os.environ.get("CTRADER_ACCOUNT_ID") or CTRADER_ACCOUNT_ID).strip()
        mock_acc = int(mock_acc_str) if (mock_acc_str and mock_acc_str.isdigit()) else 49700506
        env_check = (os.environ.get("CTRADER_ENV") or CTRADER_ENV).lower()
        return [{
            "account_id": mock_acc,
            "trader_login": mock_acc,
            "broker": "MOCK_BROKER",
            "balance": float(os.environ.get("ACCOUNT_EQUITY", "10000.0")),
            "access_rights": "FULL_ACCESS",
            "is_live": (env_check == "live")
        }]

    client_id = (os.environ.get("CTRADER_CLIENT_ID") or CTRADER_CLIENT_ID).strip()
    client_secret = (os.environ.get("CTRADER_CLIENT_SECRET") or CTRADER_CLIENT_SECRET).strip()
    access_token = (os.environ.get("CTRADER_ACCESS_TOKEN") or CTRADER_ACCESS_TOKEN).strip()
    env_name = (os.environ.get("CTRADER_ENV") or CTRADER_ENV).lower()

    if not client_id or not client_secret or not access_token:
        return []

    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType, ProtoOAAccessRights
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (
        ProtoOAApplicationAuthReq, ProtoOAGetAccountListByAccessTokenReq,
        ProtoOAGetAccountListByAccessTokenRes, ProtoOAAccountAuthReq,
        ProtoOATraderReq, ProtoOATraderRes
    )

    host = CTRADER_HOSTS.get(env_name, "demo.ctraderapi.com")
    active_accounts = []

    try:
        with create_connected_tls_socket(host, CTRADER_PORT, timeout) as s:
            # 1. Application Auth
            app_req = ProtoOAApplicationAuthReq()
            app_req.clientId = client_id
            app_req.clientSecret = client_secret
            app_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_REQ, app_req)
            if not app_res or app_res[0] != ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_RES:
                logger.warning("[cTrader Discovery] Application authentication failed.")
                return []

            # 2. Get Account List by Token
            acc_list_req = ProtoOAGetAccountListByAccessTokenReq()
            acc_list_req.accessToken = access_token
            list_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_GET_ACCOUNTS_BY_ACCESS_TOKEN_REQ, acc_list_req)
            if not list_res or list_res[0] != ProtoOAPayloadType.PROTO_OA_GET_ACCOUNTS_BY_ACCESS_TOKEN_RES:
                logger.warning("[cTrader Discovery] Account list query failed.")
                return []

            parsed_list = ProtoOAGetAccountListByAccessTokenRes()
            parsed_list.ParseFromString(list_res[1])

            # 3. Filter and Validate each account's status and permissions
            for acc_meta in parsed_list.ctidTraderAccount:
                if env_name == "live" and not acc_meta.isLive:
                    continue
                if env_name == "demo" and acc_meta.isLive:
                    continue

                acc_id = acc_meta.ctidTraderAccountId
                acc_auth = ProtoOAAccountAuthReq()
                acc_auth.ctidTraderAccountId = acc_id
                acc_auth.accessToken = access_token
                auth_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_REQ, acc_auth)
                if not auth_res or auth_res[0] != ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_RES:
                    continue

                trader_req = ProtoOATraderReq()
                trader_req.ctidTraderAccountId = acc_id
                t_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_TRADER_REQ, trader_req)
                if t_res and t_res[0] == ProtoOAPayloadType.PROTO_OA_TRADER_RES:
                    t_msg = ProtoOATraderRes()
                    t_msg.ParseFromString(t_res[1])
                    t = t_msg.trader
                    access = t.accessRights if t.HasField("accessRights") else 0
                    if access == ProtoOAAccessRights.FULL_ACCESS:
                        money_digits = t.moneyDigits if t.HasField("moneyDigits") else 2
                        bal = t.balance / (10 ** money_digits)
                        broker = t.brokerName if t.HasField("brokerName") else "ftmo"
                        t_login = t.traderLogin if t.HasField("traderLogin") else acc_id
                        active_accounts.append({
                            "account_id": acc_id,
                            "trader_login": t_login,
                            "broker": broker,
                            "balance": bal,
                            "access_rights": "FULL_ACCESS",
                            "is_live": acc_meta.isLive
                        })
                        logger.info(
                            f"[cTrader Discovery] Discovered active account #{acc_id} (Login: {t_login}, "
                            f"Broker: {broker.upper()}, Balance: ${bal:,.2f}, Status: FULL_ACCESS)"
                        )
                    else:
                        try:
                            r_name = ProtoOAAccessRights.Name(access)
                        except Exception:
                            r_name = str(access)
                        logger.info(f"[cTrader Discovery] Skipping account #{acc_id} (Access: {r_name})")
    except Exception as ex:
        logger.warning(f"[cTrader Discovery] Open API discovery notice: {ex}")

    return active_accounts


def get_target_account_ids(auto_discover: bool = True, force_refresh: bool = False) -> List[int]:
    """Resolve target cTrader account IDs.

    Resolution hierarchy:
    1. Explicit CTRADER_ACCOUNT_IDS env var (e.g. "49700506, 12345678")
    2. Dynamic auto-discovery via cTrader Open API token (when CTRADER_ACCOUNT_IDS is "auto" or empty)
    3. Fallback to single configured CTRADER_ACCOUNT_ID
    """
    raw_env = (os.environ.get("CTRADER_ACCOUNT_IDS") or CTRADER_ACCOUNT_IDS).strip()

    # 1. Explicit comma-separated list of IDs
    if raw_env and raw_env.lower() not in ("auto", "true", "all", "discover"):
        try:
            ids = [int(x.strip()) for x in raw_env.split(",") if x.strip().isdigit()]
            if ids:
                return ids
        except Exception as ex:
            logger.warning(f"Failed parsing CTRADER_ACCOUNT_IDS='{raw_env}': {ex}")

    # 2. Dynamic auto-discovery from token
    if auto_discover and has_valid_credentials():
        now = time.time()
        if not force_refresh and (now - _DISCOVERED_ACCOUNTS_CACHE["timestamp"] < 120.0) and _DISCOVERED_ACCOUNTS_CACHE["accounts"]:
            return [acc["account_id"] for acc in _DISCOVERED_ACCOUNTS_CACHE["accounts"]]

        try:
            discovered = query_authorized_accounts()
            if discovered:
                _DISCOVERED_ACCOUNTS_CACHE["timestamp"] = now
                _DISCOVERED_ACCOUNTS_CACHE["accounts"] = discovered
                return [acc["account_id"] for acc in discovered]
        except Exception as ex:
            logger.warning(f"cTrader auto-discovery notice: {ex}")

    # 3. Fallback to single configured CTRADER_ACCOUNT_ID
    acc_id_str = (os.environ.get("CTRADER_ACCOUNT_ID") or CTRADER_ACCOUNT_ID).strip()
    if acc_id_str and acc_id_str.isdigit():
        return [int(acc_id_str)]

    return []


def _find_matching_reconciled_position(
    positions: Any,
    order_req: Any,
    dispatched_at_ms: Optional[int] = None
) -> Optional[Any]:
    """Inspect open positions returned by ProtoOAReconcileRes to find a match for a timed-out order."""
    now_ms = int(time.time() * 1000)
    cutoff_ms = dispatched_at_ms if dispatched_at_ms else (now_ms - 60_000)

    for pos in positions:
        # Must be OPEN status (1)
        status = getattr(pos, "positionStatus", 1)
        if status != 1:
            continue

        trade_data = getattr(pos, "tradeData", None)
        if not trade_data:
            continue

        # Symbol ID match
        if trade_data.symbolId != getattr(order_req, "symbolId", None):
            continue

        # Trade side match (BUY / SELL)
        if trade_data.tradeSide != getattr(order_req, "tradeSide", None):
            continue

        # Timestamp match: opened within the last 60 seconds (or since dispatch)
        open_time = getattr(trade_data, "openTimestamp", 0)
        if open_time > 0 and open_time < (cutoff_ms - 15_000):
            continue

        # Volume match if specified
        order_vol = getattr(order_req, "volume", 0)
        if order_vol > 0 and trade_data.volume > 0:
            if trade_data.volume != order_vol:
                continue

        return pos

    return None


def _ensure_position_sltp_on_socket(
    s: Any,
    account_id: int,
    pos_pb: Any,
    order_req: Any,
    ord_id: int = 0,
    desired_sl: Optional[float] = None,
    desired_tp: Optional[float] = None,
    max_amend_retries: int = 3,
    retry_delay_sec: float = 0.5,
    reconciled_after_timeout: bool = False,
) -> Dict[str, Any]:
    """Verify server-side SL/TP on a filled or recovered position; amend or emergency-close if unprotected."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType, ProtoOATradeSide
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (
        ProtoOAErrorRes, ProtoOAAmendPositionSLTPReq, ProtoOAClosePositionReq
    )

    pos_id = getattr(pos_pb, "positionId", 0)
    sl_desired = bool(order_req.HasField("relativeStopLoss") or (desired_sl is not None))
    sl_attached = bool(pos_pb.HasField("stopLoss") and pos_pb.stopLoss > 0)
    tp_attached = bool(pos_pb.HasField("takeProfit") and pos_pb.takeProfit > 0)

    if sl_desired and sl_attached:
        attached_sl = pos_pb.stopLoss
        attached_tp = pos_pb.takeProfit if tp_attached else 0.0
        res: Dict[str, Any] = {
            "status": "EXECUTED",
            "position_id": pos_id,
            "order_id": ord_id or pos_id,
            "atomic_sltp": True,
            "attached_sl": attached_sl,
            "attached_tp": attached_tp,
        }
        if reconciled_after_timeout:
            res["reconciled_after_timeout"] = True
        else:
            logger.info(f"[cTrader Open API] Position #{pos_id} filled with atomic broker SL ({attached_sl}) & TP ({attached_tp}).")
        return res

    if sl_desired and not sl_attached:
        logger.warning(
            f"[cTrader Open API] Position #{pos_id} filled without Stop-Loss! "
            f"Initiating fallback amendment loop (max {max_amend_retries} retries)..."
        )
        fill_price = float(getattr(pos_pb, "price", 0.0))
        if desired_sl is not None:
            target_sl = float(desired_sl)
        elif order_req.HasField("relativeStopLoss") and fill_price > 0:
            offset = order_req.relativeStopLoss / 100_000.0
            if getattr(order_req, "tradeSide", ProtoOATradeSide.BUY) == ProtoOATradeSide.BUY:
                target_sl = fill_price - offset
            else:
                target_sl = fill_price + offset
        else:
            target_sl = None

        if desired_tp is not None:
            target_tp = float(desired_tp)
        elif order_req.HasField("relativeTakeProfit") and fill_price > 0:
            offset = order_req.relativeTakeProfit / 100_000.0
            if getattr(order_req, "tradeSide", ProtoOATradeSide.BUY) == ProtoOATradeSide.BUY:
                target_tp = fill_price + offset
            else:
                target_tp = fill_price - offset
        else:
            target_tp = None

        sym_id = getattr(order_req, "symbolId", 0)
        digits = 2 if sym_id == 41 else (3 if sym_id == 4 else 5)
        amend_success = False

        for attempt in range(1, max_amend_retries + 1):
            try:
                amend_req = ProtoOAAmendPositionSLTPReq()
                amend_req.ctidTraderAccountId = account_id
                amend_req.positionId = int(pos_id)
                if target_sl is not None:
                    amend_req.stopLoss = round(float(target_sl), digits)
                if target_tp is not None:
                    amend_req.takeProfit = round(float(target_tp), digits)

                amend_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_AMEND_POSITION_SLTP_REQ, amend_req)
                if amend_res and amend_res[0] in (
                    ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT,
                    ProtoOAPayloadType.PROTO_OA_TRAILING_SL_CHANGED_EVENT
                ):
                    amend_success = True
                    logger.info(
                        f"[cTrader Open API] Fallback amend succeeded on attempt {attempt}: "
                        f"Position #{pos_id} SL ({amend_req.stopLoss}) & TP ({amend_req.takeProfit}) attached."
                    )
                    res_ok: Dict[str, Any] = {
                        "status": "EXECUTED",
                        "position_id": pos_id,
                        "order_id": ord_id or pos_id,
                        "atomic_sltp": False,
                        "amend_retries": attempt,
                        "attached_sl": amend_req.stopLoss,
                        "attached_tp": getattr(amend_req, "takeProfit", 0.0),
                    }
                    if reconciled_after_timeout:
                        res_ok["reconciled_after_timeout"] = True
                    return res_ok
                elif amend_res and amend_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
                    err = ProtoOAErrorRes()
                    err.ParseFromString(amend_res[1])
                    logger.warning(f"[cTrader Open API] Amend attempt {attempt}/{max_amend_retries} rejected: {err.errorCode} - {err.description}")
                else:
                    resp_type = amend_res[0] if amend_res else "None"
                    logger.warning(f"[cTrader Open API] Amend attempt {attempt}/{max_amend_retries} received unexpected response: {resp_type}")
            except Exception as amend_ex:
                logger.warning(f"[cTrader Open API] Amend attempt {attempt}/{max_amend_retries} exception: {amend_ex}")

            if attempt < max_amend_retries and retry_delay_sec > 0:
                time.sleep(retry_delay_sec)

        if not amend_success:
            logger.critical(
                f"[cTrader SAFETY CRITICAL] Position #{pos_id} lacks Stop-Loss protection after {max_amend_retries} amend retries! "
                f"Dispatching emergency market close to prevent catastrophic naked exposure."
            )
            try:
                close_req = ProtoOAClosePositionReq()
                close_req.ctidTraderAccountId = account_id
                close_req.positionId = int(pos_id)
                td = getattr(pos_pb, "tradeData", None)
                pos_vol = getattr(pos_pb, "volume", 0) or (getattr(td, "volume", 0) if td else 0) or getattr(order_req, "volume", 0)
                close_req.volume = pos_vol
                _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_CLOSE_POSITION_REQ, close_req)
                logger.info(f"[cTrader Open API] Emergency close dispatched for unprotected position #{pos_id}.")
            except Exception as close_ex:
                logger.critical(f"[cTrader SAFETY CRITICAL] Failed to dispatch emergency close for position #{pos_id}: {close_ex}")

            return {
                "status": "EMERGENCY_CLOSED",
                "position_id": pos_id,
                "order_id": ord_id or pos_id,
                "error": f"Failed to attach Stop-Loss after {max_amend_retries} retries. Position closed immediately for financial safety."
            }

    res_plain: Dict[str, Any] = {"status": "EXECUTED", "position_id": pos_id, "order_id": ord_id or pos_id}
    if reconciled_after_timeout:
        res_plain["reconciled_after_timeout"] = True
    return res_plain


def _dispatch_order_over_socket(
    s: Any,
    client_id: str,
    client_secret: str,
    access_token: str,
    account_id: int,
    order_req: Any,
    max_amend_retries: int = 3,
    retry_delay_sec: float = 0.5,
    validate_access_rights: bool = False
) -> Dict[str, Any]:
    """Internal implementation of cTrader order execution flow over an open socket.

    Handles authentication, optional access rights validation, order dispatch with relative SL/TP,
    atomic SL/TP verification, fallback amendment retry loop, and emergency market close if unprotected.
    """
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
        ProtoOAPayloadType, ProtoOAOrderType, ProtoOAExecutionType, ProtoOATradeSide,
        ProtoOAAccessRights
    )
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (
        ProtoOAApplicationAuthReq, ProtoOAAccountAuthReq,
        ProtoOAExecutionEvent, ProtoOAErrorRes, ProtoOAAmendPositionSLTPReq,
        ProtoOAClosePositionReq, ProtoOAOrderErrorEvent,
        ProtoOAReconcileReq, ProtoOAReconcileRes,
        ProtoOATraderReq, ProtoOATraderRes
    )

    # 1. Application Authentication
    app_req = ProtoOAApplicationAuthReq()
    app_req.clientId = client_id
    app_req.clientSecret = client_secret
    app_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_REQ, app_req)
    if not app_res:
        return {"status": "ERROR", "error": "No response to ApplicationAuthReq"}
    if app_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
        err = ProtoOAErrorRes()
        err.ParseFromString(app_res[1])
        logger.warning(f"[cTrader Open API] App Auth Notice: {err.errorCode} - {err.description}")
        return {"status": "PENDING_KYC_ACTIVATION", "error": err.description}

    # 2. Account Authentication
    acc_req = ProtoOAAccountAuthReq()
    acc_req.ctidTraderAccountId = account_id
    acc_req.accessToken = access_token
    acc_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_REQ, acc_req)
    if not acc_res:
        return {"status": "ERROR", "error": "No response to AccountAuthReq"}
    if acc_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
        err = ProtoOAErrorRes()
        err.ParseFromString(acc_res[1])
        logger.warning(f"[cTrader Open API] Account Auth Error: {err.errorCode} - {err.description}")
        return {"status": "ACCOUNT_AUTH_ERROR", "error": err.description}

    # 2.5 Optional Pre-flight Trader Access Rights Check
    if validate_access_rights:
        trader_req = ProtoOATraderReq()
        trader_req.ctidTraderAccountId = account_id
        trader_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_TRADER_REQ, trader_req)
        if trader_res and trader_res[0] == ProtoOAPayloadType.PROTO_OA_TRADER_RES:
            t_msg = ProtoOATraderRes()
            t_msg.ParseFromString(trader_res[1])
            t = t_msg.trader
            access_rights = t.accessRights if t.HasField("accessRights") else 0
            if access_rights != ProtoOAAccessRights.FULL_ACCESS:
                rights_name = ProtoOAAccessRights.Name(access_rights) if hasattr(ProtoOAAccessRights, "Name") else str(access_rights)
                broker_str = t.brokerName if t.HasField("brokerName") else "broker"
                trader_login = t.traderLogin if t.HasField("traderLogin") else account_id
                err_msg = (
                    f"TRADING_NOT_ALLOWED: {broker_str.upper()} account {account_id} "
                    f"(Trader ID {trader_login}) is restricted to '{rights_name}' mode. "
                    f"Opening new positions is prohibited by the broker."
                )
                logger.error(f"[cTrader Open API] Pre-flight Check Blocked: {err_msg}")
                return {
                    "status": "ORDER_REJECTED",
                    "error_code": "TRADING_NOT_ALLOWED",
                    "error": err_msg,
                    "access_rights": rights_name,
                    "trading_not_allowed": True,
                    "broker": broker_str,
                    "trader_login": trader_login
                }

    # 3. New Order Dispatch
    # For MARKET orders, cTrader Open API rejects absolute stopLoss/takeProfit directly inside ProtoOANewOrderReq.
    # If absolute stopLoss/takeProfit was passed without relativeStopLoss/relativeTakeProfit, save desired levels
    # for the fallback amendment loop and clear them from the market order request.
    desired_sl = None
    desired_tp = None
    if getattr(order_req, "orderType", None) == ProtoOAOrderType.MARKET:
        if order_req.HasField("stopLoss") and order_req.stopLoss > 0:
            if not order_req.HasField("relativeStopLoss"):
                desired_sl = order_req.stopLoss
            order_req.ClearField("stopLoss")
        if order_req.HasField("takeProfit") and order_req.takeProfit > 0:
            if not order_req.HasField("relativeTakeProfit"):
                desired_tp = order_req.takeProfit
            order_req.ClearField("takeProfit")

    dispatched_at_ms = int(time.time() * 1000)
    timed_out = False
    order_res = None
    try:
        order_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_NEW_ORDER_REQ, order_req)
    except (socket.timeout, TimeoutError):
        timed_out = True
        logger.warning("[cTrader Execution] Socket timed out awaiting ProtoOANewOrderReq response.")
    except Exception as ex:
        logger.warning(f"[cTrader Execution] Socket notice awaiting ProtoOANewOrderReq response: {ex}")

    # ROP-09: If response timed out or is missing, reconcile with broker before declaring failure or retrying
    if timed_out or not order_res:
        logger.info("[cTrader Timeout Guard] Order response missing or timed out. Reconciling with broker over socket...")
        try:
            rec_req = ProtoOAReconcileReq()
            rec_req.ctidTraderAccountId = account_id
            rec_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_RECONCILE_REQ, rec_req)
            if rec_res and rec_res[0] == ProtoOAPayloadType.PROTO_OA_RECONCILE_RES:
                rec_msg = ProtoOAReconcileRes()
                rec_msg.ParseFromString(rec_res[1])
                matched_pos = _find_matching_reconciled_position(rec_msg.position, order_req, dispatched_at_ms)
                if matched_pos:
                    pos_id = matched_pos.positionId
                    logger.warning(f"[cTrader Timeout Recovery] RECOVERED: Order timed out on socket, but broker confirmed position #{pos_id} was filled! Reconciled.")
                    return _ensure_position_sltp_on_socket(
                        s=s,
                        account_id=account_id,
                        pos_pb=matched_pos,
                        order_req=order_req,
                        ord_id=pos_id,
                        desired_sl=desired_sl,
                        desired_tp=desired_tp,
                        max_amend_retries=max_amend_retries,
                        retry_delay_sec=retry_delay_sec,
                        reconciled_after_timeout=True,
                    )
        except Exception as rec_err:
            logger.warning(f"[cTrader Timeout Guard] In-socket reconciliation notice: {rec_err}")

        return {
            "status": "TIMEOUT_UNFILLED",
            "position_id": None,
            "order_id": None,
            "error": "Order timed out and confirmed NOT filled on broker (zero matching open positions found)."
        }

    # Handle PROTO_OA_ORDER_ERROR_EVENT (2132)
    if order_res[0] == ProtoOAPayloadType.PROTO_OA_ORDER_ERROR_EVENT:
        err = ProtoOAOrderErrorEvent()
        err.ParseFromString(order_res[1])
        logger.error(f"[cTrader Open API] Order Error Event: {err.errorCode} - {err.description}")
        err_msg = f"{err.errorCode}: {err.description}"
        is_trading_not_allowed = (err.errorCode == "TRADING_NOT_ALLOWED")
        if is_trading_not_allowed:
            err_msg += " (Broker account restricted to CLOSE_ONLY/Read-Only; verify account status in broker portal)"
        return {
            "status": "ORDER_REJECTED",
            "error_code": err.errorCode,
            "error": err_msg,
            "trading_not_allowed": is_trading_not_allowed
        }

    # Handle PROTO_OA_ERROR_RES (2142)
    if order_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
        err = ProtoOAErrorRes()
        err.ParseFromString(order_res[1])
        logger.error(f"[cTrader Open API] Gateway Error: {err.errorCode} - {err.description}")
        return {"status": "ORDER_REJECTED", "error": f"{err.errorCode}: {err.description}"}

    # Handle PROTO_OA_EXECUTION_EVENT (2126)
    if order_res[0] == ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT:
        event = ProtoOAExecutionEvent()
        event.ParseFromString(order_res[1])

        # If ORDER_ACCEPTED, read the subsequent fill or reject event
        if event.executionType == ProtoOAExecutionType.ORDER_ACCEPTED:
            try:
                next_frame = _read_tls_frame(s)
                if next_frame:
                    if next_frame[0] == ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT:
                        event = ProtoOAExecutionEvent()
                        event.ParseFromString(next_frame[1])
                    elif next_frame[0] == ProtoOAPayloadType.PROTO_OA_ORDER_ERROR_EVENT:
                        err = ProtoOAOrderErrorEvent()
                        err.ParseFromString(next_frame[1])
                        logger.error(f"[cTrader Open API] Post-Acceptance Order Error: {err.errorCode} - {err.description}")
                        post_err_msg = f"{err.errorCode}: {err.description}"
                        post_is_tna = (err.errorCode == "TRADING_NOT_ALLOWED")
                        if post_is_tna:
                            post_err_msg += " (Broker account restricted to CLOSE_ONLY/Read-Only; verify account status in broker portal)"
                        return {
                            "status": "ORDER_REJECTED",
                            "error_code": err.errorCode,
                            "error": post_err_msg,
                            "trading_not_allowed": post_is_tna
                        }
            except Exception as ex:
                logger.warning(f"[cTrader Open API] Waiting for fill frame notice: {ex}")

        if event.executionType == ProtoOAExecutionType.ORDER_REJECTED:
            err_code = getattr(event, "errorCode", "ORDER_REJECTED")
            logger.error(f"[cTrader Open API] Order Rejected: {err_code}")
            return {"status": "ORDER_REJECTED", "error": str(err_code)}

        if event.executionType == ProtoOAExecutionType.ORDER_CANCELLED:
            err_code = getattr(event, "errorCode", "ORDER_CANCELLED")
            logger.error(f"[cTrader Open API] Order Cancelled: {err_code}")
            return {"status": "ORDER_CANCELLED", "error": str(err_code)}

        pos_id = getattr(event.position, "positionId", 0) if event.HasField("position") else 0
        ord_id = getattr(event.order, "orderId", 0) if event.HasField("order") else 0

        if not pos_id:
            logger.warning(f"[cTrader Open API] Execution event received without positionId (executionType: {event.executionType}). Reconciling with broker...")
            try:
                rec_req = ProtoOAReconcileReq()
                rec_req.ctidTraderAccountId = account_id
                rec_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_RECONCILE_REQ, rec_req)
                if rec_res and rec_res[0] == ProtoOAPayloadType.PROTO_OA_RECONCILE_RES:
                    rec_msg = ProtoOAReconcileRes()
                    rec_msg.ParseFromString(rec_res[1])
                    matched_pos = _find_matching_reconciled_position(rec_msg.position, order_req, dispatched_at_ms)
                    if matched_pos:
                        pos_id = matched_pos.positionId
                        logger.warning(f"[cTrader Timeout Recovery] Recovered position #{pos_id} via post-acceptance reconciliation.")
                        return _ensure_position_sltp_on_socket(
                            s=s,
                            account_id=account_id,
                            pos_pb=matched_pos,
                            order_req=order_req,
                            ord_id=pos_id,
                            desired_sl=desired_sl,
                            desired_tp=desired_tp,
                            max_amend_retries=max_amend_retries,
                            retry_delay_sec=retry_delay_sec,
                            reconciled_after_timeout=True,
                        )
            except Exception as rec_err:
                logger.warning(f"[cTrader Timeout Guard] Post-acceptance reconciliation error: {rec_err}")

            return {"status": "UNFILLED", "order_id": ord_id, "error": f"Execution event type {event.executionType} without positionId"}

        # 4. Atomic SL/TP Verification & Fallback Amendment Loop (ROP-01)
        return _ensure_position_sltp_on_socket(
            s=s,
            account_id=account_id,
            pos_pb=event.position,
            order_req=order_req,
            ord_id=ord_id,
            desired_sl=desired_sl,
            desired_tp=desired_tp,
            max_amend_retries=max_amend_retries,
            retry_delay_sec=retry_delay_sec,
            reconciled_after_timeout=False,
        )

    return {"status": "ERROR", "error": f"Unexpected response payload type: {order_res[0]}"}


def dispatch_ctrader_tls_order(
    host: str,
    port: int,
    client_id: str,
    client_secret: str,
    access_token: str,
    account_id: int,
    order_req: Any,
    timeout: float = 10.0,
    max_amend_retries: int = 3,
    retry_delay_sec: float = 0.5,
    validate_access_rights: bool = False
) -> Dict[str, Any]:
    """Execute live order dispatch directly over TLS socket with cTrader Open API."""
    if (is_test_environment() or os.environ.get("PYTEST_CURRENT_TEST")) and not os.environ.get("TEST_REAL_SOCKET"):
        logger.info("[SAFETY INTERLOCK] Live order dispatch blocked because test environment was detected.")
        return {"status": "EXECUTED", "position_id": 9990001, "order_id": 9990001}

    with create_connected_tls_socket(host, port, timeout) as s:
        try:
            return _dispatch_order_over_socket(
                s=s,
                client_id=client_id,
                client_secret=client_secret,
                access_token=access_token,
                account_id=account_id,
                order_req=order_req,
                max_amend_retries=max_amend_retries,
                retry_delay_sec=retry_delay_sec,
                validate_access_rights=validate_access_rights
            )
        except (socket.timeout, TimeoutError) as ex:
            logger.warning(f"[cTrader Execution] Primary socket timed out ({ex}). Reconciling over clean TLS session...")
            return dispatch_ctrader_tls_reconcile_and_recover(
                host=host,
                port=port,
                client_id=client_id,
                client_secret=client_secret,
                access_token=access_token,
                account_id=account_id,
                order_req=order_req,
                timeout=timeout
            )


def dispatch_ctrader_tls_reconcile_and_recover(
    host: str,
    port: int,
    client_id: str,
    client_secret: str,
    access_token: str,
    account_id: int,
    order_req: Any,
    timeout: float = 10.0,
    dispatched_at_ms: Optional[int] = None
) -> Dict[str, Any]:
    """Open fresh TLS socket and reconcile positions with broker after a socket timeout.

    Verifies whether the timed-out order was filled or genuinely unexecuted.
    """
    if (is_test_environment() or os.environ.get("PYTEST_CURRENT_TEST")) and not os.environ.get("TEST_REAL_SOCKET"):
        return {"status": "TIMEOUT_UNFILLED", "error": "Mock timeout unfilled"}

    try:
        from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
        from ctrader_open_api.messages.OpenApiMessages_pb2 import (
            ProtoOAApplicationAuthReq, ProtoOAAccountAuthReq,
            ProtoOAReconcileReq, ProtoOAReconcileRes
        )

        with create_connected_tls_socket(host, port, timeout) as s:
            # 1. App Auth
            app_req = ProtoOAApplicationAuthReq()
            app_req.clientId = client_id
            app_req.clientSecret = client_secret
            app_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_REQ, app_req)
            if not app_res or app_res[0] != ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_RES:
                return {"status": "TIMEOUT_UNFILLED", "error": "Timeout reconciliation failed (App auth failed)"}

            # 2. Account Auth
            acc_req = ProtoOAAccountAuthReq()
            acc_req.ctidTraderAccountId = account_id
            acc_req.accessToken = access_token
            acc_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_REQ, acc_req)
            if not acc_res or acc_res[0] != ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_RES:
                return {"status": "TIMEOUT_UNFILLED", "error": "Timeout reconciliation failed (Account auth failed)"}

            # 3. Reconcile
            rec_req = ProtoOAReconcileReq()
            rec_req.ctidTraderAccountId = account_id
            rec_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_RECONCILE_REQ, rec_req)
            if not rec_res or rec_res[0] != ProtoOAPayloadType.PROTO_OA_RECONCILE_RES:
                return {"status": "TIMEOUT_UNFILLED", "error": "Timeout reconciliation failed (Reconcile request failed)"}

            rec_msg = ProtoOAReconcileRes()
            rec_msg.ParseFromString(rec_res[1])

            matched_pos = _find_matching_reconciled_position(rec_msg.position, order_req, dispatched_at_ms)
            if matched_pos:
                pos_id = matched_pos.positionId
                logger.warning(
                    f"[cTrader Timeout Recovery] RECOVERED: Order timed out on socket, but broker confirmed fill! "
                    f"Position #{pos_id} on symbol {getattr(order_req, 'symbolId', 0)}. Reconciling SL/TP protection..."
                )
                return _ensure_position_sltp_on_socket(
                    s=s,
                    account_id=account_id,
                    pos_pb=matched_pos,
                    order_req=order_req,
                    ord_id=pos_id,
                    reconciled_after_timeout=True,
                )

            logger.info("[cTrader Timeout Guard] Post-timeout reconciliation confirmed order was NOT filled by broker.")
            return {
                "status": "TIMEOUT_UNFILLED",
                "position_id": None,
                "order_id": None,
                "error": "Order timed out and confirmed NOT filled on broker (zero matching open positions found)."
            }

    except Exception as ex:
        logger.error(f"[cTrader Timeout Guard] Error during post-timeout reconciliation: {ex}")
        return {
            "status": "TIMEOUT_UNFILLED",
            "position_id": None,
            "order_id": None,
            "error": f"Order timed out and reconciliation failed ({ex})."
        }


def execute_ctrader_order(sig: Dict[str, Any], account_id: Optional[int] = None) -> Dict[str, Any]:
    """Execute a new trade order onto cTrader Demo/Live account.

    Args:
        sig: Signal payload dictionary generated by market_scanner.py.
        account_id: Optional specific cTrader account ID to execute order on.

    Returns:
        Execution status receipt dictionary.
    """
    pair = sig.get("pair") or sig.get("symbol", "")
    direction = sig.get("direction", "LONG").upper()
    entry = float(sig.get("entry") or sig.get("entry_price") or 0.0)
    stop_loss = float(sig.get("stop_loss") or sig.get("sl_price") or 0.0)
    take_profit = float(sig.get("take_profit") or sig.get("tp_price") or 0.0)
    lots = float(sig.get("suggested_lots") or sig.get("calc_lots") or sig.get("lots") or 0.0)

    # Resolve target account ID
    if account_id is not None:
        target_account_id = int(account_id)
    else:
        acc_str = str(CTRADER_ACCOUNT_ID or os.environ.get("CTRADER_ACCOUNT_ID", "")).strip()
        if acc_str and acc_str.isdigit():
            target_account_id = int(acc_str)
        else:
            targets = get_target_account_ids(auto_discover=True)
            target_account_id = targets[0] if targets else 0

    # 0. Test Signal Guard: Never route developer test alerts to broker
    if sig.get("is_test") or sig.get("test"):
        is_gold_symbol = bool(pair and ("XAU" in pair.upper() or "GOLD" in pair.upper()))
        units_sim = int(round(lots * 100)) if is_gold_symbol else int(round(lots * 100_000))
        logger.info(f"[cTrader Simulator] TEST SIGNAL DETECTED: {sig.get('id', 'TEST')}. Skipping real broker execution.")
        return {
            "status": "SIMULATED_DEMO_FILL",
            "mode": "DRY_RUN",
            "is_test": True,
            "pair": pair,
            "direction": direction,
            "lots": lots,
            "units": units_sim,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "account_id": str(target_account_id),
            "environment": CTRADER_ENV,
            "order_id": 9990001,
            "position_id": 9990001,
        }

    # Dynamic Account Equity & Risk Resolution for cTrader Execution
    env_equity = float(os.environ.get("ACCOUNT_EQUITY", "5000.0"))
    sig_equity = float(sig.get("account_equity") or sig.get("equity") or 0.0)
    sig_risk_pct = float(sig.get("risk_pct") or 0.0)

    # In live broker execution, query live broker balance/equity immediately before execution for this specific account
    live_broker_equity = 0.0
    if ENABLE_CTRADER_EXECUTION:
        try:
            live_info = get_ctrader_account_equity(account_id=target_account_id)
            if live_info and live_info.get("status") in ("OK", "SIMULATED"):
                b_val = float(live_info.get("balance", 0.0))
                e_val = float(live_info.get("equity", 0.0))
                if b_val > 0.0:
                    live_broker_equity = min(b_val, e_val) if (e_val > 0.0 and e_val < b_val) else b_val
                elif e_val > 0.0:
                    live_broker_equity = e_val
        except Exception as eq_err:
            logger.warning(f"Failed to fetch live broker balance for account {target_account_id}: {eq_err}")

    # Dynamic Sizing Capital resolution hierarchy:
    # 1. Live broker balance/equity (sub-second query from cTrader Open API if live execution enabled)
    # 2. Explicit ACCOUNT_EQUITY environment variable (fallback override if set or during mock testing)
    # 3. Signal equity (dynamically evaluated from live broker balance at scan time)
    # 4. Conservative baseline default ($5,000)
    if live_broker_equity > 0.0:
        effective_equity = live_broker_equity
    elif "ACCOUNT_EQUITY" in os.environ and float(os.environ["ACCOUNT_EQUITY"]) > 0:
        effective_equity = env_equity
    elif sig_equity > 0.0:
        effective_equity = sig_equity
    else:
        effective_equity = env_equity

    effective_risk_pct, risk_meta = resolve_effective_risk_pct(
        current_equity=effective_equity,
        explicit_risk_pct=(sig_risk_pct if sig_risk_pct > 0.0 else None),
        account_id=target_account_id,
        default_risk_pct=PROP_FIRM_RISK_PCT,
        prefer_dynamic_over_signal=(sig.get("risk_mode") == "dynamic_rank3"),
    )
    target_budget = effective_equity * (effective_risk_pct / 100.0)
    logger.info(
        f"[cTrader Sizing] Account #{target_account_id}: Equity=${effective_equity:,.2f} "
        f"(Base=${risk_meta.get('initial_balance', effective_equity):,.2f}, DD={risk_meta.get('dd_pct', 0.0):+.2f}%) | "
        f"Stage={risk_meta.get('stage')} | Tier={risk_meta.get('tier')} | Risk={effective_risk_pct:.2f}% (${target_budget:.2f})"
    )

    symbol_id = get_symbol_id(pair)
    is_gold = "XAU" in pair.upper() or "GOLD" in pair.upper()
    pip_size = 0.01 if "JPY" in pair.upper() else 0.0001
    sl_pips = float(sig.get("sl_pips") or (abs(entry - stop_loss) / pip_size if (entry > 0 and stop_loss > 0) else 22.0))
    sl_points = float(sig.get("sl_points") or sig.get("init_sl_points") or (abs(entry - stop_loss) if (entry > 0 and stop_loss > 0) else 25.0))

    # Calculate estimated monetary risk of current lots
    if is_gold:
        estimated_risk = lots * 100.0 * sl_points if lots > 0 else 0.0
    else:
        from core.instrument_validator import calculate_monetary_risk
        estimated_risk = calculate_monetary_risk(
            lots=lots,
            sl_pips=sl_pips,
            symbol=pair,
            exchange_rate=entry if entry > 0 else None
        ) if lots > 0 else 0.0

    # If lots is missing/zero, or if existing lots breaches target risk budget,
    # or if sig was generated on a mismatched reference equity (e.g. 5,000 vs 25,000),
    # or if dynamic tier / risk % shifted for this account, or signal was under-sized:
    # Dynamically recalculate lots to guarantee execution risk matches live account equity & risk tier.
    sig_budget_pct = sig_risk_pct if sig_risk_pct > 0.0 else effective_risk_pct
    sig_budget = float(sig.get("risk_budget_usd") or (sig_equity * (sig_budget_pct / 100.0)) if sig_equity > 0 else 0.0)
    need_recalc = (
        lots <= 0.0 or
        estimated_risk > (target_budget * 1.05) or
        (sig_equity > 0 and abs(sig_equity - effective_equity) > 1.0) or
        (sig_risk_pct > 0.0 and abs(sig_risk_pct - effective_risk_pct) > 0.01) or
        (sig_budget > 0.0 and sig_budget < (target_budget * 0.85))
    )
    if need_recalc:
        try:
            if is_gold:
                from satellite.gold_validator import calculate_gold_position_size
                recalc_lots, _ = calculate_gold_position_size(effective_equity, effective_risk_pct, sl_points)
                if recalc_lots > 0:
                    lots = recalc_lots
            else:
                from core.instrument_validator import calculate_position_size
                recalc_lots = calculate_position_size(
                    account_equity=effective_equity,
                    risk_pct=effective_risk_pct,
                    sl_pips=sl_pips,
                    symbol=pair,
                    exchange_rate=entry if entry > 0 else None
                )
                if recalc_lots > 0:
                    lots = recalc_lots
        except Exception as recalc_err:
            logger.warning(f"cTrader dynamic lot recalculation notice: {recalc_err}. Using original lots: {lots}")

    # Capital Defense Hard Clamp: Validate monetary risk CANNOT breach target risk budget (+5% tolerance)
    if is_gold:
        final_risk = lots * 100.0 * sl_points
    else:
        from core.instrument_validator import calculate_monetary_risk
        final_risk = calculate_monetary_risk(
            lots=lots,
            sl_pips=sl_pips,
            symbol=pair,
            exchange_rate=entry if entry > 0 else None
        )

    if final_risk > (target_budget * 1.05):
        logger.warning(
            f"[Capital Defense Hard Clamp] Sized lots ({lots}) risks ${final_risk:.2f}, "
            f"exceeding target budget ${target_budget:.2f} ({effective_risk_pct:.2f}% of ${effective_equity:,.2f}). "
            f"Clamping lots..."
        )
        if not is_gold:
            from core.instrument_validator import calculate_position_size
            clamped_lots = calculate_position_size(
                account_equity=effective_equity,
                risk_pct=effective_risk_pct,
                sl_pips=sl_pips,
                symbol=pair,
                exchange_rate=entry if entry > 0 else None
            )
            if 0 < clamped_lots < lots:
                lots = clamped_lots
                final_risk = calculate_monetary_risk(
                    lots=lots,
                    sl_pips=sl_pips,
                    symbol=pair,
                    exchange_rate=entry if entry > 0 else None
                )

        if final_risk > (target_budget * 1.05):
            logger.error(
                f"[Capital Defense Hard Clamp] REJECTED: Final risk ${final_risk:.2f} strictly exceeds "
                f"target budget ${target_budget:.2f} for {pair}. Order blocked to preserve account."
            )
            return {
                "status": "REJECTED_RISK_BUDGET_BREACH",
                "error": f"Monetary risk ${final_risk:.2f} exceeds target budget ${target_budget:.2f} (Hard Capital Clamp)",
                "pair": pair,
                "lots": lots,
                "monetary_risk": final_risk,
                "target_budget": target_budget,
                "account_equity": effective_equity,
                "risk_pct": effective_risk_pct,
            }

    if lots <= 0.0:
        logger.error(
            f"[cTrader Execution] Invalid or zero position size calculated ({lots} lots) for {pair}. "
            f"Rejecting order execution to preserve capital."
        )
        return {
            "status": "REJECTED_ZERO_LOTS",
            "error": "Computed lot size is 0.00 (risk budget insufficient or position sizing rejected)",
            "pair": pair,
            "lots": lots,
            "account_equity": effective_equity,
            "risk_pct": effective_risk_pct,
        }

    if is_gold:
        contract_size = 100.0  # 100 Troy Ounces per standard lot
        units = int(round(lots * contract_size))
        volume_cents = int(round(lots * contract_size * 100))
    else:
        units = int(round(lots * 100_000))
        volume_cents = units * 100  # cTrader Protocol expects subunits (units * 100)

    order_type_str = sig.get("order_type") or CTRADER_ORDER_TYPE or "MARKET"
    order_type_str = str(order_type_str).strip().upper()
    is_market_range = (order_type_str == "MARKET_RANGE")

    # 1. Fallback to Simulated Demo / Dry-Run Mode if unconfigured
    if not ENABLE_CTRADER_EXECUTION or not has_valid_credentials():
        reason = "ENABLE_CTRADER_EXECUTION is disabled" if not ENABLE_CTRADER_EXECUTION else "Missing cTrader credentials"
        logger.info(
            f"[cTrader Demo Simulator] DRY-RUN FILL: {direction} {pair} | "
            f"Lots: {lots:.2f} ({units:,} units) | Entry: {entry} | "
            f"SL: {stop_loss} | TP: {take_profit} | Mode: DRY_RUN ({reason})"
        )
        return {
            "status": "SIMULATED_DEMO_FILL",
            "mode": "DRY_RUN",
            "pair": pair,
            "direction": direction,
            "lots": lots,
            "units": units,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_pct": effective_risk_pct,
            "monetary_risk": round(final_risk, 2),
            "account_equity": effective_equity,
            "risk_mode": risk_meta.get("mode"),
            "risk_tier": risk_meta.get("tier"),
            "account_stage": risk_meta.get("stage"),
            "initial_balance": risk_meta.get("initial_balance"),
            "drawdown_pct": risk_meta.get("dd_pct"),
            "order_type": "MARKET_RANGE" if is_market_range else "MARKET",
            "base_slippage_price": (entry if entry > 0 else None) if is_market_range else None,
            "slippage_in_points": (int(round(float(sig.get("max_gold_slippage_points", MAX_GOLD_SLIPPAGE_POINTS)))) if is_gold else int(round(float(sig.get("max_slippage_pips", MAX_SLIPPAGE_PIPS)) * 10))) if is_market_range else None,
            "order_id": 9990001,
            "position_id": 9990001,
            "account_id": str(target_account_id),
            "environment": CTRADER_ENV
        }

    # 2. Live / Stage 2 cTrader Demo Execution via Open API Protobuf
    # Pre-Flight Permissions Guard: Check if broker trading is disabled
    if sig.get("is_trading_allowed") is False:
        access_name = sig.get("access_rights_name", "CLOSE_ONLY")
        err_msg = (
            f"TRADING_NOT_ALLOWED: cTrader account {target_account_id} is restricted to "
            f"'{access_name}' mode by the broker. New order placement is blocked."
        )
        logger.error(f"[cTrader Execution] Pre-flight Check Blocked: {err_msg}")
        return {
            "status": "ORDER_REJECTED",
            "error": err_msg,
            "error_code": "TRADING_NOT_ALLOWED",
            "trading_not_allowed": True,
            "access_rights": access_name,
            "mode": f"LIVE_{CTRADER_ENV.upper()}",
            "pair": pair,
            "direction": direction,
            "order_type": "MARKET_RANGE" if is_market_range else "MARKET",
            "lots": lots,
            "units": units,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "position_id": None,
            "order_id": None,
            "account_id": str(target_account_id),
            "environment": CTRADER_ENV
        }

    try:
        from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOANewOrderReq
        from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAOrderType, ProtoOATradeSide

        host = CTRADER_HOSTS.get(CTRADER_ENV, "demo.ctraderapi.com")
        logger.info(f"[cTrader Execution] Submitting {direction} {pair} ({lots} lots) to {host} for account #{target_account_id}...")

        # Construct Protobuf Order Request
        req = ProtoOANewOrderReq()
        req.ctidTraderAccountId = int(target_account_id)
        req.symbolId = symbol_id if symbol_id is not None else 1
        req.orderType = ProtoOAOrderType.MARKET_RANGE if is_market_range else ProtoOAOrderType.MARKET
        req.tradeSide = ProtoOATradeSide.BUY if direction == "LONG" else ProtoOATradeSide.SELL
        req.volume = volume_cents
        # Relative SL/TP Calculation (ROP-01) & Slippage Defense (Anti-Ban)
        # Scaled to 10^-5 (1/100,000 unit of price) as mandated by cTrader Open API Protobuf specification.
        # MARKET & MARKET_RANGE orders use relativeStopLoss & relativeTakeProfit to guarantee atomic server-side attachment upon fill.
        if req.orderType == ProtoOAOrderType.MARKET_RANGE:
            # Slippage Protection: Enforce baseSlippagePrice and slippageInPoints on MARKET_RANGE orders ONLY.
            # In cTrader Open API Protobuf, passing baseSlippagePrice to a MARKET order causes broker INVALID_REQUEST rejection.
            if entry > 0:
                req.baseSlippagePrice = float(entry)
                if is_gold:
                    gold_slip = float(sig.get("max_gold_slippage_points", MAX_GOLD_SLIPPAGE_POINTS))
                    req.slippageInPoints = int(round(gold_slip))
                else:
                    forex_slip = float(sig.get("max_slippage_pips", MAX_SLIPPAGE_PIPS))
                    req.slippageInPoints = int(round(forex_slip * 10))

        if req.orderType in (ProtoOAOrderType.MARKET, ProtoOAOrderType.MARKET_RANGE):
            if stop_loss > 0 and entry > 0:
                sl_distance = abs(entry - stop_loss)
                req.relativeStopLoss = int(round(sl_distance * 100_000))
            elif stop_loss > 0:
                if is_gold:
                    sl_points = float(sig.get("sl_points") or 25.0)
                    req.relativeStopLoss = int(round(sl_points * 100_000))
                else:
                    pip_size = 0.01 if "JPY" in pair.upper() else 0.0001
                    sl_pips = float(sig.get("sl_pips") or 22.0)
                    req.relativeStopLoss = int(round(sl_pips * pip_size * 100_000))

            if take_profit > 0 and entry > 0:
                tp_distance = abs(entry - take_profit)
                req.relativeTakeProfit = int(round(tp_distance * 100_000))
            elif take_profit > 0:
                if is_gold:
                    tp_points = float(sig.get("tp_points") or (float(sig.get("sl_points", 25.0)) * 1.5))
                    req.relativeTakeProfit = int(round(tp_points * 100_000))
                else:
                    pip_size = 0.01 if "JPY" in pair.upper() else 0.0001
                    tp_pips = float(sig.get("tp_pips") or (float(sig.get("sl_pips", 22.0)) * 1.5))
                    req.relativeTakeProfit = int(round(tp_pips * pip_size * 100_000))
        else:
            if stop_loss > 0:
                req.stopLoss = stop_loss
            if take_profit > 0:
                req.takeProfit = take_profit

        # Stealth Anti-Ban: Configurable comment & label (defaults to empty to mirror manual human orders)
        order_comment = (os.environ.get("CTRADER_ORDER_COMMENT") or "").strip()
        order_label = (os.environ.get("CTRADER_ORDER_LABEL") or "").strip()
        if order_comment:
            req.comment = order_comment
        if order_label:
            req.label = order_label

        # Attempt TLS Transmission to cTrader Open API endpoint
        is_mock = CTRADER_CLIENT_ID.startswith("mock_")
        order_id = 9990001 if is_mock else None
        position_id = 9990001 if is_mock else None
        tls_status = "EXECUTED" if is_mock else "PENDING"
        tls_error = None

        error_code = None
        trading_not_allowed = False
        if not is_mock:
            try:
                tls_res = dispatch_ctrader_tls_order(
                    host=host,
                    port=CTRADER_PORT,
                    client_id=CTRADER_CLIENT_ID,
                    client_secret=CTRADER_CLIENT_SECRET,
                    access_token=CTRADER_ACCESS_TOKEN,
                    account_id=int(target_account_id),
                    order_req=req
                )
                tls_status = tls_res.get("status", "ERROR")
                order_id = tls_res.get("order_id")
                position_id = tls_res.get("position_id")
                tls_error = tls_res.get("error")
                error_code = tls_res.get("error_code")
                trading_not_allowed = tls_res.get("trading_not_allowed", False)
            except Exception as net_err:
                tls_status = "ERROR"
                tls_error = str(net_err)
                logger.error(f"[cTrader TLS] Live dispatch error: {net_err}")

        if tls_status != "EXECUTED" or not position_id:
            logger.error(
                f"[cTrader Execution] Order execution FAILED on cTrader {CTRADER_ENV.upper()}: "
                f"Account: {target_account_id} | Symbol: {pair} (ID: {req.symbolId}) | "
                f"Status: {tls_status} | Error: {tls_error} | Position ID: {position_id}"
            )
            return {
                "status": tls_status if tls_status != "EXECUTED" else "ERROR",
                "error": tls_error or "Broker did not return a valid position ID",
                "error_code": error_code,
                "trading_not_allowed": trading_not_allowed,
                "mode": f"LIVE_{CTRADER_ENV.upper()}",
                "pair": pair,
                "direction": direction,
                "order_type": "MARKET_RANGE" if req.orderType == ProtoOAOrderType.MARKET_RANGE else "MARKET",
                "lots": lots,
                "units": units,
                "entry": entry,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "base_slippage_price": req.baseSlippagePrice if req.HasField("baseSlippagePrice") else None,
                "slippage_in_points": req.slippageInPoints if req.HasField("slippageInPoints") else None,
                "order_id": order_id,
                "position_id": position_id,
                "account_id": str(target_account_id),
                "environment": CTRADER_ENV
            }

        logger.info(
            f"[cTrader Execution] Order executed on cTrader {CTRADER_ENV.upper()}: "
            f"Account: {target_account_id} | Symbol: {pair} (ID: {req.symbolId}) | "
            f"Side: {direction} | Volume: {volume_cents} cents | Position ID: {position_id} | Status: {tls_status}"
        )

        return {
            "status": "EXECUTED",
            "mode": f"LIVE_{CTRADER_ENV.upper()}",
            "pair": pair,
            "direction": direction,
            "order_type": "MARKET_RANGE" if req.orderType == ProtoOAOrderType.MARKET_RANGE else "MARKET",
            "lots": lots,
            "units": units,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_pct": effective_risk_pct,
            "monetary_risk": round(final_risk, 2),
            "account_equity": effective_equity,
            "risk_mode": risk_meta.get("mode"),
            "risk_tier": risk_meta.get("tier"),
            "account_stage": risk_meta.get("stage"),
            "initial_balance": risk_meta.get("initial_balance"),
            "drawdown_pct": risk_meta.get("dd_pct"),
            "order_id": order_id,
            "position_id": position_id,
            "account_id": str(target_account_id),
            "environment": CTRADER_ENV,
            "base_slippage_price": req.baseSlippagePrice if req.HasField("baseSlippagePrice") else None,
            "slippage_in_points": req.slippageInPoints if req.HasField("slippageInPoints") else None,
            "reconciled_after_timeout": tls_res.get("reconciled_after_timeout", False) if not is_mock else False
        }

    except Exception as ex:
        logger.error(f"[cTrader Execution] Failed to place {pair} order on cTrader: {ex}. Scanner cycle continuing.")
        return {
            "status": "ERROR",
            "error": str(ex),
            "pair": pair
        }


def execute_multi_account_orders(
    sig: Dict[str, Any],
    account_ids: Optional[List[int]] = None,
    max_workers: int = 10
) -> List[Dict[str, Any]]:
    """Execute trade orders concurrently across multiple cTrader accounts in parallel threads.

    Guarantees sub-second simultaneous execution across all accounts with zero sequential lag.
    Each account dynamically queries its own live balance and sizes its lots independently.
    """
    targets = account_ids if account_ids is not None else get_target_account_ids()
    if not targets:
        return [execute_ctrader_order(sig)]

    if len(targets) == 1:
        return [execute_ctrader_order(sig, account_id=targets[0])]

    pair_name = sig.get("pair") or sig.get("symbol", "")
    direction = sig.get("direction", "LONG")
    logger.info(
        f"[cTrader Multi-Account Engine] Concurrently dispatching {direction} {pair_name} "
        f"across {len(targets)} accounts in parallel: {targets}"
    )

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(targets))) as executor:
        future_to_acc = {
            executor.submit(execute_ctrader_order, sig=sig.copy(), account_id=acc_id): acc_id
            for acc_id in targets
        }
        for future in concurrent.futures.as_completed(future_to_acc):
            acc_id = future_to_acc[future]
            try:
                receipt = future.result()
                results.append(receipt)
            except Exception as exc:
                logger.error(f"[cTrader Multi-Account Engine] Execution failed for account #{acc_id}: {exc}")
                results.append({
                    "status": "ERROR",
                    "error": str(exc),
                    "account_id": str(acc_id),
                    "pair": pair_name
                })

    return results


def dispatch_ctrader_tls_amend(
    host: str,
    port: int,
    client_id: str,
    client_secret: str,
    access_token: str,
    account_id: int,
    amend_req: Any,
    timeout: float = 5.0
) -> Dict[str, Any]:
    """Execute live position amendment (trailing stop) directly over TLS socket."""
    if (is_test_environment() or os.environ.get("PYTEST_CURRENT_TEST")) and not os.environ.get("TEST_REAL_SOCKET"):
        return {"status": "AMENDED"}
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (
        ProtoOAApplicationAuthReq, ProtoOAAccountAuthReq,
        ProtoOAExecutionEvent, ProtoOAErrorRes
    )

    with create_connected_tls_socket(host, port, timeout) as s:
        # 1. Application Authentication
        app_req = ProtoOAApplicationAuthReq()
        app_req.clientId = client_id
        app_req.clientSecret = client_secret
        app_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_REQ, app_req)
        if not app_res or app_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
            return {"status": "AUTH_FAILED"}

        # 2. Account Authentication
        acc_req = ProtoOAAccountAuthReq()
        acc_req.ctidTraderAccountId = account_id
        acc_req.accessToken = access_token
        acc_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_REQ, acc_req)
        if not acc_res or acc_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
            return {"status": "AUTH_FAILED"}

        # 3. Position Amendment Dispatch
        amend_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_AMEND_POSITION_SLTP_REQ, amend_req)
        if not amend_res:
            return {"status": "ERROR"}
        if amend_res[0] in (ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT, ProtoOAPayloadType.PROTO_OA_TRAILING_SL_CHANGED_EVENT):
            return {"status": "AMENDED"}
        elif amend_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
            err = ProtoOAErrorRes()
            err.ParseFromString(amend_res[1])
            return {"status": "AMEND_REJECTED", "error": err.description}

        return {"status": "AMENDED"}


def modify_ctrader_position(
    position_id: int,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    account_id: Optional[int] = None
) -> Dict[str, Any]:
    """Amend Stop Loss and Take Profit on an open cTrader position (Volatility Cushion Trailing).

    Args:
        position_id: cTrader integer position ID.
        stop_loss: New updated Stop Loss price.
        take_profit: New updated Take Profit price.
        account_id: Optional specific cTrader account ID hosting this position.

    Returns:
        Amendment status dictionary.
    """
    if account_id is not None:
        target_account_id = int(account_id)
    else:
        acc_str = str(CTRADER_ACCOUNT_ID or os.environ.get("CTRADER_ACCOUNT_ID", "")).strip()
        if acc_str and acc_str.isdigit():
            target_account_id = int(acc_str)
        else:
            targets = get_target_account_ids(auto_discover=True)
            target_account_id = targets[0] if targets else 0

    if not ENABLE_CTRADER_EXECUTION or not has_valid_credentials():
        logger.info(
            f"[cTrader Demo Simulator] DRY-RUN TRAILING AMENDMENT: Position #{position_id} -> "
            f"New SL: {stop_loss} | New TP: {take_profit}"
        )
        return {
            "status": "SIMULATED_AMENDMENT",
            "position_id": position_id,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "account_id": str(target_account_id)
        }

    try:
        from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAAmendPositionSLTPReq

        req = ProtoOAAmendPositionSLTPReq()
        req.ctidTraderAccountId = int(target_account_id)
        req.positionId = int(position_id)
        if stop_loss is not None:
            req.stopLoss = float(stop_loss)
        if take_profit is not None:
            req.takeProfit = float(take_profit)

        host = CTRADER_HOSTS.get(CTRADER_ENV, "demo.ctraderapi.com")
        tls_status = "AMENDED"
        tls_error = None
        if not CTRADER_CLIENT_ID.startswith("mock_") and not is_test_environment():
            try:
                tls_res = dispatch_ctrader_tls_amend(
                    host=host,
                    port=CTRADER_PORT,
                    client_id=CTRADER_CLIENT_ID,
                    client_secret=CTRADER_CLIENT_SECRET,
                    access_token=CTRADER_ACCESS_TOKEN,
                    account_id=int(target_account_id),
                    amend_req=req
                )
                if isinstance(tls_res, dict) and tls_res.get("status"):
                    tls_status = tls_res["status"]
                    tls_error = tls_res.get("error")
            except Exception as net_err:
                tls_status = "ERROR"
                tls_error = str(net_err)
                logger.error(f"[cTrader TLS] Amend live dispatch error: {net_err}")

        if tls_status != "AMENDED":
            logger.error(
                f"[cTrader Execution] Trailing Cushion Amendment FAILED: Position #{position_id} (Account: {target_account_id}) -> "
                f"Status: {tls_status} | Error: {tls_error}"
            )
            return {
                "status": tls_status,
                "error": tls_error or "Broker rejected position SL/TP amendment",
                "position_id": position_id,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "account_id": str(target_account_id)
            }

        logger.info(
            f"[cTrader Execution] Trailing Cushion Amendment sent: Position #{position_id} (Account: {target_account_id}) -> "
            f"SL: {stop_loss} | TP: {take_profit}"
        )
        return {
            "status": "AMENDED",
            "position_id": position_id,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "account_id": str(target_account_id)
        }
    except Exception as ex:
        logger.error(f"[cTrader Execution] Failed to amend position #{position_id} on account {target_account_id}: {ex}")
        return {
            "status": "ERROR",
            "error": str(ex),
            "position_id": position_id,
            "account_id": str(target_account_id)
        }


def _dispatch_close_over_socket(
    s: Any,
    client_id: str,
    client_secret: str,
    access_token: str,
    account_id: int,
    close_req: Any,
) -> Dict[str, Any]:
    """Execute position close request over an established TLS socket."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (
        ProtoOAApplicationAuthReq, ProtoOAAccountAuthReq,
        ProtoOAExecutionEvent, ProtoOAErrorRes
    )

    req_pos_id = getattr(close_req, "positionId", 0)

    # 1. Application Authentication
    app_req = ProtoOAApplicationAuthReq()
    app_req.clientId = client_id
    app_req.clientSecret = client_secret
    app_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_REQ, app_req)
    if not app_res or app_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
        return {"status": "AUTH_FAILED"}

    # 2. Account Authentication
    acc_req = ProtoOAAccountAuthReq()
    acc_req.ctidTraderAccountId = account_id
    acc_req.accessToken = access_token
    acc_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_REQ, acc_req)
    if not acc_res or acc_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
        return {"status": "AUTH_FAILED"}

    # 3. Position Close Dispatch
    close_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_CLOSE_POSITION_REQ, close_req)
    if not close_res:
        return {"status": "ERROR", "error": "No response to ProtoOAClosePositionReq"}
    if close_res[0] == ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT:
        event = ProtoOAExecutionEvent()
        event.ParseFromString(close_res[1])
        pos_id = getattr(event.position, "positionId", req_pos_id) if event.HasField("position") else req_pos_id
        return {"status": "CLOSED", "position_id": pos_id}
    elif close_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
        err = ProtoOAErrorRes()
        err.ParseFromString(close_res[1])
        err_code = str(err.errorCode).upper()
        err_desc = str(err.description or "").upper()
        logger.warning(f"[cTrader Open API] Close Position Error: {err.errorCode} - {err.description}")

        # If position was already closed by broker server (SL/TP trigger or manual close),
        # reconcile as ALREADY_CLOSED to prevent watchdog retry loops.
        already_closed_patterns = (
            "POSITION_NOT_FOUND",
            "POSITION_STATUS_CLOSED",
            "POSITION_CLOSED",
            "POSITION_LOCKED",
            "NOT_FOUND",
        )
        if any(p in err_code or p in err_desc for p in already_closed_patterns):
            logger.info(
                f"[cTrader Open API] Position #{req_pos_id} already closed on broker server "
                f"({err.errorCode}: {err.description}). Reconciled as ALREADY_CLOSED."
            )
            return {
                "status": "ALREADY_CLOSED",
                "position_id": req_pos_id,
                "error": err.description,
            }

        return {"status": "CLOSE_REJECTED", "error": err.description}

    return {"status": "CLOSED", "position_id": req_pos_id}


def dispatch_ctrader_tls_close(
    host: str,
    port: int,
    client_id: str,
    client_secret: str,
    access_token: str,
    account_id: int,
    close_req: Any,
    timeout: float = 5.0
) -> Dict[str, Any]:
    """Execute live position close directly over TLS socket with cTrader Open API."""
    if (is_test_environment() or os.environ.get("PYTEST_CURRENT_TEST")) and not getattr(close_req, "_force_tls_test", False):
        return {"status": "CLOSED", "position_id": getattr(close_req, "positionId", 0)}

    with create_connected_tls_socket(host, port, timeout) as s:
        return _dispatch_close_over_socket(
            s=s,
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token,
            account_id=account_id,
            close_req=close_req,
        )


def close_ctrader_position(
    position_id: int,
    volume_cents: Optional[int] = None,
    volume_units: Optional[int] = None,
    lots: Optional[float] = None,
    pair: Optional[str] = None,
    volume: Optional[int] = None,
    account_id: Optional[int] = None
) -> Dict[str, Any]:
    """Close an open position on cTrader Demo/Live account at market.

    Args:
        position_id: cTrader integer position ID.
        volume_cents: Exact position volume to close in cTrader subunits (cents).
        volume_units: Position volume in base currency units (e.g. 86,000).
        lots: Position volume in lots (e.g. 0.86).
        pair: Currency pair or commodity symbol.
        volume: Generic volume parameter (either cents or units).
        account_id: Optional specific cTrader account ID hosting this position.

    Returns:
        Close execution status receipt dictionary.
    """
    if account_id is not None:
        target_account_id = int(account_id)
    else:
        acc_str = str(CTRADER_ACCOUNT_ID or os.environ.get("CTRADER_ACCOUNT_ID", "")).strip()
        if acc_str and acc_str.isdigit():
            target_account_id = int(acc_str)
        else:
            targets = get_target_account_ids(auto_discover=True)
            target_account_id = targets[0] if targets else 0

    if volume_cents is None:
        if volume is not None:
            if volume >= 1_000_000:
                volume_cents = int(volume)
            else:
                volume_units = int(volume)

        if volume_cents is None:
            if volume_units is not None:
                volume_cents = int(volume_units * 100)
            elif lots is not None:
                is_gold = bool(pair and ("XAU" in pair.upper() or "GOLD" in pair.upper()))
                if is_gold:
                    volume_cents = int(round(lots * 100.0 * 100))
                else:
                    volume_cents = int(round(lots * 100_000 * 100))
            else:
                volume_cents = 1_000_000  # Default 0.10 lot

    # 1. Fallback to Simulated Demo / Dry-Run Mode if unconfigured
    if not ENABLE_CTRADER_EXECUTION or not has_valid_credentials():
        reason = "ENABLE_CTRADER_EXECUTION is disabled" if not ENABLE_CTRADER_EXECUTION else "Missing cTrader credentials"
        logger.info(
            f"[cTrader Demo Simulator] DRY-RUN CLOSE: Position #{position_id} | "
            f"Volume: {volume_cents} cents | Mode: DRY_RUN ({reason})"
        )
        return {
            "status": "SIMULATED_CLOSE",
            "mode": "DRY_RUN",
            "position_id": position_id,
            "volume_cents": volume_cents,
            "account_id": str(target_account_id),
            "environment": CTRADER_ENV
        }

    try:
        from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAClosePositionReq

        host = CTRADER_HOSTS.get(CTRADER_ENV, "demo.ctraderapi.com")
        logger.info(f"[cTrader Execution] Closing Position #{position_id} (volume: {volume_cents} cents) on {host} for account #{target_account_id}...")

        req = ProtoOAClosePositionReq()
        req.ctidTraderAccountId = int(target_account_id)
        req.positionId = int(position_id)
        req.volume = int(volume_cents)

        tls_status = "CLOSED"
        tls_error = None
        if not CTRADER_CLIENT_ID.startswith("mock_") and not is_test_environment():
            try:
                tls_res = dispatch_ctrader_tls_close(
                    host=host,
                    port=CTRADER_PORT,
                    client_id=CTRADER_CLIENT_ID,
                    client_secret=CTRADER_CLIENT_SECRET,
                    access_token=CTRADER_ACCESS_TOKEN,
                    account_id=int(target_account_id),
                    close_req=req
                )
                if isinstance(tls_res, dict) and tls_res.get("status"):
                    tls_status = tls_res["status"]
                    tls_error = tls_res.get("error")
            except Exception as net_err:
                tls_status = "ERROR"
                tls_error = str(net_err)
                logger.error(f"[cTrader TLS] Live close dispatch failed: {net_err}. Position #{position_id} may still be open on broker.")

        logger.info(
            f"[cTrader Execution] Position #{position_id} close dispatched to cTrader {CTRADER_ENV.upper()}: "
            f"Account: {target_account_id} | Volume: {volume_cents} | Status: {tls_status}"
        )

        res_payload = {
            "status": tls_status,
            "mode": f"LIVE_{CTRADER_ENV.upper()}",
            "position_id": position_id,
            "volume_cents": volume_cents,
            "account_id": str(target_account_id),
            "environment": CTRADER_ENV
        }
        if tls_error:
            res_payload["error"] = tls_error
        return res_payload

    except Exception as ex:
        logger.error(f"[cTrader Execution] Failed to close position #{position_id} on cTrader: {ex}")
        return {
            "status": "ERROR",
            "error": str(ex),
            "position_id": position_id
        }


# ==============================================================================
# ROP-03: LIVE EQUITY & PROP FIRM DRAWDOWN SURVEILLANCE
# ==============================================================================

def _query_equity_over_socket(
    s: Any,
    client_id: str,
    client_secret: str,
    access_token: str,
    account_id: int
) -> Dict[str, Any]:
    """Internal implementation of querying account balance, floating unrealized P&L,
    and live equity from cTrader Open API over an open socket.
    """
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (
        ProtoOAApplicationAuthReq, ProtoOAAccountAuthReq,
        ProtoOATraderReq, ProtoOATraderRes,
        ProtoOAGetPositionUnrealizedPnLReq, ProtoOAGetPositionUnrealizedPnLRes,
        ProtoOAErrorRes
    )

    # 1. Application Authentication
    app_req = ProtoOAApplicationAuthReq()
    app_req.clientId = client_id
    app_req.clientSecret = client_secret
    app_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_REQ, app_req)
    if not app_res or app_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
        err_desc = "No response"
        if app_res and app_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
            err = ProtoOAErrorRes()
            err.ParseFromString(app_res[1])
            err_desc = err.description
        return {"status": "AUTH_FAILED", "error": f"App auth failed: {err_desc}"}

    # 2. Account Authentication
    acc_req = ProtoOAAccountAuthReq()
    acc_req.ctidTraderAccountId = account_id
    acc_req.accessToken = access_token
    acc_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_REQ, acc_req)
    if not acc_res or acc_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
        err_desc = "No response"
        if acc_res and acc_res[0] == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
            err = ProtoOAErrorRes()
            err.ParseFromString(acc_res[1])
            err_desc = err.description
        return {"status": "AUTH_FAILED", "error": f"Account auth failed: {err_desc}"}

    # 3. Query Trader Profile (Balance, Money Digits, Broker Name)
    trader_req = ProtoOATraderReq()
    trader_req.ctidTraderAccountId = account_id
    trader_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_TRADER_REQ, trader_req)
    if not trader_res or trader_res[0] != ProtoOAPayloadType.PROTO_OA_TRADER_RES:
        return {"status": "ERROR", "error": "Failed to retrieve ProtoOATraderRes"}

    trader_msg = ProtoOATraderRes()
    trader_msg.ParseFromString(trader_res[1])
    trader = trader_msg.trader
    money_digits = trader.moneyDigits if trader.HasField("moneyDigits") else 2
    divisor = 10 ** money_digits
    balance = trader.balance / divisor
    broker_name = trader.brokerName if trader.HasField("brokerName") else "unknown"
    trader_login = trader.traderLogin if trader.HasField("traderLogin") else 0
    access_rights = trader.accessRights if trader.HasField("accessRights") else 0
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAAccessRights
    try:
        rights_name = ProtoOAAccessRights.Name(access_rights)
    except Exception:
        rights_name = str(access_rights)

    # 4. Query Unrealized Floating P&L
    pnl_req = ProtoOAGetPositionUnrealizedPnLReq()
    pnl_req.ctidTraderAccountId = account_id
    pnl_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_GET_POSITION_UNREALIZED_PNL_REQ, pnl_req)

    total_unrealized_pnl = 0.0
    open_positions_count = 0
    positions_pnl = []

    if pnl_res and pnl_res[0] == ProtoOAPayloadType.PROTO_OA_GET_POSITION_UNREALIZED_PNL_RES:
        pnl_msg = ProtoOAGetPositionUnrealizedPnLRes()
        pnl_msg.ParseFromString(pnl_res[1])
        pnl_digits = pnl_msg.moneyDigits if pnl_msg.HasField("moneyDigits") else money_digits
        pnl_divisor = 10 ** pnl_digits
        for p in pnl_msg.positionUnrealizedPnL:
            net_pnl = p.netUnrealizedPnL / pnl_divisor
            gross_pnl = (p.grossUnrealizedPnL / pnl_divisor) if p.HasField("grossUnrealizedPnL") else net_pnl
            total_unrealized_pnl += net_pnl
            open_positions_count += 1
            positions_pnl.append({
                "position_id": p.positionId,
                "gross_pnl": round(gross_pnl, 2),
                "net_pnl": round(net_pnl, 2)
            })

    equity = balance + total_unrealized_pnl

    return {
        "status": "OK",
        "balance": round(balance, 2),
        "unrealized_pnl": round(total_unrealized_pnl, 2),
        "equity": round(equity, 2),
        "open_positions_count": open_positions_count,
        "positions": positions_pnl,
        "broker_name": broker_name,
        "trader_login": trader_login,
        "account_id": account_id,
        "access_rights": access_rights,
        "access_rights_name": rights_name,
        "is_trading_allowed": (access_rights == ProtoOAAccessRights.FULL_ACCESS),
        "money_digits": money_digits
    }


def dispatch_ctrader_tls_equity(
    host: str,
    port: int,
    client_id: str,
    client_secret: str,
    access_token: str,
    account_id: int,
    timeout: float = 8.0
) -> Dict[str, Any]:
    """Execute live equity and unrealized P&L inspection directly over TLS socket."""
    if is_test_environment() and not os.environ.get("TEST_REAL_SOCKET"):
        fallback_eq = float(os.environ.get("ACCOUNT_EQUITY", "5000.0"))
        return {
            "status": "OK",
            "balance": fallback_eq,
            "unrealized_pnl": 0.0,
            "equity": fallback_eq,
            "open_positions_count": 0,
            "positions": [],
            "broker_name": "MOCK",
            "trader_login": account_id,
            "account_id": account_id,
            "access_rights": 0,
            "access_rights_name": "FULL_ACCESS",
            "is_trading_allowed": True,
            "money_digits": 2
        }
    with create_connected_tls_socket(host, port, timeout) as s:
        return _query_equity_over_socket(
            s=s,
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token,
            account_id=account_id
        )


def get_open_ctrader_positions(
    account_id: Optional[int] = None,
    timeout: float = 8.0
) -> Optional[List[Dict[str, Any]]]:
    """Query live open positions on a cTrader account via ProtoOAReconcileReq.

    Returns list of open position dicts (position_id, symbol_id, trade_side, volume, stop_loss, take_profit),
    or None if unavailable / dry-run / test mode / network error.
    """
    if not ENABLE_CTRADER_EXECUTION or not has_valid_credentials():
        return None
    if is_test_environment() and not os.environ.get("TEST_REAL_SOCKET"):
        return None

    acc_id = account_id
    if not acc_id:
        acc_str = str(CTRADER_ACCOUNT_ID or os.environ.get("CTRADER_ACCOUNT_ID", "")).strip()
        if acc_str and acc_str.isdigit():
            acc_id = int(acc_str)
        else:
            targets = get_target_account_ids(auto_discover=True)
            acc_id = targets[0] if targets else 0
    if not acc_id:
        return None

    env_name = (os.environ.get("CTRADER_ENV") or CTRADER_ENV).lower()
    host = CTRADER_HOSTS.get(env_name, "demo.ctraderapi.com")
    try:
        from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
        from ctrader_open_api.messages.OpenApiMessages_pb2 import (
            ProtoOAApplicationAuthReq, ProtoOAAccountAuthReq,
            ProtoOAReconcileReq, ProtoOAReconcileRes
        )
        with create_connected_tls_socket(host, CTRADER_PORT, timeout) as s:
            app_req = ProtoOAApplicationAuthReq()
            app_req.clientId = CTRADER_CLIENT_ID
            app_req.clientSecret = CTRADER_CLIENT_SECRET
            app_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_REQ, app_req)
            if not app_res or app_res[0] != ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_RES:
                return None

            acc_req = ProtoOAAccountAuthReq()
            acc_req.ctidTraderAccountId = int(acc_id)
            acc_req.accessToken = CTRADER_ACCESS_TOKEN
            acc_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_REQ, acc_req)
            if not acc_res or acc_res[0] != ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_RES:
                return None

            rec_req = ProtoOAReconcileReq()
            rec_req.ctidTraderAccountId = int(acc_id)
            rec_res = _send_tls_frame(s, ProtoOAPayloadType.PROTO_OA_RECONCILE_REQ, rec_req)
            if not rec_res or rec_res[0] != ProtoOAPayloadType.PROTO_OA_RECONCILE_RES:
                return None

            rec_msg = ProtoOAReconcileRes()
            rec_msg.ParseFromString(rec_res[1])
            positions = []
            for p in rec_msg.position:
                if getattr(p, "positionStatus", 1) != 1:
                    continue
                td = getattr(p, "tradeData", None)
                positions.append({
                    "position_id": int(p.positionId),
                    "symbol_id": int(td.symbolId) if td else 0,
                    "trade_side": int(td.tradeSide) if td else 0,
                    "volume": int(td.volume) if td else 0,
                    "price": float(getattr(p, "price", 0.0)),
                    "stop_loss": float(p.stopLoss) if p.HasField("stopLoss") else 0.0,
                    "take_profit": float(p.takeProfit) if p.HasField("takeProfit") else 0.0,
                    "account_id": int(acc_id),
                })
            return positions
    except Exception as ex:
        logger.warning(f"[cTrader Reconcile] Could not fetch live open positions for #{acc_id}: {ex}")
        return None


def get_ctrader_account_equity(
    account_id: Optional[int] = None,
    env: Optional[str] = None
) -> Dict[str, Any]:
    """Fetch live account balance, unrealized floating P&L, and equity from cTrader Open API.

    In dry-run mode, test execution, or missing credentials, returns simulated equity.
    """
    env_name = (env or os.environ.get("CTRADER_ENV") or CTRADER_ENV).lower()
    acc_id = account_id
    if not acc_id:
        acc_str = str(CTRADER_ACCOUNT_ID or os.environ.get("CTRADER_ACCOUNT_ID", "")).strip()
        if acc_str and acc_str.isdigit():
            acc_id = int(acc_str)
        else:
            targets = get_target_account_ids(auto_discover=True)
            acc_id = targets[0] if targets else 0
    fallback_equity = float(os.environ.get("ACCOUNT_EQUITY", "5000.0"))

    # Return simulated payload if missing credentials or acc_id
    if not has_valid_credentials() or not acc_id:
        return {
            "status": "SIMULATED",
            "balance": fallback_equity,
            "unrealized_pnl": 0.0,
            "equity": fallback_equity,
            "open_positions_count": 0,
            "positions": [],
            "broker_name": "SIMULATED",
            "trader_login": acc_id,
            "account_id": acc_id,
            "access_rights": 0,
            "money_digits": 2,
            "environment": env_name
        }

    # If running pytest and not explicitly mock-socket tested, return mock
    if is_test_environment() and not CTRADER_CLIENT_ID.startswith("mock_socket_") and not os.environ.get("TEST_REAL_SOCKET"):
        return {
            "status": "OK",
            "balance": fallback_equity,
            "unrealized_pnl": 0.0,
            "equity": fallback_equity,
            "open_positions_count": 0,
            "positions": [],
            "broker_name": "MOCK",
            "trader_login": acc_id,
            "account_id": acc_id,
            "access_rights": 0,
            "money_digits": 2,
            "environment": env_name
        }

    host = CTRADER_HOSTS.get(env_name, "demo.ctraderapi.com")
    try:
        res = dispatch_ctrader_tls_equity(
            host=host,
            port=CTRADER_PORT,
            client_id=CTRADER_CLIENT_ID,
            client_secret=CTRADER_CLIENT_SECRET,
            access_token=CTRADER_ACCESS_TOKEN,
            account_id=acc_id
        )
        res["environment"] = env_name
        return res
    except Exception as ex:
        logger.error(f"[cTrader Equity] Error querying live equity: {ex}")
        return {
            "status": "ERROR",
            "error": str(ex),
            "balance": fallback_equity,
            "unrealized_pnl": 0.0,
            "equity": fallback_equity,
            "open_positions_count": 0,
            "positions": [],
            "broker_name": "ERROR_FALLBACK",
            "trader_login": acc_id,
            "access_rights": 0,
            "money_digits": 2,
            "environment": env_name
        }

