from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta


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
