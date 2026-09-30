from __future__ import annotations

import argparse
import os
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from core.compliance.sebi_ra import (
    ArchiveBundle,
    persist_archives,
    resolve_registration_number,
    write_card_archive,
)
from core.config import Config, load_config
from core.database.client import DB
from core.indicators.regime import update_daily_market_regime
from core.indicators.technicals import TechnicalIndicatorsComputer
from core.ingestion.base import Ingestor
from core.ingestion.bse_announcements import BSEAnnouncementsIngestor
from core.ingestion.corporate_actions import CorporateActionsIngestor
from core.ingestion.gsec_yield import GSecYieldIngestor
from core.ingestion.nse_bhavcopy import NSEBhavcopyIngestor
from core.ingestion.nse_derivatives import NSEDerivativesIngestor
from core.ingestion.nse_index_prices import NSEIndexPricesIngestor
from core.ingestion.nse_institutional import NSEInstitutionalIngestor
from core.ingestion.nse_market_flow import NSEMarketFlowIngestor
from core.ingestion.nse_surveillance import NSESurveillanceIngestor
from core.ingestion.nse_universe import NSEUniverseIngestor
from core.ingestion.screener_collector import ScreenerCollector
from core.utils.http import NSEHttpClient, PlainHttpClient
from core.utils.logging import configure_logging, get_logger
from core.utils.trading_calendar import is_trading_day, today_ist

log = get_logger("pipeline")

# Fraction of symbols allowed to fail evaluation before a desk is considered failed.
DESK_MAX_ERROR_RATIO = 0.10
DESK_MIN_TOLERATED_ERRORS = 5
# Reports are persisted in batches (large HTML bodies) rather than one round-trip per card.
ARCHIVE_FLUSH_SIZE = 50
MAX_ERROR_SUMMARY_CHARS = 2000


@dataclass
class StepOutcome:
    name: str
    status: str  # SUCCESS | SKIPPED | FAILED
    rows: int = 0
    error: str | None = None
    critical: bool = False


@dataclass
class RunReport:
    """Aggregates per-step outcomes so a run can never report SUCCESS while data is missing."""

    steps: list[StepOutcome] = field(default_factory=list)

    def record(
        self,
        name: str,
        status: str,
        rows: int = 0,
        error: str | None = None,
        critical: bool = False,
    ) -> None:
        self.steps.append(StepOutcome(name, status, rows, error, critical))

    @property
    def total_rows(self) -> int:
        return sum(s.rows for s in self.steps)

    @property
    def failures(self) -> list[StepOutcome]:
        return [s for s in self.steps if s.status == "FAILED"]

    @property
    def critical_failed(self) -> bool:
        return any(s.critical for s in self.failures)

    @property
    def status(self) -> str:
        if self.critical_failed:
            return "FAILED"
        return "PARTIAL" if self.failures else "SUCCESS"

    @property
    def error_summary(self) -> str | None:
        if not self.failures:
            return None
        text = "; ".join(f"{s.name}: {s.error or 'failed'}" for s in self.failures)
        return text[:MAX_ERROR_SUMMARY_CHARS]


def _record_health(
    db: DB,
    run_id: str,
    workflow: str,
    status: str,
    started: datetime,
    finished: datetime | None,
    rows: int,
    error: str | None,
) -> None:
    dur = int((finished - started).total_seconds()) if finished else None
    db.upsert(
        "pipeline_health",
        [
            {
                "run_id": run_id,
                "workflow": workflow,
                "status": status,
                "started_at": started.isoformat(),
                "finished_at": finished.isoformat() if finished else None,
                "duration_seconds": dur,
                "rows_processed": rows,
                "error_message": error,
            }
        ],
        on_conflict="run_id",
    )


def _record_health_safe(*args: Any, **kwargs: Any) -> None:
    """Health logging must never mask or replace the pipeline's real outcome."""
    try:
        _record_health(*args, **kwargs)
    except Exception as exc:
        log.error("pipeline_health_write_failed", error=f"{type(exc).__name__}: {exc}")


def _run_ingestor(
    report: RunReport,
    name: str,
    ingestor: Ingestor,
    target_date: date,
    critical: bool = False,
) -> None:
    res = ingestor.run_safe(target_date)
    log.info(f"{name}_result", status=res.status, rows=res.rows_upserted, error=res.error)
    report.record(name, res.status, res.rows_upserted, res.error, critical)


def _run_step(
    report: RunReport,
    name: str,
    fn: Callable[[], int | None],
    critical: bool = False,
) -> None:
    try:
        rows = fn() or 0
    except Exception as exc:
        log.exception(f"{name}_failed")
        report.record(name, "FAILED", error=f"{type(exc).__name__}: {exc}", critical=critical)
        return
    report.record(name, "SUCCESS", rows)


def _run_desk(
    report: RunReport,
    name: str,
    desk: Any,
    symbols: list[str],
    target_date: date,
    cfg: Config,
    db: DB,
) -> None:
    """Evaluate every symbol independently; one bad symbol never aborts the desk."""
    pending: list[ArchiveBundle] = []
    cards = 0
    symbol_errors = 0

    def flush() -> None:
        persist_archives(db, pending)
        pending.clear()

    for sym in symbols:
        try:
            card = desk.evaluate_from_db(sym, target_date)
            if card:
                pending.append(
                    write_card_archive(card, archive_dir=cfg.compliance.immutable_archive_dir)
                )
                cards += 1
        except Exception as exc:
            symbol_errors += 1
            log.error(f"{name}_symbol_failed", symbol=sym, error=f"{type(exc).__name__}: {exc}")
            continue
        if len(pending) >= ARCHIVE_FLUSH_SIZE:
            try:
                flush()
            except Exception as exc:  # DB persistence failure is systemic: stop and fail loudly
                log.error(f"{name}_archive_persist_failed", error=str(exc))
                report.record(
                    name,
                    "FAILED",
                    cards,
                    f"archive persistence failed: {type(exc).__name__}: {exc}",
                    critical=True,
                )
                return
    try:
        flush()
    except Exception as exc:
        log.error(f"{name}_archive_persist_failed", error=str(exc))
        report.record(
            name,
            "FAILED",
            cards,
            f"archive persistence failed: {type(exc).__name__}: {exc}",
            critical=True,
        )
        return

    tolerated = max(DESK_MIN_TOLERATED_ERRORS, int(len(symbols) * DESK_MAX_ERROR_RATIO))
    log.info(f"{name}_result", cards=cards, symbol_errors=symbol_errors, symbols=len(symbols))
    if symbol_errors > tolerated:
        report.record(
            name,
            "FAILED",
            cards,
            f"{symbol_errors}/{len(symbols)} symbols failed evaluation",
            critical=True,
        )
    elif symbol_errors:
        report.record(name, "FAILED", cards, f"{symbol_errors} symbols failed evaluation")
    else:
        report.record(name, "SUCCESS", cards)


def _run_desks(report: RunReport, cfg: Config, db: DB, target_date: date) -> None:
    from core.engines.strategic_desk import StrategicDesk
    from core.engines.tactical_desk import TacticalDesk

    # Fail fast only if a registration number is set but malformed (registration is optional).
    resolve_registration_number()

    fno = [
        r["symbol"]
        for r in db.select("universe", columns="symbol", filters={"is_fno": True, "is_bfsi": False})
        if r.get("symbol")
    ]
    _run_desk(report, "tactical_desk", TacticalDesk(db, cfg), fno, target_date, cfg, db)

    nifty500 = [
        r["symbol"]
        for r in db.select(
            "universe", columns="symbol", filters={"is_bfsi": False, "is_nifty500": True}
        )
        if r.get("symbol")
    ]
    _run_desk(report, "strategic_desk", StrategicDesk(db, cfg), nifty500, target_date, cfg, db)


def run_eod(cfg: Config, db: DB, target_date: date, skip_ingestion: bool) -> RunReport:
    report = RunReport()

    if skip_ingestion:
        log.info("eod_skip_ingestion")  # engines below still run on already-ingested data
    else:
        universe_empty = len(db.select("universe", columns="symbol", limit=1)) == 0
        delay = cfg.ingestion.request_delay_nse_archives_ms
        ua = cfg.ingestion.user_agent
        nse = NSEHttpClient(ua, delay)
        plain = PlainHttpClient(ua, delay)

        if target_date.weekday() == 0 or universe_empty:
            _run_ingestor(
                report,
                "universe",
                NSEUniverseIngestor(PlainHttpClient(ua, delay), db, cfg),
                target_date,
                critical=universe_empty,
            )

        # (name, ingestor, critical). Critical sources gate the desks: without fresh prices,
        # cards would be built on stale data.
        sources: list[tuple[str, Ingestor, bool]] = [
            ("bhavcopy", NSEBhavcopyIngestor(nse, db, cfg), True),
            ("index_prices", NSEIndexPricesIngestor(nse, db, cfg), True),
            ("derivatives", NSEDerivativesIngestor(nse, db, cfg), False),
            ("surveillance", NSESurveillanceIngestor(plain, db, cfg), False),
            ("institutional", NSEInstitutionalIngestor(plain, db, cfg), False),
            ("market_flow", NSEMarketFlowIngestor(plain, db, cfg), False),
            ("corporate_actions", CorporateActionsIngestor(plain, db, cfg), False),
            ("gsec", GSecYieldIngestor(plain, db, cfg), False),
            ("bse_announcements", BSEAnnouncementsIngestor(plain, db, cfg), False),
        ]
        for name, ingestor, critical in sources:
            _run_ingestor(report, name, ingestor, target_date, critical)

        # Screener runs weekly or if the financials table is empty
        if target_date.weekday() == 5 or not db.select(
            "forensic_financials", columns="symbol", limit=1
        ):
            _run_ingestor(report, "screener", ScreenerCollector(plain, db, cfg), target_date)

    # Indicators
    def _regime() -> int:
        update_daily_market_regime(db, cfg, target_date)
        return 0

    _run_step(report, "market_regime", _regime)
    _run_step(
        report,
        "technicals",
        lambda: TechnicalIndicatorsComputer(db, cfg).run_for_date(target_date),
        critical=not skip_ingestion,
    )

    # Desks only run on trustworthy inputs.
    if report.critical_failed:
        log.error("desks_skipped_critical_failure", failures=report.error_summary)
        report.record(
            "desks", "FAILED", error="skipped: critical upstream step failed", critical=True
        )
    else:
        _run_step(report, "desks", lambda: _run_desks(report, cfg, db, target_date), critical=True)

    return report


def run_premarket(cfg: Config, db: DB, target_date: date) -> RunReport:
    report = RunReport()
    plain = PlainHttpClient(
        cfg.ingestion.user_agent,
        cfg.ingestion.request_delay_nse_archives_ms,
    )
    _run_ingestor(
        report,
        "premarket_surveillance",
        NSESurveillanceIngestor(plain, db, cfg),
        target_date,
        critical=True,
    )
    return report


def _annotate(level: str, message: str) -> None:
    """GitHub Actions workflow annotation (harmless elsewhere)."""
    print(f"::{level}::{message}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["eod", "premarket"], required=True)
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--date", default=None)
    ap.add_argument("--skip-ingestion", action="store_true")
    args = ap.parse_args()

    run_id = str(uuid.uuid4())
    configure_logging(run_id=run_id)
    cfg = load_config(args.config)

    date_str = args.date or os.environ.get("TARGET_DATE")
    # Exchange date is India time; a UTC date is wrong for runs after 18:30 UTC.
    target_date = date.fromisoformat(date_str) if date_str else today_ist()
    skip_ingestion = args.skip_ingestion or os.environ.get("SKIP_INGESTION", "").lower() in (
        "true",
        "1",
    )

    log.info(
        "pipeline_start",
        mode=args.mode,
        run_id=run_id,
        target_date=str(target_date),
        skip_ingestion=skip_ingestion,
    )

    db = DB()
    started = datetime.now(UTC)

    if not is_trading_day(target_date, [h.date for h in cfg.nse_holidays]):
        log.info("non_trading_day_skip", date=str(target_date))
        _record_health_safe(
            db, run_id, args.mode, "SKIPPED", started, datetime.now(UTC), 0, "non-trading day"
        )
        return 0

    report = RunReport()
    try:
        report = (
            run_eod(cfg, db, target_date, skip_ingestion)
            if args.mode == "eod"
            else run_premarket(cfg, db, target_date)
        )
    except Exception as exc:
        log.exception("pipeline_failed")
        report.record("pipeline", "FAILED", error=f"{type(exc).__name__}: {exc}", critical=True)

    status = report.status
    finished = datetime.now(UTC)
    _record_health_safe(
        db, run_id, args.mode, status, started, finished, report.total_rows, report.error_summary
    )
    log.info("pipeline_end", status=status, rows=report.total_rows, errors=report.error_summary)

    if status == "FAILED":
        _annotate("error", f"{args.mode} pipeline FAILED: {report.error_summary}")
        return 1
    if status == "PARTIAL":
        _annotate("warning", f"{args.mode} pipeline PARTIAL: {report.error_summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
