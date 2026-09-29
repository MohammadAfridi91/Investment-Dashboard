"""Pipeline outcome semantics: a run must never report SUCCESS while required data is missing."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

import run_daily_pipeline as rdp
from core.ingestion.base import Ingestor, IngestResult
from core.utils.trading_calendar import today_ist


class _Boom(Ingestor):
    SOURCE = "boom"
    SCHEDULE = "daily"

    def run(self, target_date: date) -> IngestResult:
        raise ValueError("kaboom")


class _Ok(Ingestor):
    SOURCE = "ok"
    SCHEDULE = "daily"

    def run(self, target_date: date) -> IngestResult:
        return IngestResult(source="ok", rows_upserted=7)


def test_run_safe_converts_exception_to_failed_result() -> None:
    res = _Boom().run_safe(date(2026, 9, 25))
    assert res.status == "FAILED"
    assert res.error == "ValueError: kaboom"


def test_run_safe_passthrough_and_duration() -> None:
    res = _Ok().run_safe(date(2026, 9, 25))
    assert res.status == "SUCCESS" and res.rows_upserted == 7
    assert res.duration_ms >= 0


def test_report_status_rules() -> None:
    r = rdp.RunReport()
    r.record("a", "SUCCESS", 5)
    assert r.status == "SUCCESS" and r.error_summary is None
    r.record("optional", "FAILED", error="x")
    assert r.status == "PARTIAL"
    r.record("bhavcopy", "FAILED", error="404", critical=True)
    assert r.status == "FAILED" and r.critical_failed
    assert "bhavcopy: 404" in (r.error_summary or "")
    assert r.total_rows == 5


def test_failed_ingestor_recorded_not_swallowed() -> None:
    r = rdp.RunReport()
    rdp._run_ingestor(r, "bhavcopy", _Boom(), date(2026, 9, 25), critical=True)
    assert r.status == "FAILED"


def _desk(fail_symbols: set[str]) -> Any:
    desk = MagicMock()

    def evaluate(sym: str, d: date) -> Any:
        if sym in fail_symbols:
            raise RuntimeError("bad data")
        return SimpleNamespace(symbol=sym)

    desk.evaluate_from_db.side_effect = evaluate
    return desk


@pytest.fixture
def cfg() -> Any:
    return SimpleNamespace(compliance=SimpleNamespace(immutable_archive_dir="unused"))


def test_one_bad_symbol_does_not_abort_desk(monkeypatch: pytest.MonkeyPatch, cfg: Any) -> None:
    monkeypatch.setattr(
        rdp, "write_card_archive", lambda card, archive_dir: SimpleNamespace(sym=card.symbol)
    )
    persisted: list[int] = []
    monkeypatch.setattr(rdp, "persist_archives", lambda db, b: persisted.append(len(b)))
    report = rdp.RunReport()
    symbols = [f"S{i}" for i in range(100)]
    rdp._run_desk(
        report, "tactical_desk", _desk({"S3"}), symbols, date(2026, 9, 25), cfg, MagicMock()
    )
    assert sum(persisted) == 99  # every other symbol still archived
    assert report.status == "PARTIAL"  # ...but the failure is visible, not swallowed


def test_too_many_symbol_failures_is_critical(monkeypatch: pytest.MonkeyPatch, cfg: Any) -> None:
    monkeypatch.setattr(rdp, "write_card_archive", lambda card, archive_dir: object())
    monkeypatch.setattr(rdp, "persist_archives", lambda db, b: None)
    report = rdp.RunReport()
    symbols = [f"S{i}" for i in range(100)]
    rdp._run_desk(
        report,
        "tactical_desk",
        _desk(set(symbols[:50])),
        symbols,
        date(2026, 9, 25),
        cfg,
        MagicMock(),
    )
    assert report.status == "FAILED"


def test_archive_persist_failure_is_critical(monkeypatch: pytest.MonkeyPatch, cfg: Any) -> None:
    monkeypatch.setattr(rdp, "write_card_archive", lambda card, archive_dir: object())

    def boom(db: Any, bundles: Any) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(rdp, "persist_archives", boom)
    report = rdp.RunReport()
    rdp._run_desk(
        report, "strategic_desk", _desk(set()), ["A", "B"], date(2026, 9, 25), cfg, MagicMock()
    )
    assert report.status == "FAILED"


def test_desks_skipped_when_critical_ingest_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    class Fail:
        def __init__(self, *a: Any, **k: Any) -> None: ...
        def run_safe(self, d: date) -> IngestResult:
            return IngestResult(source="x", status="FAILED", error="404")

    for name in [
        "NSEUniverseIngestor",
        "NSEBhavcopyIngestor",
        "NSEIndexPricesIngestor",
        "NSEDerivativesIngestor",
        "NSESurveillanceIngestor",
        "NSEInstitutionalIngestor",
        "NSEMarketFlowIngestor",
        "CorporateActionsIngestor",
        "GSecYieldIngestor",
        "BSEAnnouncementsIngestor",
        "ScreenerCollector",
    ]:
        monkeypatch.setattr(rdp, name, Fail)
    for name in ("NSEHttpClient", "PlainHttpClient"):
        monkeypatch.setattr(rdp, name, lambda *a, **k: None)
    monkeypatch.setattr(rdp, "update_daily_market_regime", lambda *a, **k: {})
    monkeypatch.setattr(
        rdp,
        "TechnicalIndicatorsComputer",
        lambda *a, **k: SimpleNamespace(run_for_date=lambda d: 0),
    )
    desks_called = MagicMock()
    monkeypatch.setattr(rdp, "_run_desks", desks_called)

    cfg = SimpleNamespace(
        ingestion=SimpleNamespace(request_delay_nse_archives_ms=0, user_agent="ua")
    )
    db = MagicMock()
    db.select.return_value = [{"symbol": "X"}]
    report = rdp.run_eod(cfg, db, date(2026, 9, 25), skip_ingestion=False)  # type: ignore[arg-type]
    assert report.status == "FAILED"
    desks_called.assert_not_called()


def test_skip_ingestion_still_runs_engines(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(rdp, "update_daily_market_regime", lambda *a, **k: calls.append("regime"))
    monkeypatch.setattr(
        rdp,
        "TechnicalIndicatorsComputer",
        lambda *a, **k: SimpleNamespace(run_for_date=lambda d: calls.append("tech") or 0),
    )
    monkeypatch.setattr(rdp, "_run_desks", lambda *a, **k: calls.append("desks"))
    report = rdp.run_eod(MagicMock(), MagicMock(), date(2026, 9, 25), skip_ingestion=True)
    assert calls == ["regime", "tech", "desks"]
    assert report.status == "SUCCESS"


def test_today_ist_rolls_over_before_utc() -> None:
    late_utc = datetime(2026, 9, 25, 19, 0, tzinfo=UTC)  # 00:30 IST on the 26th
    assert today_ist(late_utc) == date(2026, 9, 26)
    assert today_ist(datetime(2026, 9, 25, 13, 15, tzinfo=UTC)) == date(2026, 9, 25)
