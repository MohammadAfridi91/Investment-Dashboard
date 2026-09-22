from __future__ import annotations

import re
from datetime import date
from typing import Any, cast

from bs4 import BeautifulSoup

from core.config import Config
from core.database.client import DB
from core.ingestion.base import Ingestor, IngestResult
from core.utils.checksums import sha256_bytes
from core.utils.logging import get_logger

log = get_logger("ingest.gsec")

RBI_NSDP_URL = "https://www.rbi.org.in/Scripts/BS_NSDPDisplay.aspx?param=4"


class GSecYieldIngestor(Ingestor):
    SOURCE = "rbi_gsec_yield"
    SCHEDULE = "EOD"

    def __init__(self, http: Any, db: DB, config: Config) -> None:
        self.http = http
        self.db = db
        self.config = config

    def parse_html(self, raw_html: bytes) -> float | None:
        soup = BeautifulSoup(raw_html, "html.parser")
        for tr in soup.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if not cells or len(cells) > 20:
                continue
            header = cells[0].lower()
            if any(k in header for k in ("10-year", "10 year", "10 yr", "ten year")):
                for c in reversed(cells[1:]):
                    cleaned = re.sub(r"[^\d.]", "", c)
                    if cleaned:
                        try:
                            val = float(cleaned)
                            if 2.0 <= val <= 20.0:  # Sensible range for G-Sec yield in %
                                return round(val / 100.0, 4)
                        except ValueError:
                            continue
        return None

    def run(self, target_date: date) -> IngestResult:
        t0 = self._timer()
        try:
            raw = cast(bytes, self.http.get(RBI_NSDP_URL))
        except Exception as e:
            log.warning("gsec_fetch_failed", error=str(e))
            return IngestResult(self.SOURCE, status="FAILED", error=str(e))

        checksum = sha256_bytes(raw)
        gsec_val = self.parse_html(raw)

        if gsec_val is None:
            log.warning("gsec_yield_not_found_in_html")
            return IngestResult(
                self.SOURCE,
                status="SKIPPED",
                checksum=checksum,
                error="could not parse 10Y yield from RBI page",
            )

        regime_update: dict[str, Any] = {
            "trade_date": target_date.isoformat(),
            "gsec_10y_yield": gsec_val,
        }

        try:
            self.db.upsert("market_regime", [regime_update], on_conflict="trade_date")
        except Exception as e:
            log.error("gsec_upsert_failed", error=str(e))
            return IngestResult(self.SOURCE, status="FAILED", checksum=checksum, error=str(e))

        dur_ms = int((self._timer() - t0) * 1000)
        log.info("gsec_done", yield_val=gsec_val, duration_ms=dur_ms)
        return IngestResult(
            self.SOURCE,
            status="SUCCESS",
            target_date=target_date,
            rows_fetched=1,
            rows_valid=1,
            rows_upserted=1,
            rows_written=1,
            duration_ms=dur_ms,
            checksum=checksum,
            extras={"gsec_10y_yield": gsec_val},
        )
