"""
Unit Tests for Commercial Dual-Channel Broadcasting & Anti-Forwarding Security:
- Public Channel Quota Management (Max 4 signals/week).
- Locked Teaser Dispatch after Quota Exceeded.
- Weekly Counter Reset on Monday/New Week.
- Anti-Forwarding and Content Protection (`protect_content=True`).
"""

import os
import pytest
from datetime import datetime, timezone, timedelta
from market_scanner import (
    broadcast_commercial_signal,
    format_locked_teaser_message,
    calculate_consecutive_wins,
    format_public_tp_celebration,
    broadcast_trade_exit,
    check_and_send_periodic_vip_broadcast,
    get_periodic_vip_broadcast_templates,
)


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


def test_calculate_consecutive_wins():
    """Verify consecutive win streak calculation under various historical sequences."""
    # 1. Empty history, current WIN -> 1
    assert calculate_consecutive_wins([], current_outcome="WIN") == 1

    # 2. Current LOSS -> 0
    assert calculate_consecutive_wins([{"outcome": "WIN"}], current_outcome="LOSS") == 0

    # 3. Two previous wins + current WIN -> 3
    history_2_wins = [
        {"trade_id": "T1", "outcome": "WIN"},
        {"trade_id": "T2", "outcome": "WIN"},
    ]
    assert calculate_consecutive_wins(history_2_wins, current_outcome="WIN", current_trade_id="T3") == 3

    # 4. Break-even in between does not break streak
    history_with_be = [
        {"trade_id": "T1", "outcome": "WIN"},
        {"trade_id": "T2", "outcome": "BREAK_EVEN"},
        {"trade_id": "T3", "outcome": "WIN"},
    ]
    assert calculate_consecutive_wins(history_with_be, current_outcome="WIN", current_trade_id="T4") == 3

    # 5. Loss resets streak
    history_with_loss = [
        {"trade_id": "T1", "outcome": "WIN"},
        {"trade_id": "T2", "outcome": "LOSS"},
        {"trade_id": "T3", "outcome": "WIN"},
    ]
    assert calculate_consecutive_wins(history_with_loss, current_outcome="WIN", current_trade_id="T4") == 2

    # 6. Current trade already appended in completed_trades avoided double count
    history_already_appended = [
        {"trade_id": "T1", "outcome": "WIN"},
        {"trade_id": "T2", "outcome": "WIN"},
    ]
    assert calculate_consecutive_wins(history_already_appended, current_outcome="WIN", current_trade_id="T2") == 2


def test_format_public_tp_celebration():
    """Verify formatting of Take Profit celebration card with and without streak badges."""
    trade = {
        "pair": "EURUSD",
        "direction": "LONG",
        "setup_name": "15M 20-EMA Equilibrium Pullback Rejection",
    }

    # Single win (streak = 1) -> No consecutive streak badge
    card_single = format_public_tp_celebration(trade, realized_pips=38.5, realized_r=1.75, streak=1)
    assert "TAKE PROFIT HIT — VIP SIGNAL RESOLVED IN PROFIT!" in card_single
    assert "+38.5 pips (+1.75R)" in card_single
    assert "CONSECUTIVE WINS" not in card_single
    assert "https://whop.com/checkout/plan_AD4vSV9Uz7vyR" in card_single

    # Multiple wins (streak = 4) -> Includes consecutive streak badge
    card_streak = format_public_tp_celebration(trade, realized_pips=38.5, realized_r=1.75, streak=4)
    assert "4 CONSECUTIVE WINS IN A ROW!" in card_streak
    assert "Up to 68%–70% Win Rate on High Macro Divergence" in card_streak


def test_broadcast_trade_exit_tp_win(monkeypatch):
    """Verify that on Take Profit WIN, exit is sent to Admin, VIP, and Public channel."""
    trade = {
        "trade_id": "T_EURUSD_WIN",
        "pair": "EURUSD",
        "direction": "LONG",
        "entry": 1.0850,
        "stop_loss": 1.0828,
        "take_profit": 1.0888,
        "timeframe": "15M",
    }
    records = {
        "completed_trades": [
            {"trade_id": "T_PREV_1", "outcome": "WIN"},
            {"trade_id": "T_PREV_2", "outcome": "WIN"},
        ]
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

    res = broadcast_trade_exit(
        trade=trade,
        outcome="WIN",
        exit_price=1.0888,
        realized_pips=38.5,
        realized_r=1.75,
        records=records
    )

    assert res["admin_sent"] is True
    assert res["vip_sent"] is True
    assert res["public_sent"] is True

    # Check VIP dispatch is content protected
    vip_alert = next(a for a in sent_alerts if a["chat_id"] == "-1005701371238")
    assert vip_alert["protect_content"] is True
    assert "VIP Channel Exclusive Trade Lifecycle" in vip_alert["text"]

    # Check Public celebration card contains streak: 2 prev wins + current = 3
    pub_alert = next(a for a in sent_alerts if a["chat_id"] == "@ccrs_forex_signals")
    assert pub_alert["protect_content"] is False
    assert "3 CONSECUTIVE WINS IN A ROW!" in pub_alert["text"]
    assert "+38.5 pips (+1.75R)" in pub_alert["text"]
    assert "https://whop.com/checkout/plan_AD4vSV9Uz7vyR" in pub_alert["text"]


def test_broadcast_trade_exit_loss_suppresses_public(monkeypatch):
    """Verify that on Stop Loss LOSS, exit is sent to Admin & VIP, but NOT public channel."""
    trade = {
        "trade_id": "T_USDCAD_LOSS",
        "pair": "USDCAD",
        "direction": "SHORT",
        "entry": 1.3450,
        "stop_loss": 1.3472,
        "take_profit": 1.3411,
        "timeframe": "15M",
    }
    records = {"completed_trades": []}

    sent_alerts = []

    def mock_send(text, max_retries=3, specific_chat_id=None, protect_content=None):
        sent_alerts.append({
            "text": text,
            "chat_id": specific_chat_id,
            "protect_content": protect_content
        })
        return True

    monkeypatch.setattr("market_scanner.send_telegram_alert", mock_send)

    res = broadcast_trade_exit(
        trade=trade,
        outcome="LOSS",
        exit_price=1.3472,
        realized_pips=-22.0,
        realized_r=-1.0,
        records=records
    )

    assert res["admin_sent"] is True
    assert res["vip_sent"] is True
    assert res["public_sent"] is False  # Public channel MUST NOT receive loss alert

    # Ensure no alerts were sent to @ccrs_forex_signals
    pub_alerts = [a for a in sent_alerts if a["chat_id"] == "@ccrs_forex_signals"]
    assert len(pub_alerts) == 0


def test_periodic_vip_broadcast_cooldown_and_rotation(monkeypatch):
    """Verify periodic VIP value broadcast enforces 72h cooldown and rotates educational templates."""
    state = {}
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
    monkeypatch.setattr("market_scanner.is_forex_market_open", lambda dt=None: True)

    # 1. First dispatch: should succeed and send template #0
    t0 = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
    res1 = check_and_send_periodic_vip_broadcast(state, now_dt=t0)
    assert res1 is True
    assert state["vip_broadcast_template_idx"] == 1
    assert "HOW THE CCRS INSTITUTIONAL ENGINE WORKS" in sent_alerts[-1]["text"]

    # 2. Second dispatch after 24h: within 72h cooldown -> MUST return False
    t_24h = t0 + timedelta(hours=24)
    res2 = check_and_send_periodic_vip_broadcast(state, now_dt=t_24h)
    assert res2 is False
    assert len(sent_alerts) == 1  # No new alert

    # 3. Third dispatch after 73h: cooldown elapsed -> should succeed and send template #1
    t_73h = t0 + timedelta(hours=73)
    res3 = check_and_send_periodic_vip_broadcast(state, now_dt=t_73h)
    assert res3 is True
    assert state["vip_broadcast_template_idx"] == 2
    assert "EXECUTION MATTERS: WHY DELAY KILLS EDGE" in sent_alerts[-1]["text"]
    assert len(sent_alerts) == 2

