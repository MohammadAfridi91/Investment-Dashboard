from datetime import date

from core.utils.trading_calendar import (
    is_trading_day,
    last_n_trading_days,
    next_trading_day,
    prev_trading_day,
)

HOL = {date(2026, 1, 26), date(2026, 3, 3)}


def test_weekend_not_trading():
    assert not is_trading_day(date(2026, 1, 24), HOL)
    assert not is_trading_day(date(2026, 1, 25), HOL)


def test_holiday_not_trading():
    assert not is_trading_day(date(2026, 1, 26), HOL)


def test_regular_day_is_trading():
    assert is_trading_day(date(2026, 1, 27), HOL)


def test_prev_next_skip_holiday():
    assert next_trading_day(date(2026, 1, 23), HOL) == date(2026, 1, 27)
    assert prev_trading_day(date(2026, 1, 27), HOL) == date(2026, 1, 23)


def test_last_n_trading_days_excludes_holidays():
    days = last_n_trading_days(date(2026, 1, 30), 5, HOL)
    assert len(days) == 5
    assert date(2026, 1, 26) not in days
