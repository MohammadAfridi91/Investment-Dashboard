from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from core.config import load_config
from core.ingestion.screener_collector import ScreenerCollector


class DummyDB:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, list[dict[str, Any]]]] = []
        self.universe: list[dict[str, Any]] = [
            {"symbol": "INFY", "company_name": "Infosys Ltd"}
        ]
        self.market_regime: list[dict[str, Any]] = [
            {"trade_date": "2024-01-25", "gsec_10y_yield": 0.0718}
        ]

    def select(self, table: str, *a: Any, **k: Any) -> list[dict[str, Any]]:
        if table == "universe":
            return list(self.universe)
        if table == "market_regime":
            return list(self.market_regime)
        return []

    def upsert(self, table: str, rows: list[dict[str, Any]], *a: Any, **k: Any) -> int:
        self.upserts.append((table, rows))
        return len(rows)


class DummyHTTP:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw

    def get(self, url: str) -> bytes:
        return self.raw


def test_parse_screener_html(fixtures_dir: Path) -> None:
    cfg = load_config()
    db = DummyDB()
    raw = (fixtures_dir / "screener_infy_sample.html").read_bytes()
    http = DummyHTTP(raw)
    collector = ScreenerCollector(http, db, cfg)

    rows = collector.parse_html(raw, "INFY")
    assert len(rows) == 4
    years = [r["fiscal_year"] for r in rows]
    assert years == [2021, 2022, 2023, 2024]

    row_2024 = next(r for r in rows if r["fiscal_year"] == 2024)
    assert row_2024["sales"] == 153670.0
    assert row_2024["net_profit"] == 26233.0
    assert row_2024["cfo"] == 27500.0
    assert row_2024["total_assets"] == 138070.0


def test_screener_indicators_enrichment(fixtures_dir: Path) -> None:
    cfg = load_config()
    db = DummyDB()
    raw = (fixtures_dir / "screener_infy_sample.html").read_bytes()
    http = DummyHTTP(raw)
    collector = ScreenerCollector(http, db, cfg)

    rows = collector.parse_html(raw, "INFY")
    collector.enrich_indicators(rows, gsec_yield=0.0718)

    # 2024 has previous year (2023) so all indicators are computed
    row_2024 = next(r for r in rows if r["fiscal_year"] == 2024)
    assert row_2024["altman_z_double_prime"] is not None
    assert row_2024["beneish_m_score"] is not None
    assert row_2024["sloan_accrual"] is not None
    assert row_2024["piotroski_f_score"] is not None
    assert 0 <= row_2024["piotroski_f_score"] <= 9
    assert row_2024["wacc"] is not None


def test_screener_run(fixtures_dir: Path) -> None:
    cfg = load_config()
    db = DummyDB()
    raw = (fixtures_dir / "screener_infy_sample.html").read_bytes()
    http = DummyHTTP(raw)
    collector = ScreenerCollector(http, db, cfg)

    res = collector.run(date(2024, 1, 25))
    assert res.status == "SUCCESS"
    assert len(db.upserts) == 1
    table, rows = db.upserts[0]
    assert table == "forensic_financials"
    assert len(rows) <= 3  # Last 3 fiscal years per PIT hybrid backfill


def test_forensic_financials_zero_nulls(fixtures_dir: Path) -> None:
    cfg = load_config()
    db = DummyDB()
    raw = (fixtures_dir / "screener_infy_sample.html").read_bytes()
    http = DummyHTTP(raw)
    collector = ScreenerCollector(http, db, cfg)

    res = collector.run(date(2024, 1, 25))
    assert res.status == "SUCCESS"
    table, rows = db.upserts[0]
    assert table == "forensic_financials"
    for row in rows:
        null_keys = [k for k, v in row.items() if v is None]
        assert not null_keys, f"Found NULL columns in fiscal year {row.get('fiscal_year')}: {null_keys}"

