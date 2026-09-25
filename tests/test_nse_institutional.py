from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from core.config import load_config
from core.ingestion.nse_institutional import NSEInstitutionalIngestor


class DummyDB:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, list[dict[str, Any]]]] = []
        self.derivative_metrics: list[dict[str, Any]] = [
            {"symbol": "RELIANCE", "trade_date": "2024-01-25", "has_institutional_net_buy": False}
        ]

    def select(self, table: str, *a: Any, **k: Any) -> list[dict[str, Any]]:
        return []

    def select_in(
        self, table: str, column: str, values: list[Any], columns: str = "*"
    ) -> list[dict[str, Any]]:
        if table == "derivative_metrics":
            return [r for r in self.derivative_metrics if r.get(column) in values]
        return []

    def upsert(self, table: str, rows: list[dict[str, Any]], *a: Any, **k: Any) -> int:
        self.upserts.append((table, rows))
        if table == "derivative_metrics":
            for r in rows:
                for d in self.derivative_metrics:
                    if d["symbol"] == r["symbol"]:
                        d["has_institutional_net_buy"] = r.get("has_institutional_net_buy", False)
        return len(rows)


class DummyHTTP:
    def __init__(self, fixtures_dir: Path) -> None:
        self.fixtures_dir = fixtures_dir

    def get(self, url: str) -> bytes:
        if "bulk" in url:
            return (self.fixtures_dir / "bulk_deals_sample.csv").read_bytes()
        if "block" in url:
            return (self.fixtures_dir / "block_deals_sample.csv").read_bytes()
        raise ValueError(f"unexpected url: {url}")


def test_parse_and_pattern_matching(fixtures_dir: Path) -> None:
    cfg = load_config()
    db = DummyDB()
    http = DummyHTTP(fixtures_dir)
    ing = NSEInstitutionalIngestor(http, db, cfg)

    raw_bulk = (fixtures_dir / "bulk_deals_sample.csv").read_bytes()
    regexes = ing._compile_institutional_regexes()
    rows = ing.parse_deals_csv(raw_bulk, "BULK", date(2024, 1, 25), regexes)

    assert len(rows) == 4
    rel = next(r for r in rows if r["symbol"] == "RELIANCE")
    assert rel["is_institutional"] is True  # SBI MUTUAL FUND matches AMC regex

    ind = next(r for r in rows if r["client_name"] == "NON INSTITUTIONAL INDIVIDUAL")
    assert ind["is_institutional"] is False


def test_wash_trade_detection(fixtures_dir: Path) -> None:
    cfg = load_config()
    db = DummyDB()
    http = DummyHTTP(fixtures_dir)
    ing = NSEInstitutionalIngestor(http, db, cfg)

    raw_bulk = (fixtures_dir / "bulk_deals_sample.csv").read_bytes()
    regexes = ing._compile_institutional_regexes()
    rows = ing.parse_deals_csv(raw_bulk, "BULK", date(2024, 1, 25), regexes)

    ing._flag_wash_trades(rows)

    infy_trades = [r for r in rows if r["symbol"] == "INFY"]
    assert len(infy_trades) == 2
    # Buy 50000 @ 1650 vs Sell 49500 @ 1651: diff is (50000 - 49500)/50000 = 1.0% <= 10%, value is ~8.2 Cr >= 1 Cr
    assert infy_trades[0]["is_wash_trade"] is True
    assert infy_trades[1]["is_wash_trade"] is True


def test_run_syncs_derivative_net_buy(fixtures_dir: Path) -> None:
    cfg = load_config()
    db = DummyDB()
    http = DummyHTTP(fixtures_dir)
    ing = NSEInstitutionalIngestor(http, db, cfg)

    res = ing.run(date(2024, 1, 25))
    assert res.status == "SUCCESS"
    assert res.rows_written == 5  # 4 bulk + 1 block

    # Verify RELIANCE has_institutional_net_buy was updated to True (100000 * 2850.5 = 28.5 Cr >= 5 Cr)
    rel_d = next(d for d in db.derivative_metrics if d["symbol"] == "RELIANCE")
    assert rel_d["has_institutional_net_buy"] is True
