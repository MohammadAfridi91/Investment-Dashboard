from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from core.config import load_config
from core.ingestion.gsec_yield import GSecYieldIngestor


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


def test_parse_rbi_html(fixtures_dir: Path) -> None:
    cfg = load_config()
    db = DummyDB()
    raw = (fixtures_dir / "rbi_nsdp_sample.html").read_bytes()
    http = DummyHTTP(raw)
    ing = GSecYieldIngestor(http, db, cfg)

    val = ing.parse_html(raw)
    assert val == 0.0718  # 7.18% converted to decimal


def test_gsec_run(fixtures_dir: Path) -> None:
    cfg = load_config()
    db = DummyDB()
    raw = (fixtures_dir / "rbi_nsdp_sample.html").read_bytes()
    http = DummyHTTP(raw)
    ing = GSecYieldIngestor(http, db, cfg)

    res = ing.run(date(2024, 1, 25))
    assert res.status == "SUCCESS"
    assert len(db.upserts) == 1
    table, rows = db.upserts[0]
    assert table == "market_regime"
    assert rows[0]["gsec_10y_yield"] == 0.0718


def test_gsec_graceful_on_bad_html() -> None:
    cfg = load_config()
    db = DummyDB()
    bad_html = b"<html><body>No yield data here</body></html>"
    http = DummyHTTP(bad_html)
    ing = GSecYieldIngestor(http, db, cfg)

    res = ing.run(date(2024, 1, 25))
    assert res.status == "SKIPPED"
    assert len(db.upserts) == 0
