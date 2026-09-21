from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any


class ValidationError(Exception):
    pass


def require_positive(value: Any, field: str) -> float:
    try:
        val = float(value)
    except (TypeError, ValueError) as err:
        raise ValidationError(f"{field} not numeric: {value!r}") from err
    if val < 0:
        raise ValidationError(f"{field} negative: {val}")
    return val


def require_ohlc_consistency(
    open_val: float,
    high_val: float,
    low_val: float,
    close_val: float,
    field_prefix: str = "",
) -> None:
    for name, v in (("open", open_val), ("high", high_val), ("low", low_val), ("close", close_val)):
        if v is None or v < 0:
            raise ValidationError(f"{field_prefix}{name} invalid: {v!r}")
    if high_val < max(open_val, close_val, low_val):
        raise ValidationError(f"{field_prefix}high {high_val} < max(o,c,l)")
    if low_val > min(open_val, close_val, high_val):
        raise ValidationError(f"{field_prefix}low {low_val} > min(o,c,h)")


def validate_ohlc(row: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    o, h, low_val, c = (
        float(row["open_price"]),
        float(row["high_price"]),
        float(row["low_price"]),
        float(row["close_price"]),
    )
    if not (low_val <= o <= h):
        errs.append("open outside [low, high]")
    if not (low_val <= c <= h):
        errs.append("close outside [low, high]")
    if int(row.get("volume", 0)) < 0:
        errs.append("negative volume")
    if int(row.get("delivery_qty", 0)) > int(row.get("volume", 0)):
        errs.append("delivery > volume")
    if float(row.get("prev_close", 0)) <= 0:
        errs.append("non-positive prev_close")
    return errs


def validate_symbol_in_universe(symbol: str, universe_symbols: set[str]) -> bool:
    return symbol in universe_symbols


def validate_trading_day(d: date, holidays: Iterable[date]) -> bool:
    from core.utils.trading_calendar import is_trading_day

    return is_trading_day(d, holidays)


def ensure_not_future(d: date, today: date | None = None) -> None:
    today_date = today or date.today()
    if d > today_date:
        raise ValidationError(f"date {d} is in the future")
