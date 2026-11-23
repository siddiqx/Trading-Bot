"""Unit Tests for core.news_filter (Forex Factory High-Impact Economic News Filter)."""

import pytest
from datetime import datetime, timezone, timedelta
from core.news_filter import parse_event_time, is_news_window_active


def test_parse_event_time():
    """Verify ISO 8601 parsing handles offsets and converts to UTC."""
    raw_str = "2026-11-04T14:30:00-05:00"
    dt = parse_event_time(raw_str)
    assert dt is not None
    assert dt.tzinfo is not None
    # 14:30 at UTC-5 is 19:30 UTC
    assert dt.hour == 19
    assert dt.minute == 30


def test_news_window_active_match():
    """Verify active news suppression when a high-impact event is within buffer window."""
    now_utc = datetime(2026, 11, 4, 13, 30, tzinfo=timezone.utc)
    mock_events = [
        {
            "title": "Non-Farm Employment Change",
            "country": "USD",
            "date": "2026-11-04T13:45:00Z",  # 15 minutes away
            "impact": "High"
        },
        {
            "title": "Low impact CPI sub-component",
            "country": "EUR",
            "date": "2026-11-04T13:30:00Z",
            "impact": "Low"
        }
    ]

    # EURUSD should be suppressed because USD has High-Impact event in 15 min
    is_active, reason = is_news_window_active("EURUSD", now_utc=now_utc, buffer_minutes=30, events=mock_events)
    assert is_active is True
    assert "Non-Farm" in reason
    assert "USD" in reason


def test_news_window_inactive_outside_buffer():
    """Verify trades are permitted when news is beyond the 30-minute buffer."""
    now_utc = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    mock_events = [
        {
            "title": "FOMC Rate Decision",
            "country": "USD",
            "date": "2026-11-04T18:00:00Z",  # 6 hours away
            "impact": "High"
        }
    ]

    is_active, reason = is_news_window_active("EURUSD", now_utc=now_utc, buffer_minutes=30, events=mock_events)
    assert is_active is False
    assert reason == ""


def test_news_window_inactive_unrelated_currency():
    """Verify news on unrelated currency (e.g. JPY) does not block EURUSD."""
    now_utc = datetime(2026, 11, 4, 13, 30, tzinfo=timezone.utc)
    mock_events = [
        {
            "title": "BOJ Monetary Policy Statement",
            "country": "JPY",
            "date": "2026-11-04T13:35:00Z",  # 5 minutes away
            "impact": "High"
        }
    ]

    # EURUSD has EUR and USD, not JPY
    is_active_eurusd, _ = is_news_window_active("EURUSD", now_utc=now_utc, buffer_minutes=30, events=mock_events)
    assert is_active_eurusd is False

    # USDJPY includes JPY, so it MUST be suppressed
    is_active_usdjpy, reason = is_news_window_active("USDJPY", now_utc=now_utc, buffer_minutes=30, events=mock_events)
    assert is_active_usdjpy is True
    assert "BOJ" in reason


def test_flash_pmi_medium_impact_blocks_pair():
    """Verify Flash PMI with Medium impact blocks trading within the 45-minute buffer."""
    # French Flash Manufacturing PMI is at 08:15 UTC on Nov 23, 2026.
    # At 07:32 UTC (43 mins before release), EURUSD must be protected.
    now_utc = datetime(2026, 11, 23, 7, 32, tzinfo=timezone.utc)
    mock_events = [
        {
            "title": "French Flash Manufacturing PMI",
            "country": "EUR",
            "date": "2026-11-23T08:15:00Z",
            "impact": "Medium"
        }
    ]

    is_active, reason = is_news_window_active("EURUSD", now_utc=now_utc, buffer_minutes=30, events=mock_events)
    assert is_active is True
    assert "Flash PMI Release" in reason
    assert "French Flash Manufacturing PMI" in reason
    assert "EUR" in reason
    assert "43m" in reason


def test_flash_pmi_high_impact_blocks_pair():
    """Verify Flash PMI with High impact blocks trading and retains High-Impact label."""
    now_utc = datetime(2026, 11, 23, 8, 0, tzinfo=timezone.utc)
    mock_events = [
        {
            "title": "German Flash Services PMI",
            "country": "EUR",
            "date": "2026-11-23T08:30:00Z",
            "impact": "High"
        }
    ]

    is_active, reason = is_news_window_active("EURUSD", now_utc=now_utc, buffer_minutes=30, events=mock_events)
    assert is_active is True
    assert "High-Impact News" in reason
    assert "German Flash Services PMI" in reason
    assert "30m" in reason


def test_flash_pmi_outside_buffer_permits_trade():
    """Verify trades are permitted when Flash PMI is beyond the 45-minute buffer."""
    # At 07:00 UTC (75 minutes before 08:15 UTC release), trading is permitted.
    now_utc = datetime(2026, 11, 23, 7, 0, tzinfo=timezone.utc)
    mock_events = [
        {
            "title": "French Flash Manufacturing PMI",
            "country": "EUR",
            "date": "2026-11-23T08:15:00Z",
            "impact": "Medium"
        }
    ]

    is_active, reason = is_news_window_active("EURUSD", now_utc=now_utc, buffer_minutes=30, events=mock_events)
    assert is_active is False
    assert reason == ""


def test_flash_pmi_unrelated_currency_permits_trade():
    """Verify EUR Flash PMI does not suppress USDCAD trading."""
    now_utc = datetime(2026, 11, 23, 7, 45, tzinfo=timezone.utc)
    mock_events = [
        {
            "title": "French Flash Services PMI",
            "country": "EUR",
            "date": "2026-11-23T08:15:00Z",
            "impact": "Medium"
        }
    ]

    is_active, reason = is_news_window_active("USDCAD", now_utc=now_utc, buffer_minutes=30, events=mock_events)
    assert is_active is False
    assert reason == ""


def test_regular_medium_and_low_impact_events_ignored():
    """Verify standard Medium and Low impact non-Flash-PMI events are never blocked, preserving 100% normal trade frequency."""
    now_utc = datetime(2026, 11, 23, 13, 30, tzinfo=timezone.utc)
    mock_events = [
        {
            "title": "Retail Sales m/m",
            "country": "USD",
            "date": "2026-11-23T13:30:00Z",
            "impact": "Medium"
        },
        {
            "title": "Final Manufacturing PMI",
            "country": "EUR",
            "date": "2026-11-23T13:30:00Z",
            "impact": "Medium"
        },
        {
            "title": "Consumer Sentiment Index",
            "country": "USD",
            "date": "2026-11-23T13:35:00Z",
            "impact": "Low"
        },
        {
            "title": "Wholesale Inventories",
            "country": "USD",
            "date": "2026-11-23T13:40:00Z",
            "impact": "Low"
        }
    ]

    for pair in ["EURUSD", "USDCAD", "USDCHF", "AUDUSD"]:
        is_active, reason = is_news_window_active(pair, now_utc=now_utc, buffer_minutes=30, events=mock_events)
        assert is_active is False, f"Expected {pair} to be active, but blocked by {reason}"
        assert reason == ""
