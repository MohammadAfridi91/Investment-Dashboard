from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from core.config import load_config
from core.ingestion.corporate_actions import (
    CorporateActionsIngestor,
    parse_action_purpose,
)


class DummyDB:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, list[dict[str, Any]]]] = []
        self.daily_prices: list[dict[str, Any]] = [
            {
                "symbol": "INFY",
                "trade_date": "2024-01-24",
                "close_price": 1660.0,
                "adjusted_close": 1660.0,
            },
            {
                "symbol": "INFY",
                "trade_date": "2024-01-25",
                "close_price": 830.0,
                "adjusted_close": 830.0,
            },
        ]
        self.corporate_actions: list[dict[str, Any]] = []

    def select(self, table: str, *a: Any, filters: dict[str, Any] | None = None, **k: Any) -> list[dict[str, Any]]:
        if table == "corporate_actions":
            if filters and "ex_date" in filters:
                return [r for r in self.corporate_actions if r.get("ex_date") == filters["ex_date"]]
            return list(self.corporate_actions)
        if table == "daily_prices":
            if filters and "symbol" in filters:
                return [r for r in self.daily_prices if r.get("symbol") == filters["symbol"]]
            return list(self.daily_prices)
        return []

    def upsert(self, table: str, rows: list[dict[str, Any]], *a: Any, **k: Any) -> int:
        self.upserts.append((table, rows))
        if table == "corporate_actions":
            self.corporate_actions.extend(rows)
        if table == "daily_prices":
            for r in rows:
                for d in self.daily_prices:
                    if d["symbol"] == r["symbol"] and d["trade_date"] == r["trade_date"]:
                        d.update(r)
        return len(rows)


class DummyHTTP:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw

    def get(self, url: str) -> bytes:
        return self.raw


def test_parse_action_purpose() -> None:
    act, factor, ratio, fv, div = parse_action_purpose("Stock Split From Rs 10 To Rs 1")
    assert act == "SPLIT"
    assert factor == 10.0
    assert ratio == 10.0
    assert fv == 1.0
    assert div is None

    act, factor, ratio, fv, div = parse_action_purpose("Bonus 1:1")
    assert act == "BONUS"
    assert factor == 2.0
    assert ratio == 2.0
    assert fv is None
    assert div is None

    act, factor, ratio, fv, div = parse_action_purpose("Bonus 1:2")
    assert act == "BONUS"
    assert factor == 1.5
    assert ratio == 1.5
    assert fv is None
    assert div is None

    act, factor, ratio, fv, div = parse_action_purpose("Dividend - Rs 9 Per Share")
    assert act == "DIVIDEND"
    assert factor == 1.0
    assert ratio is None
    assert fv is None
    assert div == 9.0




def test_corporate_actions_ingest_and_adjust(fixtures_dir: Path) -> None:
    cfg = load_config()
    db = DummyDB()
    raw = (fixtures_dir / "actions_sample.csv").read_bytes()
    http = DummyHTTP(raw)
    ing = CorporateActionsIngestor(http, db, cfg)

    res = ing.run(date(2024, 1, 25))
    assert res.status == "SUCCESS"
    assert res.rows_written == 3

    # Check that INFY's historical close price before ex-date (2024-01-24) was adjusted by factor=2.0 (Bonus 1:1)
    pre_ex_row = next(r for r in db.daily_prices if r["trade_date"] == "2024-01-24")
    assert pre_ex_row["close_price"] == 1660.0  # Raw close unchanged
    assert pre_ex_row["adjusted_close"] == 830.0  # Halved for 1:1 bonus
