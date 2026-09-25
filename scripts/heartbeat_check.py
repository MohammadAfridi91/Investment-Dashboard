from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database.client import DB
from core.utils.logging import configure_logging, get_logger

log = get_logger("heartbeat")
THRESHOLD_HOURS = 26


def main() -> int:
    configure_logging(run_id=str(uuid.uuid4()))
    db = DB()

    rows = (
        db._client.table("pipeline_health")
        .select("*")
        .eq("workflow", "eod")
        .eq("status", "SUCCESS")
        .order("started_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )

    now = datetime.now(UTC)
    if not rows:
        log.error("heartbeat_no_eod_ever")
        db.upsert(
            "pipeline_health",
            [
                {
                    "run_id": str(uuid.uuid4()),
                    "workflow": "eod",
                    "status": "DELAYED",
                    "started_at": now.isoformat(),
                    "finished_at": now.isoformat(),
                    "duration_seconds": 0,
                    "rows_processed": 0,
                    "error_message": "no EOD run ever recorded",
                }
            ],
            on_conflict="run_id",
        )
        return 1

    last = datetime.fromisoformat(rows[0]["started_at"].replace("Z", "+00:00"))
    age_h = (now - last).total_seconds() / 3600.0
    log.info("heartbeat_check", last_eod=str(last), age_hours=round(age_h, 2))

    if age_h > THRESHOLD_HOURS:
        db.upsert(
            "pipeline_health",
            [
                {
                    "run_id": str(uuid.uuid4()),
                    "workflow": "eod",
                    "status": "DELAYED",
                    "started_at": now.isoformat(),
                    "finished_at": now.isoformat(),
                    "duration_seconds": 0,
                    "rows_processed": 0,
                    "error_message": f"last EOD {age_h:.1f}h ago (>{THRESHOLD_HOURS}h)",
                }
            ],
            on_conflict="run_id",
        )
        log.error("heartbeat_delayed", age_hours=age_h)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
