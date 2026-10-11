"""Unit and integration tests for TradingView webhook processing."""

import pytest


@pytest.fixture
def valid_long_payload():
    return {
        "event": "forex_signal",
        "strategy": "adaptive_trend_momentum_breakout",
        "version": "1.0.0",
        "symbol": "EURUSD",
        "exchange": "FX",
        "timeframe": "60",
        "direction": "LONG",
        "signal_time": "2026-03-09T14:00:00Z",
        "price": 1.0850,
        "entry": 1.0850,
        "stop_loss": 1.0830,
        "take_profit": 1.0890,
        "risk_reward": 2.0,
        "signal_score": 82.0,
        "adx": 27.5,
        "atr": 0.00114,
        "roc": 0.42,
        "htf_regime": "BULLISH",
        "breakout_length": 20,
        "atr_multiplier": 1.75,
        "strategy_version": "1.0.0",
        "webhook_secret": "test-secret-key-12345",
        "environment": "TEST",
    }


@pytest.fixture
def valid_short_payload():
    return {
        "event": "forex_signal",
        "strategy": "adaptive_trend_momentum_breakout",
        "version": "1.0.0",
        "symbol": "GBPUSD",
        "exchange": "FX",
        "timeframe": "60",
        "direction": "SHORT",
        "signal_time": "2026-03-09T15:00:00Z",
        "price": 1.2650,
        "entry": 1.2650,
        "stop_loss": 1.2680,
        "take_profit": 1.2590,
        "risk_reward": 2.0,
        "signal_score": 78.0,
        "adx": 26.0,
        "atr": 0.00171,
        "roc": -0.38,
        "htf_regime": "BEARISH",
        "breakout_length": 20,
        "atr_multiplier": 1.75,
        "strategy_version": "1.0.0",
        "webhook_secret": "test-secret-key-12345",
        "environment": "TEST",
    }


def test_valid_webhook_long(client, valid_long_payload):
    response = client.post("/webhook/tradingview", json=valid_long_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ACCEPTED"
    assert data["signal_id"] is not None


def test_valid_webhook_short(client, valid_short_payload):
    response = client.post("/webhook/tradingview", json=valid_short_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ACCEPTED"


def test_invalid_secret(client, valid_long_payload):
    valid_long_payload["webhook_secret"] = "wrong-unauthorized-secret"
    response = client.post("/webhook/tradingview", json=valid_long_payload)
    assert response.status_code == 401
    assert "Invalid or missing webhook secret" in response.json()["detail"]


def test_missing_required_fields(client):
    payload = {
        "symbol": "EURUSD",
        "direction": "LONG",
        "webhook_secret": "test-secret-key-12345",
    }
    response = client.post("/webhook/tradingview", json=payload)
    assert response.status_code == 422  # Pydantic validation error


def test_invalid_direction(client, valid_long_payload):
    valid_long_payload["direction"] = "SIDEWAYS"
    response = client.post("/webhook/tradingview", json=valid_long_payload)
    assert response.status_code == 422


def test_invalid_price_geometry_long(client, valid_long_payload):
    valid_long_payload["stop_loss"] = 1.0900
    valid_long_payload["entry"] = 1.0850
    response = client.post("/webhook/tradingview", json=valid_long_payload)
    assert response.status_code == 422


def test_invalid_price_geometry_short(client, valid_short_payload):
    valid_short_payload["stop_loss"] = 1.2500
    valid_short_payload["entry"] = 1.2650
    response = client.post("/webhook/tradingview", json=valid_short_payload)
    assert response.status_code == 422


def test_duplicate_signal_protection(client, valid_long_payload):
    # First delivery
    resp1 = client.post("/webhook/tradingview", json=valid_long_payload)
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "ACCEPTED"

    # Second delivery with exact same payload
    resp2 = client.post("/webhook/tradingview", json=valid_long_payload)
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "DUPLICATE_IGNORED"
    assert "Duplicate signal event" in resp2.json()["message"]


def test_gold_signal_sent_to_webhook_is_rejected(client, valid_long_payload):
    """Verify that a gold signal sent directly to the webhook is rejected and never reaches Telegram."""
    valid_long_payload["symbol"] = "XAUUSD"
    valid_long_payload["price"] = 2650.00
    valid_long_payload["entry"] = 2650.00
    valid_long_payload["stop_loss"] = 2640.00
    valid_long_payload["take_profit"] = 2665.00
    valid_long_payload["signal_id"] = "XAUUSD_TEST_WEBHOOK_REJECT"

    response = client.post("/webhook/tradingview", json=valid_long_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "REJECTED"
    assert "Gold" in data["message"] or "excluded" in data["message"].lower()
    assert data["telegram_delivered"] is False
