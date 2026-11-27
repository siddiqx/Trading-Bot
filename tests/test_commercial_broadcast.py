"""
Unit Tests for Commercial Dual-Channel Broadcasting & Anti-Forwarding Security:
- Public Channel Quota Management (Max 4 signals/week).
- Locked Teaser Dispatch after Quota Exceeded.
- Weekly Counter Reset on Monday/New Week.
- Anti-Forwarding and Content Protection (`protect_content=True`).
"""

import os
import pytest
from datetime import datetime, timezone
from market_scanner import broadcast_commercial_signal, format_locked_teaser_message


def test_public_channel_under_quota(monkeypatch):
    """Verify that signals under the 4-trade weekly limit are broadcast to public channel."""
    state = {
        "alerted_signals": [],
        "public_signals_week": datetime.now(timezone.utc).strftime("%Y-W%W"),
        "public_signals_count": 1,
    }
    sig = {
        "pair": "EURUSD",
        "direction": "LONG",
        "strategy": "CCRS_DUAL_TF",
        "strategy_type": "CCRS_DUAL_TF",
        "timeframe": "15M",
        "entry": 1.0850,
        "stop_loss": 1.0828,
        "take_profit": 1.0888,
        "sl_pips": 22.0,
        "tp_pips": 38.5,
        "rr": 1.75,
        "divergence": 2.65,
        "setup_name": "15M 20-EMA Equilibrium Pullback Rejection",
    }

    sent_alerts = []

    def mock_send(text, max_retries=3, specific_chat_id=None, protect_content=None):
        sent_alerts.append({
            "text": text,
            "chat_id": specific_chat_id,
            "protect_content": protect_content
        })
        return True

    monkeypatch.setattr("market_scanner.send_telegram_alert", mock_send)
    monkeypatch.setattr("market_scanner.save_state", lambda s: None)

    res = broadcast_commercial_signal(sig, state)
    assert res["public_sent"] is True
    assert state["public_signals_count"] == 2

    # Check public payload includes quota note and content protection
    pub_alert = next(a for a in sent_alerts if a["chat_id"] == "@ccrs_forex_signals")
    assert "Free Public Signal (2/4 this week)" in pub_alert["text"]
    assert pub_alert["protect_content"] is True


def test_public_channel_quota_exceeded_sends_locked_teaser(monkeypatch):
    """Verify that when 4 signals have been sent, the public channel receives a locked teaser."""
    state = {
        "alerted_signals": [],
        "public_signals_week": datetime.now(timezone.utc).strftime("%Y-W%W"),
        "public_signals_count": 4,  # Quota full
    }
    sig = {
        "pair": "USDCAD",
        "direction": "SHORT",
        "strategy": "CCRS_DUAL_TF",
        "strategy_type": "CCRS_DUAL_TF",
        "timeframe": "15M",
        "entry": 1.3450,
        "stop_loss": 1.3472,
        "take_profit": 1.3411,
        "sl_pips": 22.0,
        "tp_pips": 38.5,
        "rr": 1.75,
        "divergence": -2.70,
        "setup_name": "15M Donchian Turtle Soup Reclaim",
    }

    sent_alerts = []

    def mock_send(text, max_retries=3, specific_chat_id=None, protect_content=None):
        sent_alerts.append({
            "text": text,
            "chat_id": specific_chat_id,
            "protect_content": protect_content
        })
        return True

    monkeypatch.setattr("market_scanner.send_telegram_alert", mock_send)
    monkeypatch.setattr("market_scanner.save_state", lambda s: None)

    res = broadcast_commercial_signal(sig, state)
    assert res["public_sent"] is True
    # Count should remain at 4 (not increment further)
    assert state["public_signals_count"] == 4

    pub_alert = next(a for a in sent_alerts if a["chat_id"] == "@ccrs_forex_signals")
    # Verify locked teaser content
    assert "ACTIVE EXCLUSIVELY IN VIP CHANNEL" in pub_alert["text"]
    assert "Weekly public quota reached (4/4 signals shared this week)" in pub_alert["text"]
    # Exact entry and SL must NOT be in the teaser text
    assert "Ideal Entry:" not in pub_alert["text"]
    assert "1.3450" not in pub_alert["text"]


def test_weekly_counter_resets_on_new_week(monkeypatch):
    """Verify that when a new calendar week starts, the public count resets to 0."""
    state = {
        "alerted_signals": [],
        "public_signals_week": "2026-W40",  # Old week
        "public_signals_count": 4,
    }
    sig = {
        "pair": "EURUSD",
        "direction": "LONG",
        "strategy_type": "CCRS_DUAL_TF",
        "entry": 1.0850,
        "stop_loss": 1.0828,
        "take_profit": 1.0888,
        "sl_pips": 22.0,
        "tp_pips": 35.0,
        "divergence": 2.10,
    }

    monkeypatch.setattr("market_scanner.send_telegram_alert", lambda *a, **kw: True)
    monkeypatch.setattr("market_scanner.save_state", lambda s: None)

    broadcast_commercial_signal(sig, state)
    current_week = datetime.now(timezone.utc).strftime("%Y-W%W")
    assert state["public_signals_week"] == current_week
    assert state["public_signals_count"] == 1  # Reset to 0 then incremented to 1
