#!/usr/bin/env python3
"""
scripts/backfill.py

Historical backfill for daily_prices + benchmark_prices/sector_indices/
market_regime, driven by backfill.yml's BACKFILL_SESSIONS (default 375)
and optional BACKFILL_START_DATE.

Two things worth knowing before running this:

1. universe must be populated before any bhavcopy row can insert --
   daily_prices.symbol is a foreign key into universe(symbol). This
   script runs NSEUniverseIngestor once, first, for exactly that reason
   (the plan calls nse_universe.py "on-demand via CLI" and doesn't wire
   it into the daily automation, but a fresh database has no universe
   rows at all, so backfill can't skip it).

2. Trading days are processed oldest-first, not newest-first. Both
   nse_bhavcopy.py's 52w high/low and nse_index_prices.py's SMA(50)/
   SMA(200) look backward at what's already in the database -- if the
   most recent day were processed first, every earlier day would then
   compute its rolling windows against an empty history. Oldest-first
   means each day's rolling figures reflect only genuinely prior data,
   the same way they'd accumulate day-by-day in real operation.

Date range resolution:
  BACKFILL_START_DATE given -> collect BACKFILL_SESSIONS trading days
    forward from that date (inclusive).
  BACKFILL_START_DATE blank -> collect BACKFILL_SESSIONS trading days
    backward from the most recent completed trading day.

One boundary worth flagging, not handling specially: NSE's UDiFF bhavcopy
format only exists from 2024-07-08 onward (see nse_bhavcopy.py's module
docstring). The default 375 sessions from "today" lands well inside that
window, but a manually-triggered backfill with a much larger session
count or an early enough start_date will start hitting dates the format
doesn't cover. Individual date failures already degrade gracefully
(Ingestor.run() catches fetch errors per-date and continues) -- this
isn't a crash risk, just something to notice in the per-date error log
if it happens.
"""
import os
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from core.ingestion.nse_bhavcopy import NSEBhavcopyIngestor
from core.ingestion.nse_index_prices import NSEIndexPricesIngestor
from core.ingestion.nse_universe import NSEUniverseIngestor
from core.utils.logging import configure_logging
from core.utils.trading_calendar import is_trading_day, load_holidays, next_trading_day

HOLIDAYS_PATH = "config/nse_holidays.json"
DEFAULT_SESSIONS = 375
PROGRESS_EVERY = 20


def most_recent_completed_session(holidays: dict) -> date:
    d = date.today() - timedelta(days=1)
    while not is_trading_day(d, holidays):
        d -= timedelta(days=1)
    return d


def resolve_date_range(sessions: int, start_date: date | None, holidays: dict) -> list[date]:
    if start_date is not None:
        dates = []
        d = start_date if is_trading_day(start_date, holidays) else next_trading_day(start_date, holidays)
        for _ in range(sessions):
            dates.append(d)
            d = next_trading_day(d, holidays)
        return dates  # already oldest-first

    dates = []
    d = most_recent_completed_session(holidays)
    for _ in range(sessions):
        dates.append(d)
        d -= timedelta(days=1)
        while not is_trading_day(d, holidays):
            d -= timedelta(days=1)
    return list(reversed(dates))  # was newest-first, flip to oldest-first


def main() -> int:
    sessions = int(os.environ.get("BACKFILL_SESSIONS") or DEFAULT_SESSIONS)
    start_raw = (os.environ.get("BACKFILL_START_DATE") or "").strip()
    start_date = date.fromisoformat(start_raw) if start_raw else None

    run_id = uuid.uuid4()
    started_at = datetime.now(UTC)
    logger = configure_logging(run_id=str(run_id), module="backfill")
    logger.info("backfill_start", sessions=sessions, start_date=str(start_date) if start_date else "auto")

    holidays = load_holidays(HOLIDAYS_PATH)
    target_dates = resolve_date_range(sessions, start_date, holidays)
    logger.info("date_range_resolved", first=str(target_dates[0]), last=str(target_dates[-1]),
                count=len(target_dates))

    logger.info("universe_backfill_start")
    universe_result = NSEUniverseIngestor().run(target_dates[-1])
    logger.info("universe_backfill_done", rows_written=universe_result.rows_written,
                errors=universe_result.errors)
    if universe_result.rows_written == 0:
        logger.error("universe_empty_aborting",
                     note="daily_prices.symbol is FK'd to universe(symbol); "
                          "every bhavcopy insert would fail. Not proceeding.")
        _write_health(run_id, started_at, "FAILED", 0,
                      "universe backfill produced 0 rows; aborting before daily_prices")
        return 1

    total_rows = 0
    all_errors: list[str] = []
    per_date_log: list[str] = []

    for i, d in enumerate(target_dates, start=1):
        day_rows = 0
        for ingestor in (NSEBhavcopyIngestor(), NSEIndexPricesIngestor()):
            result = ingestor.run(d)
            day_rows += result.rows_written
            total_rows += result.rows_written
            for e in result.errors:
                all_errors.append(f"{d} {ingestor.SOURCE}: {e}")

        per_date_log.append(f"{d}: {day_rows} rows written")
        if i % PROGRESS_EVERY == 0 or i == len(target_dates):
            logger.info("backfill_progress", completed=i, total=len(target_dates),
                        total_rows_so_far=total_rows)

    status = "SUCCESS" if total_rows > 0 else "FAILED"
    error_message = "; ".join(all_errors)[:5000] if all_errors else None

    _write_health(run_id, started_at, status, total_rows, error_message)
    _write_log(run_id, target_dates, total_rows, per_date_log, all_errors)

    logger.info("backfill_done", status=status, total_rows=total_rows,
                dates_processed=len(target_dates), error_count=len(all_errors))
    return 0 if status == "SUCCESS" else 1


def _write_health(run_id: uuid.UUID, started_at: datetime, status: str,
                   rows: int, error_message: str | None) -> None:
    from core.database.client import get_client

    finished_at = datetime.now(UTC)
    client = get_client()
    client.bulk_upsert("pipeline_health", [{
        "id": str(uuid.uuid4()),
        "run_id": str(run_id),
        "workflow": "backfill",
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": int((finished_at - started_at).total_seconds()),
        "rows_processed": rows,
        "error_message": error_message,
    }], conflict_cols=["id"])


def _write_log(run_id: uuid.UUID, target_dates: list[date], total_rows: int,
               per_date_log: list[str], errors: list[str]) -> None:
    Path("logs").mkdir(exist_ok=True)
    path = Path("logs") / f"backfill_{run_id}.log"
    lines = [
        f"backfill run_id={run_id} range={target_dates[0]}..{target_dates[-1]} "
        f"sessions={len(target_dates)} total_rows={total_rows}",
        "",
        "--- per-date rows written ---",
        *per_date_log,
        "",
        "--- errors ---",
        *(errors or ["(none)"]),
    ]
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
