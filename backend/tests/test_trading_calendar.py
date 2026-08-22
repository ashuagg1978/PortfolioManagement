from datetime import date

from services.trading_calendar import is_trading_day, is_weekend, next_trading_day


def test_weekend_detection():
    assert is_weekend(date(2024, 1, 6))  # Saturday
    assert is_weekend(date(2024, 1, 7))  # Sunday
    assert not is_weekend(date(2024, 1, 8))  # Monday


def test_saturday_rolls_to_monday():
    saturday = date(2024, 1, 6)
    assert next_trading_day(saturday, holidays=set()) == date(2024, 1, 8)


def test_holiday_rolls_to_next_trading_day():
    holidays = {date(2024, 8, 15)}  # Independence Day, a Thursday
    assert next_trading_day(date(2024, 8, 15), holidays) == date(2024, 8, 16)


def test_holiday_immediately_before_weekend_rolls_past_both():
    # Friday holiday should roll to the following Monday.
    holidays = {date(2024, 3, 29)}  # Good Friday
    assert next_trading_day(date(2024, 3, 29), holidays) == date(2024, 4, 1)


def test_already_a_trading_day_is_unchanged():
    assert next_trading_day(date(2024, 1, 8), holidays=set()) == date(2024, 1, 8)


def test_is_trading_day_false_on_weekend_and_holiday():
    holidays = {date(2024, 8, 15)}
    assert not is_trading_day(date(2024, 1, 6), holidays)  # Saturday
    assert not is_trading_day(date(2024, 8, 15), holidays)  # holiday
    assert is_trading_day(date(2024, 8, 16), holidays)
