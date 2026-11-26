"""Unit Tests for Institutional Bank Holiday & Liquidity Freeze Filter."""

import datetime
from unittest.mock import patch
import pytest

from core.holiday_filter import (
    get_easter,
    get_nth_weekday_of_month,
    get_last_weekday_of_month,
    get_institutional_holidays,
    is_institutional_holiday,
)


def test_easter_and_good_friday():
    """Verify Meeus/Jones/Butcher algorithm across multiple known years."""
    # 2024: Easter is March 31
    assert get_easter(2024) == datetime.date(2024, 3, 31)
    # 2025: Easter is April 20
    assert get_easter(2025) == datetime.date(2025, 4, 20)
    # 2026: Easter is April 5
    assert get_easter(2026) == datetime.date(2026, 4, 5)

    holidays_2026 = get_institutional_holidays(2026)
    assert datetime.date(2026, 4, 3) in holidays_2026  # Good Friday
    assert "Good Friday" in holidays_2026[datetime.date(2026, 4, 3)]


def test_thanksgiving_and_black_friday():
    """Verify US Thanksgiving and Black Friday calculations."""
    holidays_2026 = get_institutional_holidays(2026)
    thanksgiving_2026 = datetime.date(2026, 11, 26)
    black_friday_2026 = datetime.date(2026, 11, 27)

    assert thanksgiving_2026 in holidays_2026
    assert "Thanksgiving" in holidays_2026[thanksgiving_2026]

    assert black_friday_2026 in holidays_2026
    assert "Black Friday" in holidays_2026[black_friday_2026]


def test_year_end_interbank_freeze():
    """Verify Dec 24 - Dec 31 interbank liquidity freeze."""
    holidays_2026 = get_institutional_holidays(2026)
    for day in range(24, 32):
        d = datetime.date(2026, 12, day)
        assert d in holidays_2026, f"Dec {day} must be flagged as holiday freeze"


def test_is_institutional_holiday_detection():
    """Verify is_institutional_holiday detects Thanksgiving and allows regular days."""
    with patch.dict("os.environ", {"HOLIDAY_FILTER_ENABLED": "true", "ALLOW_HOLIDAY_TRADING": "false"}):
        # Thanksgiving 2026
        dt_thanksgiving = datetime.datetime(2026, 11, 26, 14, 0, tzinfo=datetime.timezone.utc)
        is_h, reason = is_institutional_holiday(dt_thanksgiving)
        assert is_h is True
        assert "Thanksgiving" in reason

        # Black Friday 2026
        dt_black_friday = datetime.datetime(2026, 11, 27, 10, 0, tzinfo=datetime.timezone.utc)
        is_h, reason = is_institutional_holiday(dt_black_friday)
        assert is_h is True
        assert "Black Friday" in reason

        # Normal Wednesday 2026
        dt_normal = datetime.datetime(2026, 11, 25, 10, 0, tzinfo=datetime.timezone.utc)
        is_h, reason = is_institutional_holiday(dt_normal)
        assert is_h is False
        assert reason == ""


def test_allow_holiday_trading_override():
    """Verify ALLOW_HOLIDAY_TRADING override bypasses the holiday filter."""
    with patch("core.holiday_filter.ALLOW_HOLIDAY_TRADING", True):
        dt_thanksgiving = datetime.datetime(2026, 11, 26, 14, 0, tzinfo=datetime.timezone.utc)
        is_h, reason = is_institutional_holiday(dt_thanksgiving)
        assert is_h is False
        assert reason == ""
