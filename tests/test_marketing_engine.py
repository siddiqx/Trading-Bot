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
    trade_short = {
        "pair": "EURUSD",
        "direction": "SHORT",
        "entry": 1.08500,
        "stop_loss": 1.08750,
        "take_profit": 1.08125,
        "timeframe": "15M"
    }
    # 1. New Short Signal Setup: BSL sweep + MSS ▾ + -OB + SSL target
    tv_post_short = generate_tradingview_idea_post(trade_short)
    assert "EUR/USD" in tv_post_short["title"]
    assert "Bearish Setup" in tv_post_short["title"]
    assert "1.08500" in tv_post_short["description"]
    assert "1.08750" in tv_post_short["description"]
    assert "1.08125" in tv_post_short["description"]
    assert "Buy-Side Liquidity (BSL)" in tv_post_short["description"]
    assert "Market Structure Shift (MSS ▾)" in tv_post_short["description"]
    assert "Sell-Side Liquidity (SSL)" in tv_post_short["description"]
    assert "t.me/ccrs_forex_signals" in tv_post_short["description"]
    assert "forex" in tv_post_short["tags"]
    # Ensure zero markdown hash or asterisk symbols in description
    assert "#" not in tv_post_short["description"]
    assert "*" not in tv_post_short["description"]
    assert "+-" not in tv_post_short["description"]

    # 2. New Long Signal Setup: SSL sweep + MSS ▴ + +OB + BSL target
    trade_long = {
        "pair": "USDCAD",
        "direction": "LONG",
        "entry": 1.38500,
        "stop_loss": 1.38280,
        "take_profit": 1.38830,
        "timeframe": "15M"
    }
    tv_post_long = generate_tradingview_idea_post(trade_long)
    assert "Sell-Side Liquidity (SSL)" in tv_post_long["description"]
    assert "Market Structure Shift (MSS ▴)" in tv_post_long["description"]
    assert "Buy-Side Liquidity (BSL)" in tv_post_long["description"]

    # 3. Closed Win Resolution
    tv_win = generate_tradingview_idea_post(trade_short, realized_pips=37.5, realized_r=1.50)
    assert "+37.5 Pips" in tv_win["title"]
    assert "(+1.50R)" in tv_win["title"]
    assert "Full Take Profit Hit" in tv_win["description"]
    assert "+-" not in tv_win["title"]
    assert "+-" not in tv_win["description"]
    assert "#" not in tv_win["description"]
    assert "*" not in tv_win["description"]


def test_generate_market_trend_outlook():
    from core.marketing import generate_market_trend_outlook, format_market_outlook_telegram_pack
    import pandas as pd
    import numpy as np

    dates = pd.date_range("2026-11-20", periods=50, freq="4h")
    prices = 1.0850 + np.cumsum(np.random.normal(0, 0.0010, 50))
    df_4h = pd.DataFrame({
        "open": prices,
        "high": prices + 0.0015,
        "low": prices - 0.0015,
        "close": prices + 0.0005,
        "volume": [2000] * 50
    }, index=dates)

    outlook = generate_market_trend_outlook("EURUSD", df=df_4h)
    assert "EUR/USD" in outlook["title"]
    assert "Macro Trend Outlook" in outlook["title"]
    assert "MARKET CONTEXT" in outlook["description"]
    assert "KEY STRUCTURAL LEVELS" in outlook["description"]
    assert "TRADING GAME PLAN" in outlook["description"]
    assert "#" not in outlook["description"]
    assert "*" not in outlook["description"]
    assert "+-" not in outlook["description"]

    pack = format_market_outlook_telegram_pack("EURUSD", df=df_4h)
    assert "TRADINGVIEW MARKET TREND OUTLOOK PACK" in pack
    assert "<pre>" in pack



def test_generate_telegram_share_url():
    url = generate_telegram_share_url("EUR/USD", "LONG", 35.0, 1.75)
    assert url.startswith("https://t.me/share/url?")
    assert "QuantFlow" in url
    assert "EUR" in url


def test_publish_reddit_case_study_local_draft():
    trade_long = {
        "pair": "USDCHF",
        "direction": "LONG",
        "entry": 0.88500,
        "take_profit": 0.88850
    }
    case_study_long = generate_reddit_case_study(trade_long, realized_pips=35.0, realized_r=1.75)
    assert "Sell-Side Liquidity (SSL)" in case_study_long["body"]
    assert "Buy-Side Liquidity (BSL)" in case_study_long["body"]
    assert "Market Structure Shift (MSS ▴)" in case_study_long["body"]
    assert "Bullish Demand Order Block (+OB)" in case_study_long["body"]

    trade_short = {
        "pair": "EURUSD",
        "direction": "SHORT",
        "entry": 1.08500,
        "take_profit": 1.08150
    }
    case_study_short = generate_reddit_case_study(trade_short, realized_pips=35.0, realized_r=1.75)
    assert "Buy-Side Liquidity (BSL)" in case_study_short["body"]
    assert "Sell-Side Liquidity (SSL)" in case_study_short["body"]
    assert "Market Structure Shift (MSS ▾)" in case_study_short["body"]
    assert "Bearish Supply Order Block (-OB)" in case_study_short["body"]

    res = publish_reddit_case_study(case_study_long)
    assert res["status"] in ("DRAFT_SAVED", "PUBLISHED", "COOLDOWN_ACTIVE")
    assert "url" in res
    assert Path(res["url"]).exists() or res["url"].startswith("http")


def test_channel_signal_message_directional_ict():
    from market_scanner import format_channel_signal_message

    sig_short = {
        "pair": "EURUSD",
        "direction": "SHORT",
        "entry": 1.08500,
        "stop_loss": 1.08720,
        "take_profit": 1.08150,
        "sl_pips": 22.0,
        "tp_pips": 35.0,
        "rr": 1.59,
        "timeframe": "15M"
    }
    msg_short = format_channel_signal_message(sig_short)
    assert "Sell-Side Liquidity (SSL)" in msg_short

    sig_long = {
        "pair": "USDCAD",
        "direction": "LONG",
        "entry": 1.38500,
        "stop_loss": 1.38280,
        "take_profit": 1.38850,
        "sl_pips": 22.0,
        "tp_pips": 35.0,
        "rr": 1.59,
        "timeframe": "15M"
    }
    msg_long = format_channel_signal_message(sig_long)
    assert "Buy-Side Liquidity (BSL)" in msg_long


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


def test_contents_bot_commands(monkeypatch):
    from core.marketing.contents_bot import handle_contents_bot_update

    messages_sent = []
    photos_sent = []

    def mock_msg(chat_id, text, reply_markup=None, bot_token=None):
        messages_sent.append({"chat_id": chat_id, "text": text, "markup": reply_markup, "token": bot_token})
        return True

    def mock_photo(chat_id, photo_bytes, caption="", reply_markup=None, bot_token=None):
        photos_sent.append({"chat_id": chat_id, "caption": caption, "token": bot_token})
        return True

    monkeypatch.setattr("core.marketing.contents_bot.send_contents_message", mock_msg)
    monkeypatch.setattr("core.marketing.contents_bot.send_contents_photo", mock_photo)
    monkeypatch.setattr("core.marketing.contents_bot.TELEGRAM_CHAT_ID", "8142877259")

    # 1. Test /start
    res_start = handle_contents_bot_update({"message": {"chat": {"id": "8142877259"}, "text": "/start"}})
    assert res_start is True
    assert len(messages_sent) == 1
    assert "QUANTFLOW CONTENTS COCKPIT" in messages_sent[0]["text"]
    assert messages_sent[0]["markup"] is not None
    assert "remove_keyboard" in messages_sent[0]["markup"]  # Clean text bar enforced!

    # 2. Test /signal (when no active trade -> cleanly states no active trades identified)
    res_sig = handle_contents_bot_update({"message": {"chat": {"id": "8142877259"}, "text": "/signal"}})
    assert res_sig is True
    assert any("NO ACTIVE TRADES" in m["text"] or "VERIFIED ACTIVE TRADE" in m["text"] for m in messages_sent)

    # 3. Test /twitter (generates high-value content with real chart)
    res_tw = handle_contents_bot_update({"message": {"chat": {"id": "8142877259"}, "text": "/twitter"}})
    assert res_tw is True
    assert any("TWITTER / X" in m["text"] for m in messages_sent)

    # 4. Test /reddit (generates in-depth post with real chart)
    res_rd = handle_contents_bot_update({"message": {"chat": {"id": "8142877259"}, "text": "/reddit"}})
    assert res_rd is True
    assert any("REDDIT" in m["text"] for m in messages_sent)

    # 5. Test /chart
    res_ch = handle_contents_bot_update({"message": {"chat": {"id": "8142877259"}, "text": "/chart EURUSD"}})
    assert res_ch is True
    assert len(photos_sent) >= 1
    assert "REAL MARKET CHART" in photos_sent[-1]["caption"]


def test_contents_bot_callback_queries(monkeypatch):
    from core.marketing.contents_bot import handle_contents_bot_update

    messages_sent = []

    def mock_msg(chat_id, text, reply_markup=None, bot_token=None):
        messages_sent.append({"chat_id": chat_id, "text": text, "markup": reply_markup, "token": bot_token})
        return True

    monkeypatch.setattr("core.marketing.contents_bot.send_contents_message", mock_msg)
    monkeypatch.setattr("core.marketing.contents_bot.answer_callback", lambda *a, **k: True)

    cb_update = {
        "callback_query": {
            "id": "cb123",
            "from": {"id": 8142877259},
            "message": {"chat": {"id": 8142877259}},
            "data": "btn_tw_EURUSD"
        }
    }
    res = handle_contents_bot_update(cb_update)
    assert res is True
    assert any("TWITTER / X" in m["text"] for m in messages_sent)


def test_dispatch_social_media_pack(monkeypatch):
    from market_scanner import dispatch_social_media_pack
    alerts = []
    photos = []

    def mock_msg(chat_id, text, reply_markup=None, bot_token=None):
        alerts.append({"text": text, "chat_id": chat_id, "token": bot_token})
        return True

    def mock_photo(chat_id, photo_bytes, caption="", reply_markup=None, bot_token=None):
        photos.append({"caption": caption, "chat_id": chat_id, "token": bot_token})
        return True

    monkeypatch.setattr("core.marketing.contents_bot.send_contents_message", mock_msg)
    monkeypatch.setattr("core.marketing.contents_bot.send_contents_photo", mock_photo)
    monkeypatch.setattr("core.marketing.contents_bot.TELEGRAM_CHAT_ID", "8142877259")

    trade = {
        "pair": "EURUSD",
        "direction": "SHORT",
        "entry": 1.08500,
        "stop_loss": 1.08750,
        "take_profit": 1.08125,
        "timeframe": "15M"
    }

    res = dispatch_social_media_pack(trade, realized_pips=37.5, realized_r=1.50)
    assert res is True
    assert len(photos) >= 1  # Chart photo sent
    assert len(alerts) >= 1  # Master Social Hub sent
    assert "CONTENTS HUB" in alerts[0]["text"]
    assert "TWITTER / X THREAD" in alerts[0]["text"]
    assert "REDDIT CASE STUDY" in alerts[0]["text"]
    # Ensure all alerts are routed strictly to the Contents Bot!
    for a in alerts:
        assert "9196801543" in str(a["token"])


def test_ai_content_generator():
    from core.marketing.ai_content_generator import (
        generate_ai_twitter_educational_thread,
        generate_ai_reddit_educational_post
    )

    tw = generate_ai_twitter_educational_thread(topic_idx=0)
    assert "tweets" in tw
    assert len(tw["tweets"]) == 3
    assert "topic" in tw
    assert "pair" in tw

    rd = generate_ai_reddit_educational_post(topic_idx=0)
    assert "title" in rd
    assert "body" in rd
    assert "subreddit" in rd
    assert "pair" in rd

