from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from core.config import load_config
from core.ingestion.bse_announcements import BSEAnnouncementsIngestor


class DummyDB:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, list[dict[str, Any]]]] = []
        self.universe: list[dict[str, Any]] = [
            {"symbol": "INFY", "company_name": "INFOSYS LTD"},
            {"symbol": "TCS", "company_name": "TATA CONSULTANCY SERVICES LTD"},
            {"symbol": "RELIANCE", "company_name": "RELIANCE INDUSTRIES LTD"},
        ]

    def select(self, table: str, *a: Any, **k: Any) -> list[dict[str, Any]]:
        if table == "universe":
            return list(self.universe)
        return []

    def upsert(self, table: str, rows: list[dict[str, Any]], *a: Any, **k: Any) -> int:
        self.upserts.append((table, rows))
        return len(rows)


class DummyHTTP:
    def __init__(self, fixtures_dir: Path) -> None:
        self.fixtures_dir = fixtures_dir

    def get(self, url: str) -> bytes:
        if "strCat=30" in url:
            return (self.fixtures_dir / "bse_announcements_cat30.json").read_bytes()
        if "strCat=17" in url:
            return (self.fixtures_dir / "bse_announcements_cat17.json").read_bytes()
        return b'{"Table": []}'


def test_bse_announcements_classification(fixtures_dir: Path) -> None:
    cfg = load_config()
    db = DummyDB()
    http = DummyHTTP(fixtures_dir)
    ing = BSEAnnouncementsIngestor(http, db, cfg)

    res = ing.run(date(2024, 1, 25))
    assert res.status == "SUCCESS"
    assert res.rows_written > 0

    tables = {t for t, _ in db.upserts}
    assert "governance_events" in tables
    assert "auditor_history" in tables

    # Check governance events
    gov_rows = next(rows for t, rows in db.upserts if t == "governance_events")
    gov_types = {r["event_type"] for r in gov_rows}
    assert "GST_RAID" in gov_types or "SEBI_REGULATORY" in gov_types or "AUDITOR_RESIGNATION" in gov_types

    # Check auditor history
    aud_rows = next(rows for t, rows in db.upserts if t == "auditor_history")
    infy_aud = next((r for r in aud_rows if r["symbol"] == "INFY"), None)
    assert infy_aud is not None
    assert infy_aud["is_tier1"] is True  # S.R. Batliboi is in tier 1 auditors list
    assert infy_aud["mid_term_resignation"] is True
