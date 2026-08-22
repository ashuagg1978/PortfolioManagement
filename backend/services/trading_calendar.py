"""Trading-day adjustment for SIP scheduling.

The core logic is pure (just weekday + a holiday set) so it's directly
unit-testable; load_holidays is the thin DB-facing wrapper that pulls the
holiday set from market_holidays (seeded from app/data/nse_holidays.json -
see scripts/seed.py).

If a given year has no holiday rows at all, adjustment degrades to
weekend-only - has_calendar_for_year lets a caller detect that and warn
rather than silently produce a date that might be off by a day or two
around an unseeded holiday.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from models.market_holiday import MarketHoliday


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # 5=Saturday, 6=Sunday


def is_trading_day(d: date, holidays: set[date]) -> bool:
    return not is_weekend(d) and d not in holidays


def next_trading_day(d: date, holidays: set[date]) -> date:
    candidate = d
    while is_weekend(candidate) or candidate in holidays:
        candidate += timedelta(days=1)
    return candidate


def load_holidays(db: Session) -> set[date]:
    return {h.holiday_date for h in db.query(MarketHoliday.holiday_date).all()}


def has_calendar_for_year(db: Session, year: int) -> bool:
    return (
        db.query(MarketHoliday)
        .filter(MarketHoliday.holiday_date >= date(year, 1, 1))
        .filter(MarketHoliday.holiday_date <= date(year, 12, 31))
        .first()
        is not None
    )
