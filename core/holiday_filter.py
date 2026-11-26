"""Institutional Bank Holiday & Liquidity Freeze Defense Filter.

Suppresses new signal entries during major interbank holidays (Thanksgiving, Christmas,
New Year, Good Friday, Memorial Day, Labor Day, etc.) when Tier-1 liquidity providers
(JPMorgan, Citibank, Deutsche Bank, Barclays) are offline.

Prevents entering trades during erratic holiday drift, wide spreads, and false breakouts.
Existing positions continue to be monitored and protected by Stop Loss.
"""

import calendar
import datetime
import logging
import os
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("HolidayFilter")

# Configurable environment controls
HOLIDAY_FILTER_ENABLED = os.environ.get("HOLIDAY_FILTER_ENABLED", "true").lower() in ("true", "1", "yes")
ALLOW_HOLIDAY_TRADING = os.environ.get("ALLOW_HOLIDAY_TRADING", "false").lower() in ("true", "1", "yes")


def get_easter(year: int) -> datetime.date:
    """Calculate Easter Sunday using the Meeus/Jones/Butcher algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)


def get_nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> datetime.date:
    """Get the n-th occurrence of a weekday in a given month (weekday: 0=Mon, 6=Sun; n: 1-indexed)."""
    first_day = datetime.date(year, month, 1)
    first_weekday = first_day.weekday()
    day_offset = (weekday - first_weekday) % 7
    first_matching_day = 1 + day_offset
    return datetime.date(year, month, first_matching_day + (n - 1) * 7)


def get_last_weekday_of_month(year: int, month: int, weekday: int) -> datetime.date:
    """Get the last occurrence of a weekday in a given month (weekday: 0=Mon, 6=Sun)."""
    last_day = calendar.monthrange(year, month)[1]
    d = datetime.date(year, month, last_day)
    while d.weekday() != weekday:
        d -= datetime.timedelta(days=1)
    return d


def get_institutional_holidays(year: int) -> Dict[datetime.date, str]:
    """Generate institutional bank holidays and liquidity freeze dates for a given year.

    Covers US Federal Reserve bank holidays, UK/EU major banking holidays,
    and the annual year-end interbank liquidity freeze period.
    """
    holidays: Dict[datetime.date, str] = {}

    # 1. New Year's Day (Jan 1, observed Jan 2 if Sun)
    ny_day = datetime.date(year, 1, 1)
    if ny_day.weekday() == 6:  # Sunday
        holidays[datetime.date(year, 1, 2)] = "New Year's Day (Observed)"
    else:
        holidays[ny_day] = "New Year's Day"

    # 2. Martin Luther King Jr. Day (US: 3rd Monday of Jan)
    mlk = get_nth_weekday_of_month(year, 1, 0, 3)
    holidays[mlk] = "Martin Luther King Jr. Day (US Bank Holiday)"

    # 3. Presidents' Day / Washington's Birthday (US: 3rd Monday of Feb)
    presidents = get_nth_weekday_of_month(year, 2, 0, 3)
    holidays[presidents] = "Presidents' Day (US Bank Holiday)"

    # 4. Easter Holidays (Global Interbank)
    easter_sun = get_easter(year)
    good_friday = easter_sun - datetime.timedelta(days=2)
    easter_monday = easter_sun + datetime.timedelta(days=1)
    holidays[good_friday] = "Good Friday (Global Bank Holiday)"
    holidays[easter_monday] = "Easter Monday (UK / European Bank Holiday)"

    # 5. Memorial Day (US: Last Monday of May)
    memorial = get_last_weekday_of_month(year, 5, 0)
    holidays[memorial] = "Memorial Day (US Bank Holiday)"

    # 6. Juneteenth National Independence Day (US: June 19)
    juneteenth = datetime.date(year, 6, 19)
    if juneteenth.weekday() == 6:  # Sunday
        holidays[datetime.date(year, 6, 20)] = "Juneteenth (Observed)"
    elif juneteenth.weekday() == 5:  # Saturday
        holidays[datetime.date(year, 6, 18)] = "Juneteenth (Observed)"
    else:
        holidays[juneteenth] = "Juneteenth (US Bank Holiday)"

    # 7. US Independence Day (US: July 4)
    july4 = datetime.date(year, 7, 4)
    if july4.weekday() == 6:
        holidays[datetime.date(year, 7, 5)] = "US Independence Day (Observed)"
    elif july4.weekday() == 5:
        holidays[datetime.date(year, 7, 3)] = "US Independence Day (Observed)"
    else:
        holidays[july4] = "US Independence Day (US Bank Holiday)"

    # 8. Labor Day (US: 1st Monday of September)
    labor = get_nth_weekday_of_month(year, 9, 0, 1)
    holidays[labor] = "Labor Day (US Bank Holiday)"

    # 9. Thanksgiving Day (US: 4th Thursday of November)
    thanksgiving = get_nth_weekday_of_month(year, 11, 3, 4)
    holidays[thanksgiving] = "US Thanksgiving Day (US Bank Holiday)"

    # 10. Day after Thanksgiving / Black Friday (US: Institutional Half-Day / Deserted Desks)
    black_friday = thanksgiving + datetime.timedelta(days=1)
    holidays[black_friday] = "Day after Thanksgiving / Black Friday (Thin Interbank Liquidity)"

    # 11. Christmas Eve through Year-End Interbank Freeze (Dec 24 - Dec 31)
    # Tier-1 investment banks completely wind down FX trading desks during this period
    for day in range(24, 32):
        d = datetime.date(year, 12, day)
        if day == 24:
            holidays[d] = "Christmas Eve (Interbank Early Close)"
        elif day == 25:
            holidays[d] = "Christmas Day (Global Bank Holiday)"
        elif day == 26:
            holidays[d] = "Boxing Day (UK / European Bank Holiday)"
        else:
            holidays[d] = f"Year-End Interbank Liquidity Freeze (Dec {day})"

    return holidays


def is_institutional_holiday(
    dt: Optional[datetime.datetime] = None,
    pair: Optional[str] = None
) -> Tuple[bool, str]:
    """Check if the provided datetime falls on a major institutional bank holiday or liquidity freeze.

    Args:
        dt: Datetime to check (defaults to current UTC time).
        pair: Optional pair symbol (e.g. 'EURUSD', 'USDCAD').

    Returns:
        Tuple of (is_holiday: bool, reason: str).
    """
    if not HOLIDAY_FILTER_ENABLED or ALLOW_HOLIDAY_TRADING:
        return False, ""

    if dt is None:
        dt = datetime.datetime.now(datetime.timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)

    d = dt.date()
    holidays = get_institutional_holidays(d.year)

    # 1. Deterministic Interbank Holiday Calendar Check
    if d in holidays:
        return True, holidays[d]

    # Check year boundary (e.g. Dec 31 / Jan 1 boundary)
    if d.month == 1:
        prev_holidays = get_institutional_holidays(d.year - 1)
        if d in prev_holidays:
            return True, prev_holidays[d]

    # 2. Live Economic Calendar Feed Check (Forex Factory)
    try:
        from core.news_filter import fetch_economic_calendar, parse_event_time
        cal = fetch_economic_calendar()
        target_currencies = {"USD", "EUR", "GBP", "ALL"}
        if pair:
            clean = pair.replace("=X", "").upper()
            if len(clean) >= 6:
                target_currencies.update({clean[:3], clean[3:6]})

        for ev in cal:
            impact = str(ev.get("impact") or "")
            title = str(ev.get("title") or "")
            country = str(ev.get("country") or "").upper()
            if impact.lower() == "holiday" or "bank holiday" in title.lower():
                if country in target_currencies:
                    date_raw = ev.get("date")
                    if date_raw:
                        ev_dt = parse_event_time(date_raw)
                        if ev_dt and ev_dt.date() == d:
                            return True, f"{country} Bank Holiday: {title}"
    except Exception as ex:
        logger.debug(f"Calendar holiday check notice: {ex}")

    return False, ""
