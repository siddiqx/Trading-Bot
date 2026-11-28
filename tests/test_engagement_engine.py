"""
Unit Tests for Community Engagement & Educational Content Engine
================================================================
Tests economic calendar briefing generation, community polls, ICT educational cards,
VIP promotion drops, and automated cooldown scheduling.
"""

from datetime import datetime, timezone, timedelta
from core.marketing.engagement_engine import (
    generate_daily_news_briefing,
    get_community_poll,
    get_ict_educational_card,
    get_vip_promotion_card,
    check_and_dispatch_engagement_content,
    COMMUNITY_POLLS,
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
    assert "Non-Farm Employment Change" in res["telegram_msg"]
    assert "Flash Manufacturing PMI" in res["telegram_msg"]
    assert "Low Impact Report" not in res["telegram_msg"]
    assert "🇺🇸" in res["telegram_msg"]
    assert "🇪🇺" in res["telegram_msg"]
    assert "Algorithmic Risk Guard" in res["telegram_msg"]


def test_generate_daily_news_briefing_clean_runway():
    ref_dt = datetime(2026, 11, 28, 7, 0, 0, tzinfo=timezone.utc)
    res = generate_daily_news_briefing(events=[], now_dt=ref_dt)
    assert res["events_count"] == 0
    assert res["has_high_impact"] is False
    assert "Clean Macro Runway" in res["telegram_msg"]


def test_community_polls_structure():
    assert len(COMMUNITY_POLLS) >= 5
    for p in COMMUNITY_POLLS:
        assert "id" in p
        assert "question" in p
        assert "options" in p
        assert len(p["options"]) >= 2
        assert len(p["question"]) <= 300

    poll0 = get_community_poll(0)
    poll1 = get_community_poll(1)
    assert poll0 != poll1


def test_ict_educational_cards_structure():
    assert len(ICT_EDUCATIONAL_CARDS) >= 6
    for c in ICT_EDUCATIONAL_CARDS:
        assert "id" in c
        assert "title" in c
        assert "telegram_msg" in c
        assert "discord_desc" in c
        assert len(c["telegram_msg"]) > 100
        assert "Whop" in c["telegram_msg"] or "VIP" in c["telegram_msg"]

    card0 = get_ict_educational_card(0)
    card1 = get_ict_educational_card(1)
    assert card0["id"] != card1["id"]


def test_vip_promotion_cards_structure():
    assert len(VIP_PROMOTION_CARDS) >= 2
    for c in VIP_PROMOTION_CARDS:
        assert "id" in c
        assert "telegram_msg" in c
        assert "Whop" in c["telegram_msg"]


def test_discord_content_and_poll_invalid_url():
    # Graceful False when webhook url is invalid
    res_c = send_discord_content("Title", "Desc", webhook_url="https://invalid-discord.com")
    assert res_c is False

    res_p = send_discord_poll("Question", ["A", "B"], webhook_url="https://invalid-discord.com")
    assert res_p is False


def test_send_telegram_poll_suppressed_in_test_mode():
    res = send_telegram_poll("What is your bias?", ["Long", "Short"])
    assert res is True


def test_check_and_dispatch_engagement_content(monkeypatch):
    dispatched = []

    def mock_tg_alert(msg, specific_chat_id=None, protect_content=None):
        dispatched.append(("TG_ALERT", msg, specific_chat_id))
        return True

    def mock_tg_poll(question, options, specific_chat_id=None, is_anonymous=True):
        dispatched.append(("TG_POLL", question, specific_chat_id))
        return True

    def mock_dc_content(title, description, category=None, color=None):
        dispatched.append(("DC_CONTENT", title))
        return True

    def mock_dc_poll(question, options):
        dispatched.append(("DC_POLL", question))
        return True

    monkeypatch.setattr("market_scanner._safe_send_telegram_alert", mock_tg_alert)
    monkeypatch.setattr("market_scanner.send_telegram_poll", mock_tg_poll)
    monkeypatch.setattr("core.marketing.engagement_engine.send_discord_content", mock_dc_content)
    monkeypatch.setattr("core.marketing.engagement_engine.send_discord_poll", mock_dc_poll)
    monkeypatch.setattr("market_scanner.save_state", lambda s: None)

    state = {}
    now = datetime(2026, 11, 28, 11, 0, 0, tzinfo=timezone.utc)

    # 1. First run -> Dispatches ICT card (Mid-day session)
    ok, desc = check_and_dispatch_engagement_content(state, now_dt=now, content_type="ICT")
    assert ok is True
    assert "ICT Masterclass Card" in desc
    assert len(dispatched) >= 2
    assert "last_engagement_post_ts" in state

    # 2. Within 3 hours -> Cooldown active
    dispatched.clear()
    now_later = now + timedelta(hours=1)
    ok2, desc2 = check_and_dispatch_engagement_content(state, now_dt=now_later)
    assert ok2 is False
    assert "Cooldown active" in desc2
    assert len(dispatched) == 0

    # 3. Force bypasses cooldown and sends Poll
    ok3, desc3 = check_and_dispatch_engagement_content(state, now_dt=now_later, force=True, content_type="POLL")
    assert ok3 is True
    assert "Interactive Poll" in desc3
    assert len(dispatched) >= 2
