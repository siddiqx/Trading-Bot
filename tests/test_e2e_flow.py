"""End-to-End integration test covering the complete pipeline."""


def test_full_pipeline_flow(client):
    # 1. Health check
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"

    # 2. Post new test signal
    payload = {
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
        "signal_score": 85.0,
        "adx": 28.5,
        "atr": 0.00114,
        "roc": 0.42,
        "htf_regime": "BULLISH",
        "breakout_length": 20,
        "atr_multiplier": 1.75,
        "strategy_version": "1.0.0",
        "webhook_secret": "test-secret-key-12345",
        "environment": "TEST",
        "signal_id": "TEST_EURUSD_E2E_001",
    }
    res_webhook = client.post("/webhook/tradingview", json=payload)
    assert res_webhook.status_code == 200
    data = res_webhook.json()
    assert data["status"] == "ACCEPTED"
    assert data["signal_id"] == "TEST_EURUSD_E2E_001"

    # 3. Duplicate protection check
    res_dup = client.post("/webhook/tradingview", json=payload)
    assert res_dup.status_code == 200
    assert res_dup.json()["status"] == "DUPLICATE_IGNORED"

    # 4. Check /webhook/stats
    res_stats = client.get("/webhook/stats")
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert stats["total_signals"] == 1
    assert stats["long_signals"] == 1
    assert stats["test_signals"] == 1
    assert stats["signals_by_pair"]["EURUSD"] == 1

    # 5. Check /webhook/last
    res_last = client.get("/webhook/last")
    assert res_last.status_code == 200
    last_sig = res_last.json()
    assert last_sig["symbol"] == "EURUSD"
    assert last_sig["entry"] == 1.0850
