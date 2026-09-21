from __future__ import annotations

import io
from datetime import date, datetime
from typing import Any, cast

import pandas as pd

from core.config import Config
from core.database.client import DB
from core.ingestion.base import Ingestor, IngestResult
from core.utils.checksums import sha256_bytes
from core.utils.logging import get_logger
from core.utils.normalization import strip_column_names

log = get_logger("ingest.market_flow")

FIIDII_URL = "https://archives.nseindia.com/content/equities/fiidii_trading_activity.csv"


def _parse_fii_date(s: Any) -> date | None:
    if s is None:
        return None
    val = str(s).strip()
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


class NSEMarketFlowIngestor(Ingestor):
    SOURCE = "nse_market_flow"
    SCHEDULE = "EOD"

    def __init__(self, http: Any, db: DB, config: Config) -> None:
        self.http = http
        self.db = db
        self.config = config

    def parse(self, raw: bytes, target_date: date) -> tuple[float | None, float | None]:
        df = pd.read_csv(io.BytesIO(raw), dtype=str, skipinitialspace=True)
        df.columns = strip_column_names(list(df.columns))

        cat_col = next((c for c in df.columns if "CATEGORY" in c.upper()), None)
        date_col = next((c for c in df.columns if "DATE" in c.upper()), None)
        net_col = next((c for c in df.columns if "NET" in c.upper()), None)

        if not cat_col or not net_col:
            raise ValueError(f"fiidii CSV missing required columns: {list(df.columns)}")

        fii_net: float | None = None
        dii_net: float | None = None

        for _, r in df.iterrows():
            if date_col:
                row_date = _parse_fii_date(r[date_col])
                if row_date and row_date != target_date:
                    continue

            cat = str(r[cat_col]).strip().upper()
            try:
                val = float(str(r[net_col]).replace(",", "").strip())
            except (ValueError, TypeError):
                continue

            if "FII" in cat or "FPI" in cat:
                fii_net = val
            elif "DII" in cat:
                dii_net = val

        return fii_net, dii_net

    def run(self, target_date: date) -> IngestResult:
        t0 = self._timer()
        try:
            raw = cast(bytes, self.http.get(FIIDII_URL))
        except Exception as e:
            log.error("market_flow_fetch_failed", error=str(e))
            return IngestResult(self.SOURCE, status="FAILED", error=str(e))

        checksum = sha256_bytes(raw)
        try:
            fii_net, dii_net = self.parse(raw, target_date)
        except Exception as e:
            log.error("market_flow_parse_failed", error=str(e))
            return IngestResult(self.SOURCE, status="FAILED", checksum=checksum, error=str(e))

        if fii_net is None and dii_net is None:
            log.warning("market_flow_no_data_for_date", date=str(target_date))
            return IngestResult(self.SOURCE, status="SKIPPED", checksum=checksum, error="no FII/DII rows for date")

        regime_update: dict[str, Any] = {
            "trade_date": target_date.isoformat(),
            "fii_cash_net_cr": fii_net,
            "dii_cash_net_cr": dii_net,
        }

        try:
            self.db.upsert("market_regime", [regime_update], on_conflict="trade_date")
        except Exception as e:
            log.error("market_flow_upsert_failed", error=str(e))
            return IngestResult(self.SOURCE, status="FAILED", checksum=checksum, error=str(e))

        dur_ms = int((self._timer() - t0) * 1000)
        log.info("market_flow_done", fii=fii_net, dii=dii_net, duration_ms=dur_ms)
        return IngestResult(
            self.SOURCE,
            status="SUCCESS",
            target_date=target_date,
            rows_fetched=2,
            rows_valid=1,
            rows_upserted=1,
            rows_written=1,
            duration_ms=dur_ms,
            checksum=checksum,
        )
