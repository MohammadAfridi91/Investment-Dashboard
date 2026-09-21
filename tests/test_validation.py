from datetime import date

import pytest

from core.utils.validation import (
    ValidationError,
    ensure_not_future,
    require_ohlc_consistency,
    require_positive,
    validate_ohlc,
    validate_symbol_in_universe,
    validate_trading_day,
)


def test_require_positive() -> None:
    assert require_positive(10.5, "price") == 10.5
    with pytest.raises(ValidationError):
        require_positive(-1, "price")
    with pytest.raises(ValidationError):
        require_positive("abc", "price")


def test_require_ohlc_consistency() -> None:
    require_ohlc_consistency(100.0, 110.0, 90.0, 105.0)
    with pytest.raises(ValidationError):
        require_ohlc_consistency(100.0, 95.0, 90.0, 105.0)  # high < max
    with pytest.raises(ValidationError):
        require_ohlc_consistency(100.0, 110.0, 102.0, 105.0)  # low > min


def test_validate_ohlc_clean_and_malformed() -> None:
    clean_row = {
        "open_price": 100.0,
        "high_price": 105.0,
        "low_price": 99.0,
        "close_price": 102.0,
        "volume": 1000,
        "delivery_qty": 500,
        "prev_close": 98.0,
    }
    assert validate_ohlc(clean_row) == []

    bad_row = {
        "open_price": 110.0,  # outside high
        "high_price": 105.0,
        "low_price": 99.0,
        "close_price": 102.0,
        "volume": -50,
        "delivery_qty": 100,
        "prev_close": -1.0,
    }
    errs = validate_ohlc(bad_row)
    assert len(errs) >= 3


def test_validate_symbol_and_trading_day() -> None:
    assert validate_symbol_in_universe("TCS", {"TCS", "INFY"})
    assert not validate_symbol_in_universe("WIPRO", {"TCS", "INFY"})

    holidays = {date(2026, 1, 26)}
    assert validate_trading_day(date(2026, 1, 27), holidays)
    assert not validate_trading_day(date(2026, 1, 26), holidays)


def test_ensure_not_future() -> None:
    ensure_not_future(date(2020, 1, 1), today=date(2026, 1, 1))
    with pytest.raises(ValidationError):
        ensure_not_future(date(2030, 1, 1), today=date(2026, 1, 1))
