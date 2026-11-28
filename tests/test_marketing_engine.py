"""
Unit Tests for Marketing & Growth Engine
========================================
Tests case study generation, Twitter thread synthesis, viral Telegram forward links,
and Reddit publisher fallback/draft archiving.
"""

import os
from pathlib import Path
from core.marketing import (
    generate_reddit_case_study,
    generate_twitter_thread,
    generate_telegram_share_url,
    generate_tradingview_idea_post,
    publish_reddit_case_study,
    save_local_draft,
    format_viral_share_footer,
    generate_weekly_performance_digest,
)


def test_generate_reddit_case_study():
    trade = {
        "pair": "USDCAD",
        "direction": "SHORT",
        "entry": 1.43125,
        "take_profit": 1.42735,
        "timeframe": "15M"
    }
    case_study = generate_reddit_case_study(trade, realized_pips=39.0, realized_r=1.77, target_subreddit="r/Forex")
    assert "title" in case_study
    assert "body" in case_study
    assert "USD/CAD" in case_study["title"]
    assert "+39.0" in case_study["title"]
    assert "+1.77R" in case_study["title"]
    assert "Macro Context" in case_study["body"]
    assert "Smart Money Concepts" in case_study["body"]


def test_generate_twitter_thread():
    trade = {
        "pair": "EURUSD",
        "direction": "LONG",
        "entry": 1.09135,
        "take_profit": 1.09505,
        "timeframe": "15M"
    }
    thread = generate_twitter_thread(trade, realized_pips=37.0, realized_r=1.76)
    assert len(thread) == 3
    assert "$EURUSD" in thread[0]
    assert "+37.0 pips" in thread[0]
    assert "The Setup Anatomy" in thread[1]
    assert "t.me" in thread[2]


def test_generate_tradingview_idea_post():
    trade = {
        "pair": "EURUSD",
        "direction": "SHORT",
        "entry": 1.08500,
        "stop_loss": 1.08750,
        "take_profit": 1.08125,
        "timeframe": "15M"
    }
    # 1. New Signal Setup
    tv_post = generate_tradingview_idea_post(trade)
    assert "EUR/USD" in tv_post["title"]
    assert "Order Block" in tv_post["title"]
    assert "1.08500" in tv_post["description"]
    assert "1.08750" in tv_post["description"]
    assert "1.08125" in tv_post["description"]
    assert "t.me/ccrs_forex_signals" in tv_post["description"]
    assert "forex" in tv_post["tags"]
    # Ensure zero markdown hash or asterisk symbols in description
    assert "#" not in tv_post["description"]
    assert "*" not in tv_post["description"]

    # 2. Closed Win Resolution
    tv_win = generate_tradingview_idea_post(trade, realized_pips=37.5, realized_r=1.50)
    assert "+37.5 Pips" in tv_win["title"]
    assert "(+1.50R)" in tv_win["title"]
    assert "Full Take Profit Hit" in tv_win["description"]



def test_generate_telegram_share_url():
    url = generate_telegram_share_url("EUR/USD", "LONG", 35.0, 1.75)
    assert url.startswith("https://t.me/share/url?")
    assert "QuantFlow" in url
    assert "EUR" in url


def test_publish_reddit_case_study_local_draft():
    trade = {
        "pair": "USDCHF",
        "direction": "LONG",
        "entry": 0.88500,
        "take_profit": 0.88850
    }
    case_study = generate_reddit_case_study(trade, realized_pips=35.0, realized_r=1.75)
    res = publish_reddit_case_study(case_study)
    assert res["status"] in ("DRAFT_SAVED", "PUBLISHED", "COOLDOWN_ACTIVE")
    assert "url" in res
    assert Path(res["url"]).exists() or res["url"].startswith("http")


def test_generate_weekly_performance_digest():
    mock_records = {
        "completed_trades": [
            {"pair": "EURUSD", "outcome": "WIN", "realized_pips": 35.0, "realized_r": 1.75},
            {"pair": "USDCAD", "outcome": "WIN", "realized_pips": 39.0, "realized_r": 1.77},
            {"pair": "USDCHF", "outcome": "LOSS", "realized_pips": -20.0, "realized_r": -1.00},
        ]
    }
    digest = generate_weekly_performance_digest(mock_records)
    assert "QUANTFLOW INSTITUTIONAL WEEKLY AUDIT" in digest
    assert "Total Trades Closed:</b> <b>3</b>" in digest
    assert "66.7%" in digest
    assert "Net Return Factor:</b> <b>+2.52 R</b>" in digest


def test_send_discord_signal_invalid_url():
    from core.marketing import send_discord_signal
    # Invalid url returns False without throwing
    res = send_discord_signal({"pair": "EURUSD", "entry": 1.0950}, webhook_url="https://invalid.com")
    assert res is False


def test_send_discord_tp_celebration_invalid_url():
    from core.marketing import send_discord_tp_celebration
    res = send_discord_tp_celebration({"pair": "EURUSD"}, realized_pips=30.0, realized_r=1.5, webhook_url="https://invalid-discord-webhook.com")
    assert res is False


def test_check_disboard_bump_reminder(monkeypatch):
    from datetime import datetime, timezone, timedelta
    from market_scanner import check_disboard_bump_reminder

    dispatched = []

    def mock_send(msg, specific_chat_id=None, protect_content=None):
        dispatched.append({"msg": msg, "chat_id": specific_chat_id})
        return True

    monkeypatch.setattr("market_scanner._safe_send_telegram_alert", mock_send)
    monkeypatch.setattr("market_scanner.save_state", lambda s: None)
    monkeypatch.setattr("market_scanner.TELEGRAM_CHAT_ID", "8142877259")

    # 1. First run without timestamp -> Sends
    state = {}
    t0 = datetime(2026, 11, 28, 12, 0, 0, tzinfo=timezone.utc)
    res0 = check_disboard_bump_reminder(state, now_dt=t0)
    assert res0 is True
    assert len(dispatched) == 1
    assert "DISBOARD BUMP REMINDER" in dispatched[0]["msg"]
    assert "/bump" in dispatched[0]["msg"]
    assert dispatched[0]["chat_id"] == "8142877259"
    assert state.get("last_disboard_bump_reminder_ts") == t0.isoformat()

    # 2. Within 2 hours (1 hour later) -> Suppressed by cooldown
    t1 = t0 + timedelta(hours=1)
    res1 = check_disboard_bump_reminder(state, now_dt=t1)
    assert res1 is False
    assert len(dispatched) == 1

    # 3. Exactly 2 hours and 1 minute later -> Sends
    t2 = t0 + timedelta(hours=2, minutes=1)
    res2 = check_disboard_bump_reminder(state, now_dt=t2)
    assert res2 is True
    assert len(dispatched) == 2
    assert state.get("last_disboard_bump_reminder_ts") == t2.isoformat()

    # 4. Force bypasses cooldown
    t3 = t2 + timedelta(minutes=5)
    res3 = check_disboard_bump_reminder(state, now_dt=t3, force=True)
    assert res3 is True
    assert len(dispatched) == 3

