"""
Unit Tests for Community Engagement & Educational Content Engine
================================================================
Tests economic calendar briefing generation, context-aware non-contradictory polls,
ICT educational cards, VIP promotion drops, and automated cooldown scheduling.
"""

from datetime import datetime, timezone, timedelta
import re

from core.marketing.engagement_engine import (
    generate_daily_news_briefing,
    build_natural_community_poll,
    get_ict_educational_card,
    get_vip_promotion_card,
    check_and_dispatch_engagement_content,
    CORE_EDUCATIONAL_POLLS,
    ICT_EDUCATIONAL_CARDS,
    VIP_PROMOTION_CARDS,
)
from core.marketing.discord_publisher import send_discord_content, send_discord_poll
from market_scanner import send_telegram_poll


def test_generate_daily_news_briefing_with_events():
    mock_events = [
        {
            "title": "Non-Farm Employment Change",
            "country": "USD",
            "date": "2026-11-28T13:30:00Z",
            "impact": "High",
            "forecast": "180K",
            "previous": "150K"
        },
        {
            "title": "Flash Manufacturing PMI",
            "country": "EUR",
            "date": "2026-11-28T09:00:00Z",
            "impact": "Medium",
            "forecast": "46.2",
            "previous": "45.8"
        },
        {
            "title": "Low Impact Report",
            "country": "USD",
            "date": "2026-11-28T15:00:00Z",
            "impact": "Low",
            "forecast": "",
            "previous": ""
        }
    ]
    ref_dt = datetime(2026, 11, 28, 7, 0, 0, tzinfo=timezone.utc)
    res = generate_daily_news_briefing(events=mock_events, now_dt=ref_dt)
    
    assert res["type"] == "NEWS_BRIEFING"
    assert res["events_count"] == 2  # High + Medium
    assert res["has_high_impact"] is True
    assert res["skip"] is False
    assert "Non-Farm Employment Change" in res["telegram_msg"]
    assert "Flash Manufacturing PMI" in res["telegram_msg"]
    assert "Low Impact Report" not in res["telegram_msg"]
    assert "🇺🇸" in res["telegram_msg"]
    assert "🇪🇺" in res["telegram_msg"]
    assert "Algorithmic Risk Guard" in res["telegram_msg"]


def test_generate_daily_news_briefing_skips_when_empty():
    ref_dt = datetime(2026, 11, 28, 7, 0, 0, tzinfo=timezone.utc)
    res = generate_daily_news_briefing(events=[], now_dt=ref_dt)
    assert res["events_count"] == 0
    assert res["has_high_impact"] is False
    assert res["skip"] is True  # Avoids posting artificial filler text


def test_build_natural_poll_active_trade_alignment():
    """When an active trade exists on EURUSD Short, poll asks for position management, NOT conflicting bias."""
    mock_records = {
        "active_trades": {
            "tr_123": {
                "pair": "EURUSD",
                "direction": "SHORT",
                "entry": 1.0850,
                "stop_loss": 1.0875,
                "take_profit": 1.08125
            }
        }
    }
    state = {}
    poll = build_natural_community_poll(state, records=mock_records)
    assert "EUR/USD Short" in poll["question"]
    assert "Position Management" in poll["question"]
    # Check options are clean and authentic
    assert "Holding to full 1:1.50R Take Profit" in poll["options"]
    assert "Stop Loss trailed to Breakeven" in poll["options"]
    # Verify no fabricated target prices like '1.0950'
    for opt in poll["options"]:
        assert not re.search(r"\d\.\d{4}", opt)


def test_build_natural_poll_avoids_recently_alerted_pairs():
    """When EURUSD and USDCAD were recently signaled, session bias poll chooses a different neutral pair."""
    mock_records = {"active_trades": {}}
    state = {
        "alerted_signals": [
            "EURUSD_15M_2026-11-28T08:00:00Z_SHORT",
            "USDCAD_15M_2026-11-28T09:00:00Z_LONG",
        ]
    }
    now_dt = datetime(2026, 11, 25, 8, 30, 0, tzinfo=timezone.utc)  # Wednesday London session
    poll = build_natural_community_poll(state, records=mock_records, now_dt=now_dt)
    assert "EUR/USD" not in poll["question"]
    assert "USD/CAD" not in poll["question"]
    # Should choose USD/CHF or AUD/USD
    assert any(sym in poll["question"] for sym in ["USD/CHF", "AUD/USD"])
    # Options use clean price action terms (Bullish, Bearish, MSS)
    assert any("Bullish" in opt for opt in poll["options"])
    assert any("Bearish" in opt for opt in poll["options"])
    assert any("Market Structure Shift" in opt for opt in poll["options"])


def test_build_natural_poll_ccrs_macro_divergence():
    """Leverages live mathematical divergence from CCRS matrix."""
    mock_records = {"active_trades": {}}
    state = {"alerted_signals": []}
    mock_ccrs = {
        "latest_div": {
            "AUDUSD": +3.48,
            "EURUSD": +1.49,
            "USDCHF": -1.56,
            "USDCAD": -2.23
        }
    }
    poll = build_natural_community_poll(state, records=mock_records, ccrs_matrix=mock_ccrs)
    assert "AUD/USD" in poll["question"]
    assert "+3.48σ" in poll["question"]
    assert any("Market Structure Shift" in opt for opt in poll["options"])


def test_ict_educational_cards_structure():
    assert len(ICT_EDUCATIONAL_CARDS) >= 6
    for c in ICT_EDUCATIONAL_CARDS:
        assert "id" in c
        assert "title" in c
        assert "telegram_msg" in c
        assert "discord_desc" in c
        assert len(c["telegram_msg"]) > 100
        assert "Whop" in c["telegram_msg"] or "VIP" in c["telegram_msg"]


def test_vip_promotion_cards_structure():
    assert len(VIP_PROMOTION_CARDS) >= 2
    for c in VIP_PROMOTION_CARDS:
        assert "id" in c
        assert "telegram_msg" in c
        assert "Whop" in c["telegram_msg"]


def test_discord_content_and_poll_invalid_url():
    res_c = send_discord_content("Title", "Desc", webhook_url="https://invalid-discord.com")
    assert res_c is False

    res_p = send_discord_poll("Question", ["A", "B"], webhook_url="https://invalid-discord.com")
    assert res_p is False


def test_send_telegram_poll_suppressed_in_test_mode():
    res = send_telegram_poll("What is your bias?", ["Long", "Short"])
    assert res is True


def test_post_signal_quiet_buffer(monkeypatch):
    """Verifies that non-signal engagement content holds silence for 60m after a live trade signal."""
    monkeypatch.setattr("market_scanner._safe_send_telegram_alert", lambda *a, **kw: True)
    monkeypatch.setattr("market_scanner.save_state", lambda s: None)

    now = datetime(2026, 11, 28, 14, 0, 0, tzinfo=timezone.utc)
    # Signal was sent 15 minutes ago
    state = {
        "last_signal_time": (now - timedelta(minutes=15)).isoformat()
    }
    ok, reason = check_and_dispatch_engagement_content(state, now_dt=now)
    assert ok is False
    assert "Holding silence" in reason


def test_dead_zone_suppression(monkeypatch):
    """Verifies that engagement posts are suppressed between 21:00 and 06:00 UTC."""
    now_night = datetime(2026, 11, 28, 23, 0, 0, tzinfo=timezone.utc)
    state = {}
    ok, reason = check_and_dispatch_engagement_content(state, now_dt=now_night)
    assert ok is False
    assert "dead-zone" in reason
