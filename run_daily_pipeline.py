#!/usr/bin/env python3
"""
run_daily_pipeline.py

Week 1 scope: wires the ingestors together and records every run to
pipeline_health.

--mode eod       Runs nse_bhavcopy + nse_index_prices for TARGET_DATE
                 (today's session, meant to run after market close --
                 both files become available around the same time).
--mode premarket No Week-1-scoped ingestion belongs here yet:
                 nse_universe.py is explicitly "on-demand via CLI" in the
                 plan (not a daily automated job), and surveillance /
                 corporate-action ingestion -- this slot's original
                 intent per the repo's own README -- is Week 2 scope.
                 Logs that plainly and exits 0 rather than inventing
                 work to fill the slot.

Env vars (matching what the workflows pass):
  TARGET_DATE      YYYY-MM-DD, optional. Defaults to today.
  SKIP_INGESTION   "true"/"false", optional. Default false.
"""
import argparse
import os
import sys
import traceback
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from core.ingestion.base import Ingestor
from core.ingestion.nse_bhavcopy import NSEBhavcopyIngestor
from core.ingestion.nse_index_prices import NSEIndexPricesIngestor
from core.utils.logging import configure_logging
from core.utils.trading_calendar import is_trading_day, load_holidays

HOLIDAYS_PATH = "config/nse_holidays.json"


def parse_target_date() -> date:
    raw = os.environ.get("TARGET_DATE", "").strip()
    return date.fromisoformat(raw) if raw else date.today()


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() == "true"


def run_ingestor(ingestor: Ingestor, target_date: date, logger) -> tuple[int, list[str]]:
    logger.info("ingestor_start", source=ingestor.SOURCE)
    result = ingestor.run(target_date)
    logger.info(
        "ingestor_done",
        source=ingestor.SOURCE,
        rows_fetched=result.rows_fetched,
        rows_valid=result.rows_valid,
        rows_rejected=result.rows_rejected,
        rows_written=result.rows_written,
        duration_ms=result.duration_ms,
        errors=result.errors,
    )
    return result.rows_written, [f"{ingestor.SOURCE}: {e}" for e in result.errors]


def write_health(
    workflow: str, run_id: uuid.UUID, started_at: datetime,
    status: str, rows_processed: int, error_message: str | None,
) -> None:
    from core.database.client import get_client

    finished_at = datetime.now(UTC)
    client = get_client()
    client.bulk_upsert("pipeline_health", [{
        "id": str(uuid.uuid4()),  # bulk_upsert needs a conflict target;
                                  # a fresh id per write makes this a
                                  # plain insert in practice
        "run_id": str(run_id),
        "workflow": workflow,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": int((finished_at - started_at).total_seconds()),
        "rows_processed": rows_processed,
        "error_message": (error_message or None),
    }], conflict_cols=["id"])


def write_log_summary(mode: str, run_id: uuid.UUID, status: str, rows: int, errors: list[str]) -> None:
    """eod_pipeline.yml's 'Upload logs' step expects logs/ to have
    something in it; structlog's JSON stream already goes to stdout
    (captured in the job's own log regardless), this is just a
    convenient downloadable summary alongside it."""
    Path("logs").mkdir(exist_ok=True)
    path = Path("logs") / f"{mode}_{run_id}.log"
    lines = [
        f"mode={mode} run_id={run_id} status={status} rows_processed={rows}",
        *errors,
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=["eod", "premarket"])
    args = parser.parse_args()

    target_date = parse_target_date()
    skip_ingestion = env_flag("SKIP_INGESTION")
    run_id = uuid.uuid4()
    started_at = datetime.now(UTC)

    logger = configure_logging(run_id=str(run_id), module="run_daily_pipeline")
    logger.info("pipeline_start", mode=args.mode, target_date=str(target_date),
                skip_ingestion=skip_ingestion)

    holidays = load_holidays(HOLIDAYS_PATH)
    if not is_trading_day(target_date, holidays):
        logger.warning("not_a_trading_day", target_date=str(target_date))
        write_health(args.mode, run_id, started_at, "SUCCESS", 0,
                     f"{target_date} is not a trading day; nothing to do")
        write_log_summary(args.mode, run_id, "SUCCESS", 0,
                          [f"{target_date} is not a trading day"])
        return 0

    total_rows = 0
    errors: list[str] = []
    status = "SUCCESS"

    try:
        if skip_ingestion:
            logger.info("skip_ingestion_set", mode=args.mode)
        elif args.mode == "eod":
            for ingestor in (NSEBhavcopyIngestor(), NSEIndexPricesIngestor()):
                rows, ing_errors = run_ingestor(ingestor, target_date, logger)
                total_rows += rows
                errors.extend(ing_errors)
        elif args.mode == "premarket":
            logger.info(
                "premarket_noop",
                note="No Week 1 premarket-scoped ingestion: nse_universe.py "
                     "is on-demand via CLI per the plan, and surveillance/"
                     "corporate-action ingestion is Week 2.",
            )
    except Exception:
        status = "FAILED"
        tb = traceback.format_exc()
        errors.append(tb)
        logger.error("pipeline_exception", traceback=tb)

    if status == "SUCCESS" and total_rows == 0 and errors:
        # every ingestor that ran produced zero rows AND reported errors --
        # a genuinely empty EOD run is worth flagging loudly, distinct from
        # "some rows were rejected but most wrote fine"
        status = "FAILED"

    error_message = "; ".join(errors)[:5000] if errors else None
    write_health(args.mode, run_id, started_at, status, total_rows, error_message)
    write_log_summary(args.mode, run_id, status, total_rows, errors)

    logger.info("pipeline_done", status=status, total_rows=total_rows)
    return 0 if status != "FAILED" else 1


if __name__ == "__main__":
    sys.exit(main())
