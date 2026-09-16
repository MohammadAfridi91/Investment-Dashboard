import json
from datetime import date, timedelta
from pathlib import Path


def load_holidays(path: str | Path) -> dict[str, set[date]]:
    raw = json.loads(Path(path).read_text())
    return {
        year: {date.fromisoformat(h['date']) for h in entries}
        for year, entries in raw.items()
    }


def is_trading_day(d: date, holidays: dict[str, set[date]]) -> bool:
    if d.weekday() >= 5:
        return False
    return d not in holidays.get(str(d.year), set())


def next_trading_day(d: date, holidays: dict[str, set[date]]) -> date:
    nxt = d + timedelta(days=1)
    while not is_trading_day(nxt, holidays):
        nxt += timedelta(days=1)
    return nxt
