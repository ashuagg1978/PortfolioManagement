from datetime import date

from models.enums import SipFrequency
from services.sip_schedule import generate_schedule


def test_monthly_jan_31_clamps_across_non_leap_february():
    occurrences = generate_schedule(
        frequency=SipFrequency.MONTHLY,
        start_date=date(2025, 1, 31),
        end_date=None,
        until=date(2025, 4, 30),
        holidays=set(),
        years_with_calendar={2025},
    )
    scheduled = [o.scheduled_date for o in occurrences]
    assert scheduled == [date(2025, 1, 31), date(2025, 2, 28), date(2025, 3, 31), date(2025, 4, 30)]


def test_monthly_jan_31_clamps_across_leap_february():
    occurrences = generate_schedule(
        frequency=SipFrequency.MONTHLY,
        start_date=date(2024, 1, 31),
        end_date=None,
        until=date(2024, 2, 29),
        holidays=set(),
        years_with_calendar={2024},
    )
    assert [o.scheduled_date for o in occurrences] == [date(2024, 1, 31), date(2024, 2, 29)]


def test_saturday_occurrence_rolls_to_monday():
    # 6 Jan 2024 is a Saturday.
    occurrences = generate_schedule(
        frequency=SipFrequency.MONTHLY,
        start_date=date(2024, 1, 6),
        end_date=None,
        until=date(2024, 1, 6),
        holidays=set(),
        years_with_calendar={2024},
    )
    assert occurrences[0].scheduled_date == date(2024, 1, 6)
    assert occurrences[0].adjusted_date == date(2024, 1, 8)


def test_known_holiday_rolls_forward():
    occurrences = generate_schedule(
        frequency=SipFrequency.MONTHLY,
        start_date=date(2024, 8, 15),
        end_date=None,
        until=date(2024, 8, 15),
        holidays={date(2024, 8, 15)},
        years_with_calendar={2024},
    )
    assert occurrences[0].adjusted_date == date(2024, 8, 16)


def test_biweekly_spans_year_boundary():
    occurrences = generate_schedule(
        frequency=SipFrequency.BIWEEKLY,
        start_date=date(2024, 12, 20),
        end_date=None,
        until=date(2025, 1, 20),
        holidays=set(),
        years_with_calendar={2024, 2025},
    )
    scheduled = [o.scheduled_date for o in occurrences]
    assert scheduled == [date(2024, 12, 20), date(2025, 1, 3), date(2025, 1, 17)]


def test_perpetual_sip_has_no_end_date_bound():
    occurrences = generate_schedule(
        frequency=SipFrequency.MONTHLY,
        start_date=date(2024, 1, 1),
        end_date=None,
        until=date(2024, 3, 1),
        holidays=set(),
        years_with_calendar={2024},
    )
    # bounded only by `until`, not by any end_date
    assert len(occurrences) == 3


def test_end_date_before_until_stops_early():
    occurrences = generate_schedule(
        frequency=SipFrequency.MONTHLY,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 2, 15),
        until=date(2024, 6, 1),
        holidays=set(),
        years_with_calendar={2024},
    )
    assert [o.scheduled_date for o in occurrences] == [date(2024, 1, 1), date(2024, 2, 1)]


def test_start_after_until_returns_empty():
    occurrences = generate_schedule(
        frequency=SipFrequency.MONTHLY,
        start_date=date(2025, 1, 1),
        end_date=None,
        until=date(2024, 1, 1),
        holidays=set(),
        years_with_calendar={2024},
    )
    assert occurrences == []


def test_calendar_complete_flag_reflects_seeded_years():
    occurrences = generate_schedule(
        frequency=SipFrequency.MONTHLY,
        start_date=date(2030, 1, 1),
        end_date=None,
        until=date(2030, 1, 1),
        holidays=set(),
        years_with_calendar={2024},  # 2030 not seeded
    )
    assert occurrences[0].calendar_complete is False
