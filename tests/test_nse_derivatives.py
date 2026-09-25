from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from core.config import load_config
from core.ingestion.nse_derivatives import NSEDerivativesIngestor


class DummyDB:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, list[dict[str, Any]]]] = []
        self.universe: list[dict[str, Any]] = [
            {"symbol": "INFY", "company_name": "Infosys", "isin": "INE009A01021", "is_fno": False},
            {"symbol": "TCS", "company_name": "TCS", "isin": "INE467B01029", "is_fno": False},
            {
                "symbol": "RELIANCE",
                "company_name": "Reliance",
                "isin": "INE002A01018",
                "is_fno": False,
            },
        ]
        self.daily_prices: list[dict[str, Any]] = [
            {"symbol": "INFY", "trade_date": "2024-01-25", "close_price": 1665.0},
            {"symbol": "TCS", "trade_date": "2024-01-25", "close_price": 3840.0},
            {"symbol": "RELIANCE", "trade_date": "2024-01-25", "close_price": 2720.0},
        ]

    def select(self, table: str, *a: Any, **k: Any) -> list[dict[str, Any]]:
        if table == "universe":
            return list(self.universe)
        return []

    def select_in(
        self, table: str, column: str, values: list[Any], columns: str = "*"
    ) -> list[dict[str, Any]]:
        if table == "daily_prices":
            return [r for r in self.daily_prices if r.get(column) in values]
        return []

    def upsert(self, table: str, rows: list[dict[str, Any]], *a: Any, **k: Any) -> int:
        self.upserts.append((table, rows))
        if table == "universe":
            for r in rows:
                for u in self.universe:
                    if u["symbol"] == r["symbol"]:
                        u["is_fno"] = r.get("is_fno", False)
        return len(rows)


class DummyHTTP:
    def __init__(self, fixtures_dir: Path) -> None:
        self.fixtures_dir = fixtures_dir

    def get(self, url: str) -> bytes:
        if "bhav.csv" in url:
            return (self.fixtures_dir / "fo_bhavcopy_sample.csv").read_bytes()
        if "cor_mwp" in url:
            return (self.fixtures_dir / "mwpl_sample.csv").read_bytes()
        if "secban" in url:
            return (self.fixtures_dir / "fo_secban_sample.csv").read_bytes()
        raise ValueError(f"unexpected url: {url}")


def test_parse_fo_bhavcopy(fixtures_dir: Path) -> None:
    cfg = load_config()
    db = DummyDB()
    http = DummyHTTP(fixtures_dir)
    ing = NSEDerivativesIngestor(http, db, cfg)

    raw_fo = (fixtures_dir / "fo_bhavcopy_sample.csv").read_bytes()
    raw_mwpl = (fixtures_dir / "mwpl_sample.csv").read_bytes()
    raw_ban = (fixtures_dir / "fo_secban_sample.csv").read_bytes()

    mwpl_map = ing.parse_mwpl(raw_mwpl)
    ban_set = ing.parse_ban_list(raw_ban)

    rows, fno_syms = ing.parse_bhavcopy(raw_fo, date(2024, 1, 25), mwpl_map, ban_set)

    assert "INFY" in fno_syms
    assert "TCS" in fno_syms
    assert "RELIANCE" in fno_syms

    infy = next(r for r in rows if r["symbol"] == "INFY")
    # INFY has two FUTSTK contracts: 1000000 + 600000 = 1600000
    assert infy["fno_oi"] == 1600000
    assert infy["mwpl_pct"] == 32.0
    assert infy["is_fno_ban"] is False
    assert infy["spot_price"] == 1665.0
    # PCR check: PE OI 360000 / CE OI 400000 = 0.90
    assert infy["pcr"] == 0.90
    # Rollover %: 600000 / (1000000 + 600000) = 37.5%
    assert infy["rollover_pct"] == 37.5

    rel = next(r for r in rows if r["symbol"] == "RELIANCE")
    assert rel["is_fno_ban"] is True
    assert rel["mwpl_pct"] == 80.0


def test_derivatives_run_syncs_universe(fixtures_dir: Path) -> None:
    cfg = load_config()
    db = DummyDB()
    http = DummyHTTP(fixtures_dir)
    ing = NSEDerivativesIngestor(http, db, cfg)

    result = ing.run(date(2024, 1, 25))
    assert result.status == "SUCCESS"
    assert result.rows_written == 3

    # Verify universe is_fno got updated to True
    infy_u = next(u for u in db.universe if u["symbol"] == "INFY")
    assert infy_u["is_fno"] is True
