"""Pure SIP occurrence generation - no DB access, directly unit-testable.

scheduled_date is the RAW, unadjusted calendar date and is what the
idempotency key (Transaction.sip_scheduled_date) is built from - so if a
holiday gets added or removed from the calendar later, previously generated
occurrences keep the same identity even though their adjusted_date might
shift. adjusted_date is what's shown to the user as the actual due date.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from models.enums import SipFrequency
from services.trading_calendar import next_trading_day


@dataclass(frozen=True, slots=True)
class SipOccurrence:
    scheduled_date: date
    adjusted_date: date
    calendar_complete: bool  # False if scheduled_date's year has no seeded holiday data


def _monthly_dates(start: date, end: date) -> list[date]:
    """Clamps to month-end: a start day of 31 becomes the 30th (or 28th/29th
    in February) in any month shorter than 31 days.
    """
    dates: list[date] = []
    year, month, day = start.year, start.month, start.day
    while True:
        last_day = calendar.monthrange(year, month)[1]
        d = date(year, month, min(day, last_day))
        if d > end:
            break
        dates.append(d)
        month += 1
        if month == 13:
            month = 1
            year += 1
    return dates


def _biweekly_dates(start: date, end: date) -> list[date]:
    dates: list[date] = []
    d = start
    while d <= end:
        dates.append(d)
        d += timedelta(days=14)
    return dates


def generate_schedule(
    *,
    frequency: str,
    start_date: date,
    end_date: date | None,
    until: date,
    holidays: set[date],
    years_with_calendar: set[int],
) -> list[SipOccurrence]:
    """All occurrences from start_date through min(end_date or until, until).
    end_date is None for a perpetual SIP.
    """
    effective_end = min(end_date, until) if end_date is not None else until
    if start_date > effective_end:
        return []

    if frequency == SipFrequency.MONTHLY:
        raw_dates = _monthly_dates(start_date, effective_end)
    elif frequency == SipFrequency.BIWEEKLY:
        raw_dates = _biweekly_dates(start_date, effective_end)
    else:
        raise ValueError(f"Unknown SIP frequency: {frequency!r}")

    return [
        SipOccurrence(
            scheduled_date=d,
            adjusted_date=next_trading_day(d, holidays),
            calendar_complete=d.year in years_with_calendar,
        )
        for d in raw_dates
    ]
