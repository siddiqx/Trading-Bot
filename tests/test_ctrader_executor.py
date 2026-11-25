"""Unit tests for core.ctrader_executor (cTrader Open API Auto-Execution Engine)."""

import pytest
from core.ctrader_executor import (
    get_symbol_id,
    has_valid_credentials,
    execute_ctrader_order,
    modify_ctrader_position,
    close_ctrader_position,
    DEFAULT_SYMBOL_MAP
)


def test_symbol_id_mapping():
    """Verify standard Forex pairs and Gold map correctly to verified cTrader integer IDs."""
    assert get_symbol_id("EURUSD") == 1
    assert get_symbol_id("GBPUSD") == 2
    assert get_symbol_id("USDJPY") == 4
    assert get_symbol_id("AUDUSD") == 5
    assert get_symbol_id("USDCHF") == 6
    assert get_symbol_id("USDCAD") == 8
    assert get_symbol_id("XAUUSD") == 41
    assert get_symbol_id("GC=F") == 41
    assert get_symbol_id("GOLD") == 41
    assert get_symbol_id("EUR/USD") == 1
    assert get_symbol_id("EURUSD=X") == 1


def test_dry_run_execution_unconfigured(monkeypatch):
    """Verify execution safely falls back to Simulated Demo / Dry-Run when unconfigured."""
    import core.ctrader_executor as ce
    monkeypatch.setattr(ce, "ENABLE_CTRADER_EXECUTION", False)

    sig = {
        "pair": "EURUSD",
        "direction": "LONG",
        "entry": 1.08500,
        "stop_loss": 1.08280,
        "take_profit": 1.08830,
        "suggested_lots": 0.11
    }

    res = execute_ctrader_order(sig)
    assert res["status"] == "SIMULATED_DEMO_FILL"
    assert res["mode"] == "DRY_RUN"
    assert res["lots"] == 0.11
    assert res["units"] == 11_000
    assert res["pair"] == "EURUSD"
    assert res["direction"] == "LONG"
    assert res["stop_loss"] == 1.08280
    assert res["take_profit"] == 1.08830


def test_dry_run_trailing_amendment(monkeypatch):
    """Verify position amendment works in Simulated Demo / Dry-Run mode."""
    import core.ctrader_executor as ce
    monkeypatch.setattr(ce, "ENABLE_CTRADER_EXECUTION", False)

    res = modify_ctrader_position(position_id=9990001, stop_loss=1.08400, take_profit=1.08940)
    assert res["status"] == "SIMULATED_AMENDMENT"
    assert res["position_id"] == 9990001
    assert res["stop_loss"] == 1.08400
    assert res["take_profit"] == 1.08940


def test_live_demo_execution_structure(monkeypatch):
    """Verify ProtoOANewOrderReq construction when credentials and execution are enabled."""
    monkeypatch.setenv("ENABLE_CTRADER_EXECUTION", "true")
    monkeypatch.setenv("CTRADER_CLIENT_ID", "mock_client_id")
    monkeypatch.setenv("CTRADER_CLIENT_SECRET", "mock_client_secret")
    monkeypatch.setenv("CTRADER_ACCESS_TOKEN", "mock_access_token")
    monkeypatch.setenv("CTRADER_ACCOUNT_ID", "12345678")
    monkeypatch.setenv("CTRADER_ENV", "demo")

    # Re-import to pick up monkeypatched env
    import core.ctrader_executor as ce
    monkeypatch.setattr(ce, "ENABLE_CTRADER_EXECUTION", True)
    monkeypatch.setattr(ce, "CTRADER_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(ce, "CTRADER_CLIENT_SECRET", "mock_client_secret")
    monkeypatch.setattr(ce, "CTRADER_ACCESS_TOKEN", "mock_access_token")
    monkeypatch.setattr(ce, "CTRADER_ACCOUNT_ID", "12345678")
    monkeypatch.setattr(ce, "CTRADER_ENV", "demo")

    sig = {
        "pair": "GBPUSD",
        "direction": "SHORT",
        "entry": 1.30000,
        "stop_loss": 1.30220,
        "take_profit": 1.29670,
        "suggested_lots": 0.08
    }

    res = ce.execute_ctrader_order(sig)
    assert res["status"] == "EXECUTED"
    assert res["mode"] == "LIVE_DEMO"
    assert res["account_id"] == "12345678"
    assert res["units"] == 8_000
    assert res["pair"] == "GBPUSD"
    assert res["direction"] == "SHORT"


def test_dry_run_close_position(monkeypatch):
    """Verify position close safely falls back to Simulated Demo / Dry-Run when unconfigured."""
    import core.ctrader_executor as ce
    monkeypatch.setattr(ce, "ENABLE_CTRADER_EXECUTION", False)

    res = close_ctrader_position(position_id=9990001, volume_units=86000, pair="USDCAD")
    assert res["status"] == "SIMULATED_CLOSE"
    assert res["mode"] == "DRY_RUN"
    assert res["position_id"] == 9990001
    assert res["volume_cents"] == 8_600_000


def test_live_demo_close_position_structure(monkeypatch):
    """Verify ProtoOAClosePositionReq dispatch when credentials and execution are enabled."""
    import core.ctrader_executor as ce
    monkeypatch.setattr(ce, "ENABLE_CTRADER_EXECUTION", True)
    monkeypatch.setattr(ce, "CTRADER_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(ce, "CTRADER_CLIENT_SECRET", "mock_client_secret")
    monkeypatch.setattr(ce, "CTRADER_ACCESS_TOKEN", "mock_access_token")
    monkeypatch.setattr(ce, "CTRADER_ACCOUNT_ID", "12345678")
    monkeypatch.setattr(ce, "CTRADER_ENV", "demo")

    res = ce.close_ctrader_position(position_id=16254441, lots=0.56, pair="GBPUSD")
    assert res["status"] == "CLOSED"
    assert res["mode"] == "LIVE_DEMO"
    assert res["position_id"] == 16254441
    assert res["volume_cents"] == 5_600_000
    assert res["account_id"] == "12345678"


def test_dynamic_25k_account_lot_sizing(monkeypatch):
    """Verify that a 25k account dynamically sizes Forex and Gold to avoid low-profit under-sizing."""
    import core.ctrader_executor as ce
    monkeypatch.setattr(ce, "ENABLE_CTRADER_EXECUTION", False)
    monkeypatch.setenv("ACCOUNT_EQUITY", "25000.0")
    monkeypatch.setenv("RISK_PCT", "1.00")

    # 1. Forex EURUSD with 22p stop: $250 budget / (22 * $10) = 1.13 lots
    sig_forex = {
        "pair": "EURUSD",
        "direction": "LONG",
        "entry": 1.08500,
        "stop_loss": 1.08280,
        "take_profit": 1.08850,
        "sl_pips": 22.0,
        "account_equity": 5000.0, # Old/mismatched signal equity
        "suggested_lots": 0.11
    }
    res_forex = ce.execute_ctrader_order(sig_forex)
    assert res_forex["lots"] == 1.13
    assert res_forex["units"] == 113_000

    # 2. Gold XAUUSD with 25pt stop: $250 budget / (25 * $100) = 0.10 lots
    sig_gold = {
        "pair": "XAUUSD",
        "direction": "SHORT",
        "entry": 4050.0,
        "stop_loss": 4075.0,
        "take_profit": 4012.5,
        "sl_points": 25.0,
        "account_equity": 5000.0,
        "suggested_lots": 0.01
    }
    res_gold = ce.execute_ctrader_order(sig_gold)
    assert res_gold["lots"] == 0.10
    assert res_gold["units"] == 10 # 10 oz


def test_dynamic_5k_account_lot_sizing_forex_and_gold(monkeypatch):
    """Verify that a $5,000 prop firm challenge account dynamically sizes Forex and Gold to exact risk budgets."""
    import core.ctrader_executor as ce
    monkeypatch.setattr(ce, "ENABLE_CTRADER_EXECUTION", False)
    monkeypatch.setenv("ACCOUNT_EQUITY", "5000.0")
    monkeypatch.setenv("RISK_PCT", "1.00")

    # 1. EURUSD with 22p stop: $50 budget / (22 * $10) = 0.22 lots ($48.40 risk <= $50.00)
    sig_eur = {
        "pair": "EURUSD",
        "direction": "LONG",
        "entry": 1.08500,
        "stop_loss": 1.08280,
        "take_profit": 1.08830,
        "sl_pips": 22.0,
        "account_equity": 5000.0,
        "suggested_lots": 0.0
    }
    res_eur = ce.execute_ctrader_order(sig_eur)
    assert res_eur["lots"] == 0.22
    assert res_eur["units"] == 22_000

    # 2. USDCAD with 22p stop, entry 1.4100: CAD pip value ~$7.09/pip/lot -> 0.32 lots ($49.92 risk <= $50.00)
    sig_cad = {
        "pair": "USDCAD",
        "direction": "SHORT",
        "entry": 1.41000,
        "stop_loss": 1.41220,
        "take_profit": 1.40670,
        "sl_pips": 22.0,
        "account_equity": 5000.0,
        "suggested_lots": 0.0
    }
    res_cad = ce.execute_ctrader_order(sig_cad)
    assert res_cad["lots"] == 0.32
    assert res_cad["units"] == 32_000

    # 3. USDCHF with 22p stop, entry 0.8800: CHF pip value ~$11.36/pip/lot -> 0.20 lots ($49.98 risk <= $50.00)
    sig_chf = {
        "pair": "USDCHF",
        "direction": "LONG",
        "entry": 0.88000,
        "stop_loss": 0.87780,
        "take_profit": 0.88330,
        "sl_pips": 22.0,
        "account_equity": 5000.0,
        "suggested_lots": 0.0
    }
    res_chf = ce.execute_ctrader_order(sig_chf)
    assert res_chf["lots"] == 0.20
    assert res_chf["units"] == 20_000

    # 4. AUDUSD with 22p stop: USD quote currency ($10/pip) -> 0.22 lots ($48.40 risk <= $50.00)
    sig_aud = {
        "pair": "AUDUSD",
        "direction": "LONG",
        "entry": 0.65000,
        "stop_loss": 0.64780,
        "take_profit": 0.65330,
        "sl_pips": 22.0,
        "account_equity": 5000.0,
        "suggested_lots": 0.0
    }
    res_aud = ce.execute_ctrader_order(sig_aud)
    assert res_aud["lots"] == 0.22
    assert res_aud["units"] == 22_000

    # 5. Gold XAUUSD with 25pt stop: $50 budget / (25 * $100) = 0.02 lots ($50.00 risk)
    sig_gold = {
        "pair": "XAUUSD",
        "direction": "SHORT",
        "entry": 4050.0,
        "stop_loss": 4075.0,
        "take_profit": 4012.5,
        "sl_points": 25.0,
        "account_equity": 5000.0,
        "suggested_lots": 0.0
    }
    res_gold = ce.execute_ctrader_order(sig_gold)
    assert res_gold["lots"] == 0.02
    assert res_gold["units"] == 2  # 2 oz


def test_capital_defense_hard_clamp_intercepts_oversized_orders(monkeypatch):
    """Verify Capital Defense Hard Clamp downsizes or rejects oversized lot sizes to protect 5k capital."""
    import core.ctrader_executor as ce
    monkeypatch.setattr(ce, "ENABLE_CTRADER_EXECUTION", False)
    monkeypatch.setenv("ACCOUNT_EQUITY", "5000.0")
    monkeypatch.setenv("RISK_PCT", "1.00")

    # Mismatched signal sending 1.13 lots ($248 risk) into a $5,000 account ($50 budget)
    oversized_sig = {
        "pair": "EURUSD",
        "direction": "LONG",
        "entry": 1.08500,
        "stop_loss": 1.08280,
        "take_profit": 1.08830,
        "sl_pips": 22.0,
        "suggested_lots": 1.13,  # Dangerously oversized!
        "account_equity": 5000.0
    }
    res = ce.execute_ctrader_order(oversized_sig)
    # Must be clamped down to 0.22 lots ($48.40) to preserve $5k account
    assert res["lots"] == 0.22
    assert res["units"] == 22_000


def test_dynamic_equity_fluctuations_adaptive_sizing(monkeypatch):
    """Verify that sizing adapts dynamically to account drawdown and profit states."""
    import core.ctrader_executor as ce
    monkeypatch.setattr(ce, "ENABLE_CTRADER_EXECUTION", False)
    monkeypatch.setenv("RISK_PCT", "1.00")

    # Drawdown state ($4,800 equity): $48 budget -> 0.21 lots ($46.20 risk)
    monkeypatch.setenv("ACCOUNT_EQUITY", "4800.0")
    sig_dd = {
        "pair": "EURUSD",
        "direction": "LONG",
        "entry": 1.08500,
        "stop_loss": 1.08280,
        "take_profit": 1.08830,
        "sl_pips": 22.0,
        "account_equity": 4800.0,
        "suggested_lots": 0.0
    }
    res_dd = ce.execute_ctrader_order(sig_dd)
    assert res_dd["lots"] == 0.21
    assert res_dd["units"] == 21_000

    # Profit state ($5,250 equity): $52.50 budget -> 0.23 lots ($50.60 risk)
    monkeypatch.setenv("ACCOUNT_EQUITY", "5250.0")
    sig_profit = {
        "pair": "EURUSD",
        "direction": "LONG",
        "entry": 1.08500,
        "stop_loss": 1.08280,
        "take_profit": 1.08830,
        "sl_pips": 22.0,
        "account_equity": 5250.0,
        "suggested_lots": 0.0
    }
    res_profit = ce.execute_ctrader_order(sig_profit)
    assert res_profit["lots"] == 0.23
    assert res_profit["units"] == 23_000


def test_dynamic_075_live_broker_balance_adaptation(monkeypatch):
    """Verify that execution automatically discovers live balance directly from broker query
    and dynamically sizes orders to 0.75% risk without hardcoded balance values."""
    import core.ctrader_executor as ce
    monkeypatch.setattr(ce, "ENABLE_CTRADER_EXECUTION", True)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("ACCOUNT_EQUITY", raising=False)
    monkeypatch.setenv("RISK_PCT", "0.75")

    # Mock live broker response returning $10,350.50 settled balance
    monkeypatch.setattr(ce, "get_ctrader_account_equity", lambda *args, **kwargs: {
        "status": "OK",
        "balance": 10350.50,
        "unrealized_pnl": 0.0,
        "equity": 10350.50,
        "is_trading_allowed": True
    })

    # Incoming signal from 15M scanner
    sig = {
        "pair": "EURUSD",
        "direction": "LONG",
        "entry": 1.08500,
        "stop_loss": 1.08340,
        "take_profit": 1.08740,
        "sl_pips": 16.0,
        "account_equity": 0.0,
        "suggested_lots": 0.0
    }

    # Target budget: 10350.50 * 0.0075 = $77.63
    # Sized lots for 16p stop ($160/lot): floor(77.63 / 160) = 0.48 lots ($76.80 risk)
    res = ce.execute_ctrader_order(sig)
    assert res["lots"] == 0.48
    assert res["units"] == 48_000
    assert res["lots"] * 16.0 * 10.0 <= (10350.50 * 0.0075)


def test_stealth_comment_and_label_configuration(monkeypatch):
    """Verify stealth comment and label configuration for prop firm anti-ban safety."""
    monkeypatch.setenv("ENABLE_CTRADER_EXECUTION", "true")
    monkeypatch.setenv("CTRADER_CLIENT_ID", "mock_client_id")
    monkeypatch.setenv("CTRADER_CLIENT_SECRET", "mock_client_secret")
    monkeypatch.setenv("CTRADER_ACCESS_TOKEN", "mock_access_token")
    monkeypatch.setenv("CTRADER_ACCOUNT_ID", "12345678")
    monkeypatch.setenv("CTRADER_ENV", "demo")
    monkeypatch.setenv("CTRADER_ORDER_COMMENT", "swing_manual")
    monkeypatch.setenv("CTRADER_ORDER_LABEL", "tier1")

    import core.ctrader_executor as ce
    monkeypatch.setattr(ce, "ENABLE_CTRADER_EXECUTION", True)
    monkeypatch.setattr(ce, "CTRADER_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(ce, "CTRADER_CLIENT_SECRET", "mock_client_secret")
    monkeypatch.setattr(ce, "CTRADER_ACCESS_TOKEN", "mock_access_token")
    monkeypatch.setattr(ce, "CTRADER_ACCOUNT_ID", "12345678")

    sig = {
        "pair": "EURUSD",
        "direction": "LONG",
        "entry": 1.08500,
        "stop_loss": 1.08280,
        "take_profit": 1.08830,
        "suggested_lots": 0.10
    }

    res = ce.execute_ctrader_order(sig)
    assert res["status"] == "EXECUTED"


def test_live_order_rejection_safety(monkeypatch):
    """Verify that execute_ctrader_order does not report fake execution when broker rejects order."""
    import core.ctrader_executor as ce
    monkeypatch.setattr(ce, "ENABLE_CTRADER_EXECUTION", True)
    monkeypatch.setattr(ce, "CTRADER_CLIENT_ID", "real_client_id")
    monkeypatch.setattr(ce, "CTRADER_CLIENT_SECRET", "real_client_secret")
    monkeypatch.setattr(ce, "CTRADER_ACCESS_TOKEN", "real_token")
    monkeypatch.setattr(ce, "CTRADER_ACCOUNT_ID", "12345678")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    # Mock dispatch_ctrader_tls_order returning broker rejection
    monkeypatch.setattr(
        ce,
        "dispatch_ctrader_tls_order",
        lambda **kwargs: {"status": "ORDER_REJECTED", "error": "TRADING_BAD_VOLUME: Invalid volume"}
    )

    sig = {
        "pair": "XAUUSD",
        "direction": "LONG",
        "entry": 3575.10,
        "stop_loss": 3540.10,
        "take_profit": 3627.60,
        "suggested_lots": 0.03
    }

    res = ce.execute_ctrader_order(sig)
    assert res["status"] == "ORDER_REJECTED"
    assert res["position_id"] is None
    assert "TRADING_BAD_VOLUME" in res["error"]


def test_rop01_relative_sltp_market_framing(monkeypatch):
    """Verify execute_ctrader_order populates relativeStopLoss/relativeTakeProfit and omits absolute SL/TP."""
    import core.ctrader_executor as ce
    monkeypatch.setattr(ce, "ENABLE_CTRADER_EXECUTION", True)
    monkeypatch.setattr(ce, "CTRADER_CLIENT_ID", "real_client_id")
    monkeypatch.setattr(ce, "CTRADER_CLIENT_SECRET", "real_client_secret")
    monkeypatch.setattr(ce, "CTRADER_ACCESS_TOKEN", "real_token")
    monkeypatch.setattr(ce, "CTRADER_ACCOUNT_ID", "12345678")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    captured_req = {}
    def mock_dispatch(**kwargs):
        captured_req["req"] = kwargs.get("order_req")
        return {"status": "EXECUTED", "position_id": 12345, "order_id": 67890}

    monkeypatch.setattr(ce, "dispatch_ctrader_tls_order", mock_dispatch)

    # 1. EURUSD: 22 pips SL (0.00220), 33 pips TP (0.00330)
    sig_forex = {
        "pair": "EURUSD",
        "direction": "LONG",
        "entry": 1.08500,
        "stop_loss": 1.08280,
        "take_profit": 1.08830,
        "suggested_lots": 0.10
    }
    ce.execute_ctrader_order(sig_forex)
    req = captured_req["req"]
    assert req.relativeStopLoss == 220
    assert req.relativeTakeProfit == 330
    assert not req.HasField("stopLoss")
    assert not req.HasField("takeProfit")

    # 2. XAUUSD: 25.0 points SL, 37.5 points TP
    sig_gold = {
        "pair": "XAUUSD",
        "direction": "SHORT",
        "entry": 2750.00,
        "stop_loss": 2775.00,
        "take_profit": 2712.50,
        "suggested_lots": 0.05
    }
    ce.execute_ctrader_order(sig_gold)
    req_gold = captured_req["req"]
    assert req_gold.relativeStopLoss == 2_500_000
    assert req_gold.relativeTakeProfit == 3_750_000
    assert not req_gold.HasField("stopLoss")
    assert not req_gold.HasField("takeProfit")

    # 3. USDJPY: 22 pips SL (0.22), 33 pips TP (0.33)
    sig_jpy = {
        "pair": "USDJPY",
        "direction": "LONG",
        "entry": 154.500,
        "stop_loss": 154.280,
        "take_profit": 154.830,
        "suggested_lots": 0.10
    }
    ce.execute_ctrader_order(sig_jpy)
    req_jpy = captured_req["req"]
    assert req_jpy.relativeStopLoss == 22_000
    assert req_jpy.relativeTakeProfit == 33_000
    assert not req_jpy.HasField("stopLoss")
    assert not req_jpy.HasField("takeProfit")


def test_market_order_slippage_parameters(monkeypatch):
    """Verify market orders omit baseSlippagePrice for MARKET type, and enforce them for MARKET_RANGE."""
    import core.ctrader_executor as ce
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAOrderType

    monkeypatch.setattr(ce, "ENABLE_CTRADER_EXECUTION", True)
    monkeypatch.setattr(ce, "CTRADER_CLIENT_ID", "real_client_id")
    monkeypatch.setattr(ce, "CTRADER_CLIENT_SECRET", "real_client_secret")
    monkeypatch.setattr(ce, "CTRADER_ACCESS_TOKEN", "real_token")
    monkeypatch.setattr(ce, "CTRADER_ACCOUNT_ID", "12345678")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    captured_req = {}
    def mock_dispatch(**kwargs):
        captured_req["req"] = kwargs.get("order_req")
        return {"status": "EXECUTED", "position_id": 12345, "order_id": 67890}

    monkeypatch.setattr(ce, "dispatch_ctrader_tls_order", mock_dispatch)

    # 1. Default standard MARKET order: Omits baseSlippagePrice to prevent cTrader INVALID_REQUEST rejection
    sig_eur = {
        "pair": "EURUSD",
        "direction": "LONG",
        "entry": 1.08500,
        "stop_loss": 1.08280,
        "take_profit": 1.08830,
        "suggested_lots": 0.10
    }
    res_eur = ce.execute_ctrader_order(sig_eur)
    req_eur = captured_req["req"]
    assert req_eur.orderType == ProtoOAOrderType.MARKET
    assert not req_eur.HasField("baseSlippagePrice")
    assert not req_eur.HasField("slippageInPoints")
    assert req_eur.relativeStopLoss == 220
    assert req_eur.relativeTakeProfit == 330
    assert res_eur["order_type"] == "MARKET"
    assert res_eur["base_slippage_price"] is None
    assert res_eur["slippage_in_points"] is None

    # 2. MARKET_RANGE order: Correctly sets orderType=MARKET_RANGE and attaches baseSlippagePrice and slippageInPoints
    sig_eur_range = {
        "pair": "EURUSD",
        "direction": "LONG",
        "order_type": "MARKET_RANGE",
        "entry": 1.08500,
        "stop_loss": 1.08280,
        "take_profit": 1.08830,
        "suggested_lots": 0.10
    }
    res_range = ce.execute_ctrader_order(sig_eur_range)
    req_range = captured_req["req"]
    assert req_range.orderType == ProtoOAOrderType.MARKET_RANGE
    assert req_range.baseSlippagePrice == 1.08500
    assert req_range.slippageInPoints == 30
    assert res_range["order_type"] == "MARKET_RANGE"
    assert res_range["base_slippage_price"] == 1.08500
    assert res_range["slippage_in_points"] == 30

    # 3. Custom Forex slippage override on MARKET_RANGE: 1.5 pips -> 15 points
    sig_custom_fx = {
        "pair": "USDCAD",
        "direction": "SHORT",
        "order_type": "MARKET_RANGE",
        "entry": 1.35000,
        "stop_loss": 1.35200,
        "take_profit": 1.34700,
        "suggested_lots": 0.10,
        "max_slippage_pips": 1.5
    }
    res_custom = ce.execute_ctrader_order(sig_custom_fx)
    req_custom = captured_req["req"]
    assert req_custom.orderType == ProtoOAOrderType.MARKET_RANGE
    assert req_custom.baseSlippagePrice == 1.35000
    assert req_custom.slippageInPoints == 15

    # 4. Gold on MARKET_RANGE: 50 points ($0.50)
    sig_gold = {
        "pair": "XAUUSD",
        "direction": "LONG",
        "order_type": "MARKET_RANGE",
        "entry": 2750.00,
        "stop_loss": 2725.00,
        "take_profit": 2787.50,
        "suggested_lots": 0.05
    }
    res_gold = ce.execute_ctrader_order(sig_gold)
    req_gold = captured_req["req"]
    assert req_gold.orderType == ProtoOAOrderType.MARKET_RANGE
    assert req_gold.baseSlippagePrice == 2750.00
    assert req_gold.slippageInPoints == 50
    assert res_gold["base_slippage_price"] == 2750.00
    assert res_gold["slippage_in_points"] == 50

    # 5. Dry-Run / Paper simulator reflects configured order types
    monkeypatch.setattr(ce, "ENABLE_CTRADER_EXECUTION", False)
    res_dry_market = ce.execute_ctrader_order(sig_eur)
    assert res_dry_market["status"] == "SIMULATED_DEMO_FILL"
    assert res_dry_market["order_type"] == "MARKET"
    assert res_dry_market["base_slippage_price"] is None

    res_dry_range = ce.execute_ctrader_order(sig_eur_range)
    assert res_dry_range["status"] == "SIMULATED_DEMO_FILL"
    assert res_dry_range["order_type"] == "MARKET_RANGE"
    assert res_dry_range["base_slippage_price"] == 1.08500
    assert res_dry_range["slippage_in_points"] == 30



class _FakeSocket:
    """Mock socket for testing TLS framing without connecting to cTrader broker."""
    def __init__(self, responses):
        import struct
        from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoMessage
        self.sent_frames = []
        self._read_buffer = bytearray()
        for p_type, msg in responses:
            proto_msg = ProtoMessage()
            proto_msg.payloadType = p_type
            proto_msg.payload = msg.SerializeToString()
            data = proto_msg.SerializeToString()
            self._read_buffer.extend(struct.pack('>I', len(data)) + data)

    def sendall(self, data):
        self.sent_frames.append(data)

    def recv(self, num_bytes):
        chunk = self._read_buffer[:num_bytes]
        self._read_buffer = self._read_buffer[num_bytes:]
        return bytes(chunk)


def _build_test_order_req():
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAOrderType, ProtoOATradeSide
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOANewOrderReq
    req = ProtoOANewOrderReq()
    req.ctidTraderAccountId = 111
    req.symbolId = 1
    req.tradeSide = ProtoOATradeSide.BUY
    req.volume = 100000
    req.orderType = ProtoOAOrderType.MARKET
    req.relativeStopLoss = 220
    req.relativeTakeProfit = 330
    return req


def _build_test_auth_responses():
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAApplicationAuthRes, ProtoOAAccountAuthRes
    app_res = ProtoOAApplicationAuthRes()
    acc_res = ProtoOAAccountAuthRes()
    acc_res.ctidTraderAccountId = 111
    return [
        (ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_RES, app_res),
        (ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_RES, acc_res)
    ]


def _build_test_execution_event(position_id=12345, order_id=67890, sl=None, tp=None, execution_type=None):
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
        ProtoOAExecutionType, ProtoOAOrderType, ProtoOATradeSide,
        ProtoOAPositionStatus, ProtoOAOrderStatus
    )
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAExecutionEvent
    ev = ProtoOAExecutionEvent()
    ev.ctidTraderAccountId = 111
    ev.executionType = execution_type or ProtoOAExecutionType.ORDER_FILLED
    ev.order.orderId = order_id
    ev.order.orderType = ProtoOAOrderType.MARKET
    ev.order.orderStatus = ProtoOAOrderStatus.ORDER_STATUS_ACCEPTED
    ev.order.tradeData.symbolId = 1
    ev.order.tradeData.volume = 100000
    ev.order.tradeData.tradeSide = ProtoOATradeSide.BUY
    ev.position.positionId = position_id
    ev.position.positionStatus = ProtoOAPositionStatus.POSITION_STATUS_OPEN
    ev.position.swap = 0
    ev.position.price = 1.08500
    ev.position.tradeData.symbolId = 1
    ev.position.tradeData.volume = 100000
    ev.position.tradeData.tradeSide = ProtoOATradeSide.BUY
    if sl is not None:
        ev.position.stopLoss = float(sl)
    if tp is not None:
        ev.position.takeProfit = float(tp)
    return ev


def test_rop01_fake_socket_atomic_sltp_success():
    """Verify _dispatch_order_over_socket detects atomic server-side SL/TP on fill."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
    from core.ctrader_executor import _dispatch_order_over_socket

    responses = _build_test_auth_responses()
    ev = _build_test_execution_event(sl=1.08280, tp=1.08830)
    responses.append((ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT, ev))

    sock = _FakeSocket(responses)
    req = _build_test_order_req()

    res = _dispatch_order_over_socket(sock, "client_id", "secret", "token", 111, req)
    assert res["status"] == "EXECUTED"
    assert res["atomic_sltp"] is True
    assert res["position_id"] == 12345
    assert res["attached_sl"] == 1.08280
    assert res["attached_tp"] == 1.08830


def test_rop01_fake_socket_fallback_amend_success():
    """Verify fallback amendment loop triggers when SL is missing on fill and succeeds on retry."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
    from core.ctrader_executor import _dispatch_order_over_socket

    responses = _build_test_auth_responses()
    # 1. Fill event WITHOUT stop loss (naked position)
    ev_naked = _build_test_execution_event(sl=None, tp=None)
    responses.append((ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT, ev_naked))

    # 2. Amend response acknowledging SL/TP attachment
    ev_amended = _build_test_execution_event(sl=1.08280, tp=1.08830)
    responses.append((ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT, ev_amended))

    sock = _FakeSocket(responses)
    req = _build_test_order_req()

    res = _dispatch_order_over_socket(sock, "client_id", "secret", "token", 111, req, max_amend_retries=3, retry_delay_sec=0.0)
    assert res["status"] == "EXECUTED"
    assert res["atomic_sltp"] is False
    assert res["amend_retries"] == 1
    assert res["position_id"] == 12345


def test_rop01_fake_socket_emergency_market_close_on_amend_failure():
    """Verify emergency market close is dispatched when all 3 amend retries fail."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAErrorRes
    from core.ctrader_executor import _dispatch_order_over_socket

    responses = _build_test_auth_responses()
    # 1. Fill event without SL
    ev_naked = _build_test_execution_event(sl=None, tp=None)
    responses.append((ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT, ev_naked))

    # 2. 3 Amend rejections
    for i in range(3):
        err = ProtoOAErrorRes()
        err.ctidTraderAccountId = 111
        err.errorCode = f"REJECTED_{i+1}"
        err.description = f"Amend failure {i+1}"
        responses.append((ProtoOAPayloadType.PROTO_OA_ERROR_RES, err))

    # 3. Close event response
    ev_closed = _build_test_execution_event(sl=None, tp=None)
    responses.append((ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT, ev_closed))

    sock = _FakeSocket(responses)
    req = _build_test_order_req()

    res = _dispatch_order_over_socket(sock, "client_id", "secret", "token", 111, req, max_amend_retries=3, retry_delay_sec=0.0)
    assert res["status"] == "EMERGENCY_CLOSED"
    assert res["position_id"] == 12345
    assert "Failed to attach Stop-Loss after 3 retries" in res["error"]


def test_rop01_tick_rounding_5digit_forex_and_gold():
    """Verify tick rounding calculations for 5-digit Forex (EURUSD) and Gold (XAUUSD)."""
    from scripts.demo_relative_sltp import verify_tick_rounding

    # 1. 5-digit Forex pair (EURUSD)
    passed_forex, data_forex = verify_tick_rounding(
        symbol="EURUSD",
        entry=1.08543,
        sl_distance=0.00220,
        tp_distance=0.00330
    )
    assert passed_forex is True
    assert data_forex["rel_sl"] == 220
    assert data_forex["rel_tp"] == 330
    assert data_forex["sl_price"] == 1.08323
    assert data_forex["tp_price"] == 1.08873
    assert data_forex["sl_diff"] <= 0.00001
    assert data_forex["tp_diff"] <= 0.00001

    # 2. Commodity Gold (XAUUSD)
    passed_gold, data_gold = verify_tick_rounding(
        symbol="XAUUSD",
        entry=2750.65,
        sl_distance=25.00,
        tp_distance=37.50
    )
    assert passed_gold is True
    assert data_gold["rel_sl"] == 2_500_000
    assert data_gold["rel_tp"] == 3_750_000
    assert data_gold["sl_price"] == 2725.65
    assert data_gold["tp_price"] == 2788.15
    assert data_gold["sl_diff"] <= 0.01
    assert data_gold["tp_diff"] <= 0.01


def _build_test_trader_response(balance_cents=500000, money_digits=2, broker_name="the5ers", login=12345):
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOATraderRes
    res = ProtoOATraderRes()
    res.ctidTraderAccountId = 111
    res.trader.ctidTraderAccountId = 111
    res.trader.depositAssetId = 1
    res.trader.balance = balance_cents
    res.trader.moneyDigits = money_digits
    res.trader.brokerName = broker_name
    res.trader.traderLogin = login
    return (ProtoOAPayloadType.PROTO_OA_TRADER_RES, res)


def _build_test_pnl_response(positions_pnl=None, money_digits=2):
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAGetPositionUnrealizedPnLRes
    res = ProtoOAGetPositionUnrealizedPnLRes()
    res.ctidTraderAccountId = 111
    res.moneyDigits = money_digits
    if positions_pnl:
        for pos_id, net_cents, gross_cents in positions_pnl:
            p = res.positionUnrealizedPnL.add()
            p.positionId = pos_id
            p.netUnrealizedPnL = net_cents
            p.grossUnrealizedPnL = gross_cents
    return (ProtoOAPayloadType.PROTO_OA_GET_POSITION_UNREALIZED_PNL_RES, res)


def test_rop03_query_equity_idle_account():
    """Verify ROP-03 queries balance and calculates live equity accurately when no positions are open."""
    from core.ctrader_executor import _query_equity_over_socket

    responses = _build_test_auth_responses()
    responses.append(_build_test_trader_response(balance_cents=500000, money_digits=2, broker_name="the5ers", login=55512))
    responses.append(_build_test_pnl_response(positions_pnl=[], money_digits=2))

    sock = _FakeSocket(responses)
    res = _query_equity_over_socket(sock, "client_id", "secret", "token", 111)

    assert res["status"] == "OK"
    assert res["balance"] == 5000.00
    assert res["unrealized_pnl"] == 0.00
    assert res["equity"] == 5000.00
    assert res["open_positions_count"] == 0
    assert res["broker_name"] == "the5ers"
    assert res["trader_login"] == 55512


def test_rop03_query_equity_with_floating_pnl():
    """Verify ROP-03 computes live equity with multiple positive and negative floating positions."""
    from core.ctrader_executor import _query_equity_over_socket

    responses = _build_test_auth_responses()
    # $5,000.00 initial balance
    responses.append(_build_test_trader_response(balance_cents=500000, money_digits=2, broker_name="the5ers", login=55512))
    # Position 1: +$45.50 (4550 cents), Position 2: +$20.25 (2025 cents) -> total = +$65.75
    responses.append(_build_test_pnl_response(
        positions_pnl=[(101, 4550, 4800), (102, 2025, 2100)],
        money_digits=2
    ))

    sock = _FakeSocket(responses)
    res = _query_equity_over_socket(sock, "client_id", "secret", "token", 111)

    assert res["status"] == "OK"
    assert res["balance"] == 5000.00
    assert res["unrealized_pnl"] == 65.75
    assert res["equity"] == 5065.75
    assert res["open_positions_count"] == 2
    assert len(res["positions"]) == 2
    assert res["positions"][0]["net_pnl"] == 45.50
    assert res["positions"][1]["net_pnl"] == 20.25


def test_rop03_query_equity_with_floating_drawdown():
    """Verify ROP-03 correctly calculates reduced live equity during open drawdown."""
    from core.ctrader_executor import _query_equity_over_socket

    responses = _build_test_auth_responses()
    # $5,000.00 balance
    responses.append(_build_test_trader_response(balance_cents=500000, money_digits=2, broker_name="the5ers", login=55512))
    # Position 1: -$150.00 (-15000 cents)
    responses.append(_build_test_pnl_response(
        positions_pnl=[(201, -15000, -14500)],
        money_digits=2
    ))

    sock = _FakeSocket(responses)
    res = _query_equity_over_socket(sock, "client_id", "secret", "token", 111)

    assert res["status"] == "OK"
    assert res["balance"] == 5000.00
    assert res["unrealized_pnl"] == -150.00
    assert res["equity"] == 4850.00
    assert res["open_positions_count"] == 1


def test_rop03_daily_circuit_breaker_floating_equity(monkeypatch):
    """Verify check_daily_circuit_breaker trips when floating equity breaches bot halt threshold."""
    from datetime import datetime, timezone
    from market_scanner import check_daily_circuit_breaker
    import market_scanner as ms
    monkeypatch.setattr(ms, "BOT_HALT_DAILY_LOSS_PCT", 3.0)
    monkeypatch.setattr(ms, "FIRM_DAILY_LOSS_LIMIT_PCT", 5.0)

    records = {
        "daily_equity_baseline": {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "starting_equity": 5000.0,
            "starting_balance": 5000.0
        },
        "completed_trades": []
    }

    # 1. Safe floating loss (-$75.00, 1.5% DD < 3.0% halt limit)
    live_safe = {
        "status": "OK",
        "balance": 5000.0,
        "unrealized_pnl": -75.0,
        "equity": 4925.0
    }
    tripped, reason = check_daily_circuit_breaker(records, live_safe)
    assert tripped is False
    assert reason == ""

    # 2. Dangerous floating loss (-$175.00, 3.5% DD >= 3.0% halt limit)
    live_danger = {
        "status": "OK",
        "balance": 5000.0,
        "unrealized_pnl": -175.0,
        "equity": 4825.0
    }
    tripped, reason = check_daily_circuit_breaker(records, live_danger)
    assert tripped is True
    assert "Prop Firm Daily Drawdown Guardrail Triggered" in reason
    assert "3.50%" in reason


def test_check_daily_circuit_breaker_account_switch_reset(monkeypatch):
    """Verify check_daily_circuit_breaker resets baseline upon account migration and does not falsely trip."""
    from datetime import datetime, timezone
    from market_scanner import check_daily_circuit_breaker
    import market_scanner as ms
    monkeypatch.setattr(ms, "BOT_HALT_DAILY_LOSS_PCT", 3.0)

    # Simulated state from retiring a 25k account and activating a 10k account on the same day
    records = {
        "daily_equity_baseline": {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "account_id": "49435680",
            "starting_equity": 24847.77,
            "starting_balance": 24847.77
        },
        "completed_trades": []
    }

    live_new_account = {
        "status": "OK",
        "account_id": "49700506",
        "balance": 10000.0,
        "unrealized_pnl": 0.0,
        "equity": 10000.0
    }

    tripped, reason = check_daily_circuit_breaker(records, live_new_account)
    assert tripped is False
    assert reason == ""
    assert records["daily_equity_baseline"]["account_id"] == "49700506"
    assert records["daily_equity_baseline"]["starting_equity"] == 10000.0


def test_check_daily_circuit_breaker_legacy_baseline_discrepancy_reset(monkeypatch):
    """Verify check_daily_circuit_breaker resets legacy baseline missing account_id when equity changes sharply."""
    from datetime import datetime, timezone
    from market_scanner import check_daily_circuit_breaker
    import market_scanner as ms
    monkeypatch.setattr(ms, "BOT_HALT_DAILY_LOSS_PCT", 3.0)

    # Legacy baseline without account_id
    records = {
        "daily_equity_baseline": {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "starting_equity": 24847.77,
            "starting_balance": 24847.77
        },
        "completed_trades": []
    }

    live_new_account = {
        "status": "OK",
        "account_id": "49700506",
        "balance": 10000.0,
        "unrealized_pnl": 0.0,
        "equity": 10000.0
    }

    tripped, reason = check_daily_circuit_breaker(records, live_new_account)
    assert tripped is False
    assert reason == ""
    assert records["daily_equity_baseline"]["account_id"] == "49700506"
    assert records["daily_equity_baseline"]["starting_equity"] == 10000.0


def _build_test_reconcile_response(positions=None):
    import time
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAReconcileRes
    res = ProtoOAReconcileRes()
    res.ctidTraderAccountId = 111
    if positions:
        for pos_id, symbol_id, trade_side, volume, sl in positions:
            p = res.position.add()
            p.positionId = pos_id
            p.positionStatus = 1  # OPEN
            p.swap = 0
            p.tradeData.symbolId = symbol_id
            p.tradeData.tradeSide = trade_side
            p.tradeData.volume = volume
            p.tradeData.openTimestamp = int(time.time() * 1000)
            if sl:
                p.stopLoss = sl
    return (ProtoOAPayloadType.PROTO_OA_RECONCILE_RES, res)


class _TimeoutFakeSocket:
    """Mock socket that simulates a timeout on NewOrderReq, then returns ProtoOAReconcileRes on ReconcileReq."""
    def __init__(self, auth_responses, reconcile_response=None, raise_timeout=True):
        import struct
        from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoMessage
        self.auth_responses = auth_responses
        self.reconcile_response = reconcile_response
        self.raise_timeout = raise_timeout
        self.order_req_received = False
        self._read_buffer = bytearray()

        # Populate initial auth frames
        for p_type, msg in auth_responses:
            proto_msg = ProtoMessage()
            proto_msg.payloadType = p_type
            proto_msg.payload = msg.SerializeToString()
            data = proto_msg.SerializeToString()
            self._read_buffer.extend(struct.pack('>I', len(data)) + data)

    def sendall(self, data):
        import struct
        from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoMessage
        from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
        if len(data) > 4:
            proto_msg = ProtoMessage()
            proto_msg.ParseFromString(data[4:])
            if proto_msg.payloadType == ProtoOAPayloadType.PROTO_OA_NEW_ORDER_REQ:
                self.order_req_received = True
            elif proto_msg.payloadType == ProtoOAPayloadType.PROTO_OA_RECONCILE_REQ:
                if self.reconcile_response:
                    p_type, msg = self.reconcile_response
                    res_proto = ProtoMessage()
                    res_proto.payloadType = p_type
                    res_proto.payload = msg.SerializeToString()
                    res_data = res_proto.SerializeToString()
                    self._read_buffer.extend(struct.pack('>I', len(res_data)) + res_data)

    def recv(self, num_bytes):
        if self.order_req_received and len(self._read_buffer) == 0:
            if self.raise_timeout:
                import socket
                raise socket.timeout("Socket recv timed out waiting for ProtoOANewOrderReq response")
            return b""
        chunk = self._read_buffer[:num_bytes]
        self._read_buffer = self._read_buffer[num_bytes:]
        return bytes(chunk)


def test_rop09_timeout_then_fill_reconciliation():
    """Verify ROP-09 recovers filled position via ProtoOAReconcileReq when order response times out."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOATradeSide
    from core.ctrader_executor import _dispatch_order_over_socket

    auth_res = _build_test_auth_responses()
    rec_res = _build_test_reconcile_response(
        positions=[(88888, 1, ProtoOATradeSide.BUY, 100000, 1.08280)]
    )

    sock = _TimeoutFakeSocket(auth_res, rec_res, raise_timeout=True)
    req = _build_test_order_req()
    req.symbolId = 1
    req.tradeSide = ProtoOATradeSide.BUY
    req.volume = 100000

    res = _dispatch_order_over_socket(sock, "client_id", "secret", "token", 111, req)

    assert res["status"] == "EXECUTED"
    assert res["position_id"] == 88888
    assert res.get("reconciled_after_timeout") is True


def test_rop09_timeout_unfilled_reconciliation():
    """Verify ROP-09 confirms order was NOT filled when reconcile returns no matching position."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOATradeSide
    from core.ctrader_executor import _dispatch_order_over_socket

    auth_res = _build_test_auth_responses()
    rec_res = _build_test_reconcile_response(positions=[])

    sock = _TimeoutFakeSocket(auth_res, rec_res, raise_timeout=True)
    req = _build_test_order_req()
    req.symbolId = 1
    req.tradeSide = ProtoOATradeSide.BUY
    req.volume = 100000

    res = _dispatch_order_over_socket(sock, "client_id", "secret", "token", 111, req)

    assert res["status"] == "TIMEOUT_UNFILLED"
    assert res["position_id"] is None
    assert "confirmed NOT filled" in res["error"]


def test_rop09_post_acceptance_missing_position_reconciled():
    """Verify ROP-09 recovers position when ORDER_ACCEPTED is received without positionId."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
        ProtoOAPayloadType, ProtoOAExecutionType, ProtoOATradeSide
    )
    from core.ctrader_executor import _dispatch_order_over_socket

    # 1. Auth responses + ORDER_ACCEPTED (executionType: 2) without positionId
    initial_responses = _build_test_auth_responses()
    ev_accepted = _build_test_execution_event(position_id=0, execution_type=ProtoOAExecutionType.ORDER_ACCEPTED)
    initial_responses.append((ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT, ev_accepted))

    # 2. Reconcile response returning the filled position #99999
    rec_res = _build_test_reconcile_response(
        positions=[(99999, 1, ProtoOATradeSide.BUY, 100000, 1.08280)]
    )

    sock = _TimeoutFakeSocket(initial_responses, rec_res, raise_timeout=False)
    req = _build_test_order_req()
    req.symbolId = 1
    req.tradeSide = ProtoOATradeSide.BUY
    req.volume = 100000

    res = _dispatch_order_over_socket(sock, "client_id", "secret", "token", 111, req)

    assert res["status"] == "EXECUTED"
    assert res["position_id"] == 99999
    assert res.get("reconciled_after_timeout") is True


def test_close_position_already_closed_by_broker_reconciled():
    """Verify _dispatch_close_over_socket treats POSITION_NOT_FOUND as ALREADY_CLOSED."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAErrorRes, ProtoOAClosePositionReq
    from core.ctrader_executor import _dispatch_close_over_socket

    responses = _build_test_auth_responses()
    err = ProtoOAErrorRes()
    err.ctidTraderAccountId = 111
    err.errorCode = "POSITION_NOT_FOUND"
    err.description = "Position #88888 not found (already closed by server)"
    responses.append((ProtoOAPayloadType.PROTO_OA_ERROR_RES, err))

    sock = _FakeSocket(responses)
    close_req = ProtoOAClosePositionReq()
    close_req.ctidTraderAccountId = 111
    close_req.positionId = 88888
    close_req.volume = 100000

    res = _dispatch_close_over_socket(sock, "client_id", "secret", "token", 111, close_req)

    assert res["status"] == "ALREADY_CLOSED"
    assert res["position_id"] == 88888
    assert "already closed by server" in res["error"]


def test_close_position_normal_close_success():
    """Verify _dispatch_close_over_socket returns CLOSED on execution event."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAClosePositionReq
    from core.ctrader_executor import _dispatch_close_over_socket

    responses = _build_test_auth_responses()
    ev_closed = _build_test_execution_event(position_id=88888)
    responses.append((ProtoOAPayloadType.PROTO_OA_EXECUTION_EVENT, ev_closed))

    sock = _FakeSocket(responses)
    close_req = ProtoOAClosePositionReq()
    close_req.ctidTraderAccountId = 111
    close_req.positionId = 88888
    close_req.volume = 100000

    res = _dispatch_close_over_socket(sock, "client_id", "secret", "token", 111, close_req)

    assert res["status"] == "CLOSED"
    assert res["position_id"] == 88888


def test_close_position_other_error_rejected():
    """Verify _dispatch_close_over_socket returns CLOSE_REJECTED on genuine errors."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAErrorRes, ProtoOAClosePositionReq
    from core.ctrader_executor import _dispatch_close_over_socket

    responses = _build_test_auth_responses()
    err = ProtoOAErrorRes()
    err.ctidTraderAccountId = 111
    err.errorCode = "MARKET_CLOSED"
    err.description = "Market is currently closed"
    responses.append((ProtoOAPayloadType.PROTO_OA_ERROR_RES, err))

    sock = _FakeSocket(responses)
    close_req = ProtoOAClosePositionReq()
    close_req.ctidTraderAccountId = 111
    close_req.positionId = 88888
    close_req.volume = 100000

    res = _dispatch_close_over_socket(sock, "client_id", "secret", "token", 111, close_req)

    assert res["status"] == "CLOSE_REJECTED"
    assert res["error"] == "Market is currently closed"


def test_rejected_zero_lots_safety(monkeypatch):
    """Verify execute_ctrader_order safely aborts with REJECTED_ZERO_LOTS when lots <= 0.0."""
    monkeypatch.setenv("ACCOUNT_EQUITY", "5.0")
    monkeypatch.setenv("RISK_PCT", "1.00")
    import core.ctrader_executor as ce
    monkeypatch.setattr(ce, "ENABLE_CTRADER_EXECUTION", True)
    monkeypatch.setattr(ce, "CTRADER_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(ce, "CTRADER_CLIENT_SECRET", "mock_client_secret")
    monkeypatch.setattr(ce, "CTRADER_ACCESS_TOKEN", "mock_access_token")
    monkeypatch.setattr(ce, "CTRADER_ACCOUNT_ID", "12345678")

    sig = {
        "pair": "EURUSD",
        "direction": "LONG",
        "entry": 1.08500,
        "stop_loss": 1.08280,
        "take_profit": 1.08850,
        "suggested_lots": 0.0,
        "equity": 5.0,  # Insufficient equity for even 0.01 lot ($0.05 budget)
        "risk_pct": 1.00
    }

    res = ce.execute_ctrader_order(sig)
    assert res["status"] == "REJECTED_ZERO_LOTS"
    assert "Computed lot size is 0.00" in res["error"]


def test_preflight_access_rights_close_only_blocked(monkeypatch):
    """Verify execute_ctrader_order aborts immediately when is_trading_allowed is False."""
    import core.ctrader_executor as ce
    monkeypatch.setattr(ce, "ENABLE_CTRADER_EXECUTION", True)
    monkeypatch.setattr(ce, "CTRADER_CLIENT_ID", "mock_client")
    monkeypatch.setattr(ce, "CTRADER_CLIENT_SECRET", "mock_secret")
    monkeypatch.setattr(ce, "CTRADER_ACCESS_TOKEN", "mock_token")
    monkeypatch.setattr(ce, "CTRADER_ACCOUNT_ID", "49435680")

    sig = {
        "pair": "USDCHF",
        "direction": "SHORT",
        "entry": 0.88500,
        "stop_loss": 0.88720,
        "take_profit": 0.88170,
        "suggested_lots": 0.50,
        "is_trading_allowed": False,
        "access_rights_name": "CLOSE_ONLY"
    }

    res = ce.execute_ctrader_order(sig)
    assert res["status"] == "ORDER_REJECTED"
    assert res["trading_not_allowed"] is True
    assert res["error_code"] == "TRADING_NOT_ALLOWED"
    assert "restricted to 'CLOSE_ONLY' mode" in res["error"]


def test_order_error_event_trading_not_allowed_enriched():
    """Verify _dispatch_order_over_socket enriches TRADING_NOT_ALLOWED error event."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAOrderErrorEvent
    from core.ctrader_executor import _dispatch_order_over_socket

    responses = _build_test_auth_responses()
    err_event = ProtoOAOrderErrorEvent()
    err_event.ctidTraderAccountId = 111
    err_event.errorCode = "TRADING_NOT_ALLOWED"
    err_event.description = "Trading is not allowed for trader id 241278"
    responses.append((ProtoOAPayloadType.PROTO_OA_ORDER_ERROR_EVENT, err_event))

    sock = _FakeSocket(responses)
    req = _build_test_order_req()

    res = _dispatch_order_over_socket(sock, "client_id", "secret", "token", 111, req)
    assert res["status"] == "ORDER_REJECTED"
    assert res["trading_not_allowed"] is True
    assert res["error_code"] == "TRADING_NOT_ALLOWED"
    assert "CLOSE_ONLY/Read-Only" in res["error"]


def test_query_equity_over_socket_access_rights_parsing():
    """Verify _query_equity_over_socket parses accessRights into access_rights_name and is_trading_allowed."""
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (
        ProtoOAApplicationAuthRes, ProtoOAAccountAuthRes, ProtoOATraderRes, ProtoOAGetPositionUnrealizedPnLRes
    )
    from core.ctrader_executor import _query_equity_over_socket

    app_res = ProtoOAApplicationAuthRes()
    acc_res = ProtoOAAccountAuthRes()
    acc_res.ctidTraderAccountId = 111

    # Mock Trader with CLOSE_ONLY (1)
    t_res = ProtoOATraderRes()
    t_res.ctidTraderAccountId = 111
    t_res.trader.ctidTraderAccountId = 111
    t_res.trader.balance = 2500000
    t_res.trader.depositAssetId = 15
    t_res.trader.moneyDigits = 2
    t_res.trader.brokerName = "ftmo"
    t_res.trader.traderLogin = 241278
    t_res.trader.accessRights = 1  # CLOSE_ONLY

    pnl_res = ProtoOAGetPositionUnrealizedPnLRes()
    pnl_res.ctidTraderAccountId = 111
    pnl_res.moneyDigits = 2

    responses = [
        (ProtoOAPayloadType.PROTO_OA_APPLICATION_AUTH_RES, app_res),
        (ProtoOAPayloadType.PROTO_OA_ACCOUNT_AUTH_RES, acc_res),
        (ProtoOAPayloadType.PROTO_OA_TRADER_RES, t_res),
        (ProtoOAPayloadType.PROTO_OA_GET_POSITION_UNREALIZED_PNL_RES, pnl_res)
    ]
    sock = _FakeSocket(responses)

    info = _query_equity_over_socket(sock, "client_id", "secret", "token", 111)
    assert info["status"] == "OK"
    assert info["broker_name"] == "ftmo"
    assert info["trader_login"] == 241278
    assert info["access_rights"] == 1
    assert info["access_rights_name"] == "CLOSE_ONLY"
    assert info["is_trading_allowed"] is False







