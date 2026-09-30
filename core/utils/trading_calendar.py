from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta, timezone

# India has no DST; a fixed offset avoids a tzdata dependency on minimal runners.
IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def today_ist(now: datetime | None = None) -> date:
    """Current calendar date in India (exchange time), not UTC."""
    return (now or datetime.now(UTC)).astimezone(IST).date()


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def is_trading_day(d: date, holidays: Iterable[date]) -> bool:
    if is_weekend(d):
        return False
    return d not in set(holidays)


def prev_trading_day(d: date, holidays: Iterable[date]) -> date:
    cur = d - timedelta(days=1)
    while not is_trading_day(cur, holidays):
        cur -= timedelta(days=1)
    return cur


def next_trading_day(d: date, holidays: Iterable[date]) -> date:
    cur = d + timedelta(days=1)
    while not is_trading_day(cur, holidays):
        cur += timedelta(days=1)
    return cur


def last_n_trading_days(end: date, n: int, holidays: Iterable[date]) -> list[date]:
    hol = set(holidays)
    out: list[date] = []
    cur = end if is_trading_day(end, hol) else prev_trading_day(end, hol)
    while len(out) < n:
        out.append(cur)
        cur = prev_trading_day(cur, hol)
    return list(reversed(out))
