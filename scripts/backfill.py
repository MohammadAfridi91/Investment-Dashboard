from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import UTC, date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import load_config
from core.database.client import DB
from core.ingestion.nse_bhavcopy import NSEBhavcopyIngestor
from core.ingestion.nse_index_prices import NSEIndexPricesIngestor
from core.ingestion.nse_universe import NSEUniverseIngestor
from core.utils.http import NSEHttpClient, PlainHttpClient
from core.utils.logging import configure_logging, get_logger
from core.utils.trading_calendar import is_trading_day, last_n_trading_days

log = get_logger("backfill")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--sessions",
        type=int,
        default=int(os.environ.get("BACKFILL_SESSIONS", 375)),
    )
    ap.add_argument("--start-date", default=os.environ.get("BACKFILL_START_DATE"))
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--end-date", default=None)
    args = ap.parse_args()

    run_id = str(uuid.uuid4())
    configure_logging(run_id=run_id)
    cfg = load_config(args.config)
    db = DB()
    started = datetime.now(UTC)

    end = date.fromisoformat(args.end_date) if args.end_date else datetime.now(UTC).date()
    all_holidays = [h.date for h in cfg.nse_holidays]

    if args.start_date:
        cur = date.fromisoformat(args.start_date)
        sessions: list[date] = []
        while cur <= end:
            if is_trading_day(cur, all_holidays):
                sessions.append(cur)
            cur += timedelta(days=1)
    else:
        sessions = last_n_trading_days(end, args.sessions, all_holidays)

    log.info(
        "backfill_start",
        sessions=len(sessions),
        first=str(sessions[0]) if sessions else "",
        last=str(sessions[-1]) if sessions else "",
    )

    if not sessions:
        log.warning("no_sessions_to_backfill")
        return 0

    # Bootstrap universe if empty
    uni_count = len(db.select("universe", columns="symbol", limit=1))
    if uni_count == 0:
        log.info("backfill_bootstrapping_universe")
        uni_ing = NSEUniverseIngestor(
            PlainHttpClient(cfg.ingestion.user_agent, cfg.ingestion.request_delay_nse_archives_ms),
            db,
            cfg,
        )
        res = uni_ing.run(sessions[-1])
        log.info("universe_bootstrap_done", rows=res.rows_upserted)

    nse = NSEHttpClient(
        cfg.ingestion.user_agent,
        cfg.ingestion.request_delay_nse_archives_ms,
    )
    bc_ing = NSEBhavcopyIngestor(nse, db, cfg)
    ip_ing = NSEIndexPricesIngestor(nse, db, cfg)

    failures = 0
    total_processed = 0
    for i, d in enumerate(sessions, 1):
        r1 = bc_ing.run(d)
        r2 = ip_ing.run(d)
        total_processed += r1.rows_upserted + r2.rows_upserted
        if r1.status == "FAILED" or r2.status == "FAILED":
            failures += 1
        if i % 25 == 0 or i == len(sessions):
            log.info(
                "backfill_progress",
                i=i,
                total=len(sessions),
                failures=failures,
                date=str(d),
            )

    finished = datetime.now(UTC)
    dur = int((finished - started).total_seconds())
    status = "SUCCESS" if failures == 0 else "FAILED"
    db.upsert(
        "pipeline_health",
        [
            {
                "run_id": run_id,
                "workflow": "backfill",
                "status": status,
                "started_at": started.isoformat(),
                "finished_at": finished.isoformat(),
                "duration_seconds": dur,
                "rows_processed": total_processed,
                "error_message": f"{failures} failed sessions" if failures else None,
            }
        ],
        on_conflict="run_id",
    )

    log.info("backfill_done", sessions=len(sessions), failures=failures, rows=total_processed)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
