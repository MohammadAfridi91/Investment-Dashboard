from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import UTC, date, datetime

from core.config import Config, load_config
from core.database.client import DB
from core.indicators.regime import update_daily_market_regime
from core.indicators.technicals import TechnicalIndicatorsComputer
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
from core.utils.trading_calendar import is_trading_day

log = get_logger("pipeline")


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


def run_eod(cfg: Config, db: DB, target_date: date, skip_ingestion: bool) -> int:
    total_rows = 0
    universe_count = len(db.select("universe", columns="symbol", limit=1))
    if not skip_ingestion and (target_date.weekday() == 0 or universe_count == 0):
        uni = NSEUniverseIngestor(
            PlainHttpClient(
                cfg.ingestion.user_agent,
                cfg.ingestion.request_delay_nse_archives_ms,
            ),
            db,
            cfg,
        )
        res = uni.run(target_date)
        log.info("universe_result", status=res.status, rows=res.rows_upserted)
        total_rows += res.rows_upserted

    if skip_ingestion:
        log.info("eod_skip_ingestion")
        return total_rows

    nse = NSEHttpClient(
        cfg.ingestion.user_agent,
        cfg.ingestion.request_delay_nse_archives_ms,
    )
    plain = PlainHttpClient(
        cfg.ingestion.user_agent,
        cfg.ingestion.request_delay_nse_archives_ms,
    )

    bc = NSEBhavcopyIngestor(nse, db, cfg).run(target_date)
    log.info("bhavcopy_result", status=bc.status, rows=bc.rows_upserted, error=bc.error)
    total_rows += bc.rows_upserted

    ip = NSEIndexPricesIngestor(nse, db, cfg).run(target_date)
    log.info("index_result", status=ip.status, rows=ip.rows_upserted, error=ip.error)
    total_rows += ip.rows_upserted

    deriv = NSEDerivativesIngestor(nse, db, cfg).run(target_date)
    log.info("derivatives_result", status=deriv.status, rows=deriv.rows_upserted, error=deriv.error)
    total_rows += deriv.rows_upserted

    surv = NSESurveillanceIngestor(plain, db, cfg).run(target_date)
    log.info("surveillance_result", status=surv.status, rows=surv.rows_upserted, error=surv.error)
    total_rows += surv.rows_upserted

    inst = NSEInstitutionalIngestor(plain, db, cfg).run(target_date)
    log.info("institutional_result", status=inst.status, rows=inst.rows_upserted, error=inst.error)
    total_rows += inst.rows_upserted

    flow = NSEMarketFlowIngestor(plain, db, cfg).run(target_date)
    log.info("market_flow_result", status=flow.status, rows=flow.rows_upserted, error=flow.error)
    total_rows += flow.rows_upserted

    actions = CorporateActionsIngestor(plain, db, cfg).run(target_date)
    log.info(
        "actions_result", status=actions.status, rows=actions.rows_upserted, error=actions.error
    )
    total_rows += actions.rows_upserted

    gsec = GSecYieldIngestor(plain, db, cfg).run(target_date)
    log.info("gsec_result", status=gsec.status, rows=gsec.rows_upserted, error=gsec.error)
    total_rows += gsec.rows_upserted

    bse = BSEAnnouncementsIngestor(plain, db, cfg).run(target_date)
    log.info("bse_result", status=bse.status, rows=bse.rows_upserted, error=bse.error)
    total_rows += bse.rows_upserted

    # Screener runs weekly or if financial table is empty
    fin_count = len(db.select("forensic_financials", columns="symbol", limit=1))
    if target_date.weekday() == 5 or fin_count == 0:
        scr = ScreenerCollector(plain, db, cfg).run(target_date)
        log.info("screener_result", status=scr.status, rows=scr.rows_upserted, error=scr.error)
        total_rows += scr.rows_upserted

    # Week 4: Market regime update & Technical indicators computation
    try:
        update_daily_market_regime(db, cfg, target_date)
    except Exception as e:
        log.error("market_regime_update_failed", error=str(e))

    try:
        tech_count = TechnicalIndicatorsComputer(db, cfg).run_for_date(target_date)
        total_rows += tech_count
        log.info("technicals_result", rows=tech_count)
    except Exception as e:
        log.error("technicals_computation_failed", error=str(e))

    # Week 5: Evaluate Tactical and Strategic Desks
    try:
        from core.compliance.sebi_ra import archive_card_report
        from core.engines.strategic_desk import StrategicDesk
        from core.engines.tactical_desk import TacticalDesk

        tactical_desk = TacticalDesk(db, cfg)
        strategic_desk = StrategicDesk(db, cfg)

        # Tactical Desk: Evaluate F&O non-BFSI universe
        fno_candidates = db.select(
            "universe", columns="symbol", filters={"is_fno": True, "is_bfsi": False}
        )
        card1_count = 0
        for cand in fno_candidates:
            sym = cand.get("symbol")
            if not sym:
                continue
            card1 = tactical_desk.evaluate_from_db(sym, target_date)
            if card1:
                archive_card_report(card1, db=db)
                card1_count += 1
        log.info("tactical_desk_result", cards_evaluated=card1_count)
        total_rows += card1_count

        # Strategic Desk: Evaluate Nifty 500 non-BFSI universe
        strat_candidates = db.select(
            "universe", columns="symbol", filters={"is_bfsi": False, "is_nifty500": True}
        )
        card2_count = 0
        for cand in strat_candidates:
            sym = cand.get("symbol")
            if not sym:
                continue
            card2 = strategic_desk.evaluate_from_db(sym, target_date)
            if card2:
                archive_card_report(card2, db=db)
                card2_count += 1
        log.info("strategic_desk_result", cards_evaluated=card2_count)
        total_rows += card2_count
    except Exception as e:
        log.error("desks_evaluation_failed", error=str(e))

    return total_rows


def run_premarket(cfg: Config, db: DB, target_date: date) -> int:
    plain = PlainHttpClient(
        cfg.ingestion.user_agent,
        cfg.ingestion.request_delay_nse_archives_ms,
    )
    surv = NSESurveillanceIngestor(plain, db, cfg).run(target_date)
    log.info(
        "premarket_surveillance_result",
        status=surv.status,
        rows=surv.rows_upserted,
        error=surv.error,
    )
    return surv.rows_upserted


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
    target_date = date.fromisoformat(date_str) if date_str else datetime.now(UTC).date()
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
    status = "SUCCESS"
    err: str | None = None
    rows = 0

    if not is_trading_day(target_date, [h.date for h in cfg.nse_holidays]):
        log.info("non_trading_day_skip", date=str(target_date))
        _record_health(
            db,
            run_id,
            args.mode,
            "SKIPPED",
            started,
            datetime.now(UTC),
            0,
            "non-trading day",
        )
        return 0

    try:
        if args.mode == "eod":
            rows = run_eod(cfg, db, target_date, skip_ingestion)
        else:
            rows = run_premarket(cfg, db, target_date)
    except Exception as e:
        log.exception("pipeline_failed")
        status = "FAILED"
        err = str(e)

    finished = datetime.now(UTC)
    _record_health(db, run_id, args.mode, status, started, finished, rows, err)
    log.info("pipeline_end", status=status, rows=rows)
    return 0 if status == "SUCCESS" else 1


if __name__ == "__main__":
    sys.exit(main())
