from __future__ import annotations

import json
import re
import time
from datetime import date, datetime
from typing import Any, cast

from core.config import Config
from core.database.client import DB
from core.ingestion.base import Ingestor, IngestResult
from core.utils.checksums import sha256_bytes
from core.utils.logging import get_logger

log = get_logger("ingest.bse")

BSE_API_CAT30 = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?strCat=30"
BSE_API_CAT17 = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?strCat=17"
BSE_API_CATBM = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?strCat=BM"

REGULATORY_RE = re.compile(
    r"(SEBI|REGULATORY|FORENSIC|SPECIAL AUDIT|SHOW CAUSE|INVESTIGATION|INSPECTION|DISGORGEMENT)",
    re.IGNORECASE,
)
AUDITOR_RESIGN_RE = re.compile(
    r"(resignation of statutory auditor|cessation of auditor|resignation of auditor)",
    re.IGNORECASE,
)
AUDITOR_QUAL_RE = re.compile(
    r"(qualified opinion|modified opinion|adverse opinion|disclaimer of opinion)",
    re.IGNORECASE,
)
CARO_RE = re.compile(
    r"(adverse|qualified|material uncertainty|going concern|title deeds not held|"
    r"physical verification not conducted|inventory discrepancy)",
    re.IGNORECASE,
)
CFO_RESIGN_RE = re.compile(r"(cfo resignation|resignation of cfo|chief financial officer)", re.IGNORECASE)
CS_RESIGN_RE = re.compile(r"(cs resignation|resignation of company secretary|company secretary)", re.IGNORECASE)
RAID_RE = re.compile(r"(gst search|gst raid|it raid|income tax search|ed raid|enforcement directorate)", re.IGNORECASE)


def _parse_bse_date(dt_str: Any) -> date | None:
    if not dt_str:
        return None
    val = str(dt_str).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


class BSEAnnouncementsIngestor(Ingestor):
    SOURCE = "bse_announcements"
    SCHEDULE = "EOD"

    def __init__(self, http: Any, db: DB, config: Config) -> None:
        self.http = http
        self.db = db
        self.config = config

    def _match_symbol(self, longname: str, name_map: dict[str, str]) -> str | None:
        norm = re.sub(r"[^\w\s]", "", longname.upper()).strip()
        # Direct lookup
        if norm in name_map:
            return name_map[norm]
        # Partial match
        for k, sym in name_map.items():
            if k in norm or norm in k:
                return sym
        return None

    def _fetch_category(
        self, base_url: str, target_date: date | None = None
    ) -> list[dict[str, Any]]:
        delay_s = float(self.config.ingestion.request_delay_bse_api_ms) / 1000.0
        time.sleep(delay_s)
        url = base_url
        if target_date:
            dt_str = target_date.strftime("%Y%m%d")
            sep = "&" if "?" in base_url else "?"
            url = f"{base_url}{sep}strPrevDate={dt_str}&strToDate={dt_str}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bseindia.com/",
            "Origin": "https://www.bseindia.com",
            "Accept": "application/json, text/plain, */*",
        }
        try:
            try:
                raw = cast(bytes, self.http.get(url, headers=headers))
            except TypeError:
                raw = cast(bytes, self.http.get(url))
            data = json.loads(raw.decode("utf-8-sig", errors="ignore"))
            if isinstance(data, dict) and "Table" in data and isinstance(data["Table"], list):
                return cast(list[dict[str, Any]], data["Table"])
            return []
        except Exception as e:
            log.warning("bse_fetch_category_failed", url=url, error=str(e))
            return []

    def classify_announcements(
        self,
        items: list[dict[str, Any]],
        target_date: date,
        name_map: dict[str, str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        gov_events: list[dict[str, Any]] = []
        auditor_rows: list[dict[str, Any]] = []

        tier1_patterns = [
            re.compile(r"\b" + re.escape(aud.strip()) + r"\b", re.IGNORECASE)
            for aud in self.config.tier1_auditors
        ]

        for it in items:
            longname = str(it.get("SLONGNAME", "")).strip()
            sym = self._match_symbol(longname, name_map)
            if not sym:
                continue

            event_dt = _parse_bse_date(it.get("DT_TM")) or target_date
            sub = str(it.get("NEWS_SUB", "")).strip()
            headline = str(it.get("HEADLINE", "")).strip()
            text = f"{sub} {headline}"

            # 1. Auditor events
            is_auditor_resign = bool(AUDITOR_RESIGN_RE.search(text))
            is_auditor_qual = bool(AUDITOR_QUAL_RE.search(text))
            is_caro = bool(CARO_RE.search(text))

            if is_auditor_resign or is_auditor_qual or is_caro or "statutory auditor" in text.lower():
                is_t1 = any(p.search(text) for p in tier1_patterns)
                auditor_rows.append(
                    {
                        "symbol": sym,
                        "fiscal_year": event_dt.year,
                        "auditor_firm": headline[:100],
                        "is_tier1": is_t1,
                        "mid_term_resignation": is_auditor_resign,
                        "resignation_date": event_dt.isoformat() if is_auditor_resign else None,
                        "has_qualified_opinion": is_auditor_qual,
                        "qualification_notes": headline if is_auditor_qual else None,
                        "caro_qualified": is_caro,
                        "non_audit_fee_ratio": None,
                    }
                )

            # 2. Fatal & Regulatory Governance Events
            event_type: str | None = None
            severity = "MEDIUM"

            if RAID_RE.search(text):
                event_type = "GST_RAID" if "gst" in text.lower() else "IT_RAID"
                severity = "FATAL"
            elif CFO_RESIGN_RE.search(text):
                event_type = "CFO_RESIGN"
                severity = "FATAL"
            elif CS_RESIGN_RE.search(text):
                event_type = "CS_RESIGN"
                severity = "HIGH"
            elif REGULATORY_RE.search(text):
                event_type = "SEBI_REGULATORY"
                severity = "HIGH"
            elif is_auditor_resign:
                event_type = "AUDITOR_RESIGNATION"
                severity = "FATAL"

            if event_type:
                gov_events.append(
                    {
                        "symbol": sym,
                        "event_date": event_dt.isoformat(),
                        "event_type": event_type,
                        "severity": severity,
                        "details": text[:500],
                        "source": "bse_api",
                        "source_url": str(it.get("ATTACHMENTNAME") or ""),
                    }
                )

        return gov_events, auditor_rows

    def run(self, target_date: date) -> IngestResult:
        t0 = self._timer()

        # Build name mapping from universe
        univ = self.db.select("universe", columns="symbol,company_name")
        name_map: dict[str, str] = {}
        for u in univ:
            sym = u["symbol"]
            cname = re.sub(r"[^\w\s]", "", str(u.get("company_name", "")).upper()).strip()
            if cname:
                name_map[cname] = sym
            name_map[sym] = sym

        items_30 = self._fetch_category(BSE_API_CAT30, target_date)
        items_17 = self._fetch_category(BSE_API_CAT17, target_date)
        items_bm = self._fetch_category(BSE_API_CATBM, target_date)
        all_items = items_30 + items_17 + items_bm

        gov_events, auditor_rows = self.classify_announcements(all_items, target_date, name_map)

        written_gov = 0
        written_aud = 0

        if gov_events:
            try:
                written_gov = self.db.upsert(
                    "governance_events",
                    gov_events,
                    on_conflict="symbol,event_date,event_type",
                )
            except Exception as e:
                log.error("bse_gov_events_upsert_failed", error=str(e))

        if auditor_rows:
            try:
                written_aud = self.db.upsert(
                    "auditor_history",
                    auditor_rows,
                    on_conflict="symbol,fiscal_year",
                )
            except Exception as e:
                log.error("bse_auditor_history_upsert_failed", error=str(e))

        dur_ms = int((self._timer() - t0) * 1000)
        total_written = written_gov + written_aud
        checksum = sha256_bytes(str(len(all_items)).encode())
        log.info(
            "bse_announcements_done",
            total=len(all_items),
            gov=written_gov,
            auditor=written_aud,
            duration_ms=dur_ms,
        )
        return IngestResult(
            self.SOURCE,
            status="SUCCESS",
            target_date=target_date,
            rows_fetched=len(all_items),
            rows_valid=len(gov_events) + len(auditor_rows),
            rows_upserted=total_written,
            rows_written=total_written,
            duration_ms=dur_ms,
            checksum=checksum,
            extras={"gov_events": written_gov, "auditor_rows": written_aud},
        )
