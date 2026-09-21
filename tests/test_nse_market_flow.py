from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from core.config import load_config
from core.ingestion.nse_market_flow import NSEMarketFlowIngestor


class DummyDB:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, list[dict[str, Any]]]] = []

    def select(self, table: str, *a: Any, **k: Any) -> list[dict[str, Any]]:
        return []

    def upsert(self, table: str, rows: list[dict[str, Any]], *a: Any, **k: Any) -> int:
        self.upserts.append((table, rows))
        return len(rows)


class DummyHTTP:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw

    def get(self, url: str) -> bytes:
        return self.raw


def test_parse_fiidii(fixtures_dir: Path) -> None:
    cfg = load_config()
    db = DummyDB()
    raw = (fixtures_dir / "fiidii_sample.csv").read_bytes()
    http = DummyHTTP(raw)
    ing = NSEMarketFlowIngestor(http, db, cfg)

    fii, dii = ing.parse(raw, date(2024, 1, 25))
    assert fii == -2144.75
    assert dii == 3450.00


def test_market_flow_run(fixtures_dir: Path) -> None:
    cfg = load_config()
    db = DummyDB()
    raw = (fixtures_dir / "fiidii_sample.csv").read_bytes()
    http = DummyHTTP(raw)
    ing = NSEMarketFlowIngestor(http, db, cfg)

    res = ing.run(date(2024, 1, 25))
    assert res.status == "SUCCESS"
    assert len(db.upserts) == 1
    table, rows = db.upserts[0]
    assert table == "market_regime"
    assert rows[0]["fii_cash_net_cr"] == -2144.75
    assert rows[0]["dii_cash_net_cr"] == 3450.00
