"""Unit tests for core.ctrader_executor (cTrader Open API Auto-Execution Engine)."""

import pytest
from core.ctrader_executor import (
    get_symbol_id,
    has_valid_credentials,
    execute_ctrader_order,
    modify_ctrader_position,
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
