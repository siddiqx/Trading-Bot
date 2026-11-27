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
