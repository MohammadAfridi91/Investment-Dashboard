from __future__ import annotations

import io
import re
from datetime import date
from typing import Any, cast

import pandas as pd

from core.config import Config
from core.database.client import DB
from core.ingestion.base import Ingestor, IngestResult
from core.utils.checksums import sha256_bytes
from core.utils.logging import get_logger
from core.utils.normalization import strip_column_names

log = get_logger("ingest.surveillance")

ASM_LONG_TERM_URL = "https://archives.nseindia.com/content/equities/eq_asm_long_term.csv"
ASM_SHORT_TERM_URL = "https://archives.nseindia.com/content/equities/eq_asm_short_term.csv"
GSM_URL = "https://archives.nseindia.com/content/equities/eq_gsm.csv"


def _extract_stage(val: Any) -> int:
    if val is None:
        return 0
    s = str(val).strip().upper()
    if not s:
        return 0
    # Roman numerals check (IV, III, II, I)
    if "IV" in s:
        return 4
    if "III" in s:
        return 3
    if "II" in s:
        return 2
    if "I" in s:
        return 1
    # Digit check
    m = re.search(r"\d+", s)
    if m:
        return int(m.group(0))
    return 1


class NSESurveillanceIngestor(Ingestor):
    SOURCE = "nse_surveillance"
    SCHEDULE = "PREMARKET"

    def __init__(self, http: Any, db: DB, config: Config) -> None:
        self.http = http
        self.db = db
        self.config = config

    def _fetch_csv_safely(self, url: str) -> bytes | None:
        try:
            return cast(bytes, self.http.get(url))
        except Exception as e:
            log.warning("surveillance_fetch_failed", url=url, error=str(e))
            return None

    def parse_stage_csv(self, raw: bytes | None) -> dict[str, int]:
        if not raw:
            return {}
        try:
            df = pd.read_csv(io.BytesIO(raw), dtype=str, skipinitialspace=True)
            df.columns = strip_column_names(list(df.columns))
            sym_col = next((c for c in df.columns if "SYMBOL" in c.upper()), None)
            if not sym_col:
                return {}
            stage_col = next((c for c in df.columns if "STAGE" in c.upper()), None)

            result: dict[str, int] = {}
            for _, r in df.iterrows():
                sym = str(r[sym_col]).strip()
                if not sym:
                    continue
                stage_val = r[stage_col] if stage_col else 1
                result[sym] = _extract_stage(stage_val)
            return result
        except Exception as e:
            log.warning("surveillance_parse_stage_failed", error=str(e))
            return {}

    def run(self, target_date: date, t2t_symbols: set[str] | None = None) -> IngestResult:
        t0 = self._timer()
        raw_lt = self._fetch_csv_safely(ASM_LONG_TERM_URL)
        raw_st = self._fetch_csv_safely(ASM_SHORT_TERM_URL)
        raw_gsm = self._fetch_csv_safely(GSM_URL)

        asm_lt = self.parse_stage_csv(raw_lt)
        asm_st = self.parse_stage_csv(raw_st)
        gsm = self.parse_stage_csv(raw_gsm)
        t2t = t2t_symbols or set()

        # Combine all symbols mentioned in any surveillance list
        all_syms = set(asm_lt.keys()) | set(asm_st.keys()) | set(gsm.keys()) | t2t

        rows: list[dict[str, Any]] = []
        for sym in all_syms:
            asm_stage = max(asm_lt.get(sym, 0), asm_st.get(sym, 0))
            gsm_stage = gsm.get(sym, 0)
            is_t2t = sym in t2t

            rows.append(
                {
                    "symbol": sym,
                    "record_date": target_date.isoformat(),
                    "asm_stage": asm_stage,
                    "gsm_stage": gsm_stage,
                    "is_t2t": is_t2t,
                    "promoter_pledge_pct": 0.0,
                    "pledge_rising_2q": False,
                    "promoter_holding_pct": None,
                    "promoter_holding_change_4q": None,
                    "sast_sale_flag": False,
                    "days_to_earnings": 999,
                    "has_auditor_resignation": False,
                    "has_regulatory_raid": False,
                    "has_forensic_audit": False,
                }
            )

        known = {u["symbol"] for u in self.db.select("universe", columns="symbol")}
        valid_rows = [r for r in rows if r["symbol"] in known] if known else rows

        written = 0
        if valid_rows:
            try:
                written = self.db.upsert("surveillance_registry", valid_rows, on_conflict="symbol,record_date")
            except Exception as e:
                log.error("surveillance_upsert_failed", error=str(e))
                return IngestResult(self.SOURCE, status="FAILED", error=str(e))

        dur_ms = int((self._timer() - t0) * 1000)
        checksum = sha256_bytes(str(sorted(all_syms)).encode())
        log.info("surveillance_done", symbols=len(all_syms), written=written, duration_ms=dur_ms)
        return IngestResult(
            self.SOURCE,
            status="SUCCESS",
            target_date=target_date,
            rows_fetched=len(rows),
            rows_valid=len(valid_rows),
            rows_rejected=len(rows) - len(valid_rows),
            rows_upserted=written,
            rows_written=written,
            duration_ms=dur_ms,
            checksum=checksum,
        )
