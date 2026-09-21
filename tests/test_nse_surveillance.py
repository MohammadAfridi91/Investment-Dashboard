from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from core.config import load_config
from core.ingestion.nse_surveillance import NSESurveillanceIngestor, _extract_stage


class DummyDB:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, list[dict[str, Any]]]] = []

    def select(self, table: str, *a: Any, **k: Any) -> list[dict[str, Any]]:
        return []

    def upsert(self, table: str, rows: list[dict[str, Any]], *a: Any, **k: Any) -> int:
        self.upserts.append((table, rows))
        return len(rows)


class DummyHTTP:
    def __init__(self, fixtures_dir: Path) -> None:
        self.fixtures_dir = fixtures_dir

    def get(self, url: str) -> bytes:
        if "long_term" in url:
            return (self.fixtures_dir / "asm_long_term_sample.csv").read_bytes()
        if "short_term" in url:
            return (self.fixtures_dir / "asm_short_term_sample.csv").read_bytes()
        if "gsm" in url:
            return (self.fixtures_dir / "gsm_sample.csv").read_bytes()
        raise ValueError(f"unexpected url: {url}")


def test_extract_stage() -> None:
    assert _extract_stage("Stage I") == 1
    assert _extract_stage("Stage II") == 2
    assert _extract_stage("Stage III") == 3
    assert _extract_stage("Stage IV") == 4
    assert _extract_stage("Stage 2") == 2
    assert _extract_stage(None) == 0
    assert _extract_stage("") == 0


def test_parse_stage_csv(fixtures_dir: Path) -> None:
    cfg = load_config()
    db = DummyDB()
    http = DummyHTTP(fixtures_dir)
    ing = NSESurveillanceIngestor(http, db, cfg)

    raw_lt = (fixtures_dir / "asm_long_term_sample.csv").read_bytes()
    stages = ing.parse_stage_csv(raw_lt)
    assert stages["ADANIENT"] == 2
    assert stages["GTLINFRA"] == 1


def test_surveillance_run_merges_all_sources(fixtures_dir: Path) -> None:
    cfg = load_config()
    db = DummyDB()
    http = DummyHTTP(fixtures_dir)
    ing = NSESurveillanceIngestor(http, db, cfg)

    t2t_set = {"SUZLON", "SOMEOTHER"}
    res = ing.run(date(2024, 1, 25), t2t_symbols=t2t_set)

    assert res.status == "SUCCESS"
    assert res.rows_written > 0

    assert len(db.upserts) == 1
    table, rows = db.upserts[0]
    assert table == "surveillance_registry"

    by_sym = {r["symbol"]: r for r in rows}
    assert by_sym["ADANIENT"]["asm_stage"] == 2
    assert by_sym["SUZLON"]["asm_stage"] == 1
    assert by_sym["SUZLON"]["is_t2t"] is True
    assert by_sym["RPOWER"]["gsm_stage"] == 1
