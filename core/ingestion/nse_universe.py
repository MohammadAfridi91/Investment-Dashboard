from __future__ import annotations

import io
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from core.database.client import DB
from core.ingestion.base import Ingestor, IngestResult
from core.utils.checksums import sha256_bytes
from core.utils.logging import get_logger
from core.utils.normalization import strip_column_names

log = get_logger("ingest.universe")

NIFTY500_URL = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
MIDCAP150_URL = "https://archives.nseindia.com/content/indices/ind_niftymidcap150list.csv"
SMALLCAP250_URL = "https://archives.nseindia.com/content/indices/ind_niftysmallcap250list.csv"

BFSI_INDUSTRY_EXACT = {
    "Banks",
    "Financial Technology (Fintech)",
    "Finance",
    "Insurance",
    "Asset Management Company",
    "Investment Company",
    "Housing Finance",
    "Other Financial Services",
    "Financial Services",
    "Private Sector Bank",
    "Public Sector Bank",
    "Non Banking Financial Company (NBFC)",
    "Housing Finance Company",
    "Life Insurance",
    "General Insurance",
    "Financial Institution",
    "Broking & Allied Services",
}
BFSI_REGEX = re.compile(
    r"(Bank|Finance|Financial|Insurance|Asset Management|Housing Fin|"
    r"Investment|Broking|Capital Market)",
    re.IGNORECASE,
)


def is_bfsi(industry: str | None, sector: str | None) -> bool:
    for val in (industry or "", sector or ""):
        if val in BFSI_INDUSTRY_EXACT:
            return True
        if BFSI_REGEX.search(val):
            return True
    return False


class NSEUniverseIngestor(Ingestor):
    SOURCE = "nse_universe"
    SCHEDULE = "WEEKLY"

    def __init__(self, http: Any, db: DB, config: Any) -> None:
        self.http = http
        self.db = db
        self.config = config

    def _fetch_csv(self, url: str) -> pd.DataFrame:
        raw = self.http.get(url)
        df = pd.read_csv(io.BytesIO(raw))
        df.columns = strip_column_names(list(df.columns))
        return df

    def fetch_all(self) -> dict[str, dict[str, Any]]:
        sym_to_sector: dict[str, str] = {}
        mapping_file = getattr(
            getattr(self.config, "sector_rs", None),
            "mapping_file",
            "config/industry_mappings.json",
        )
        try:
            p = Path(mapping_file)
            if not p.is_file():
                p = Path(__file__).resolve().parents[2] / mapping_file
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8"))
                for sec_name, sym_list in data.items():
                    for s in sym_list:
                        sym_to_sector[s.strip()] = sec_name.strip()
        except Exception:
            pass

        frames = {
            "n500": self._fetch_csv(NIFTY500_URL),
            "mid150": self._fetch_csv(MIDCAP150_URL),
            "small250": self._fetch_csv(SMALLCAP250_URL),
        }
        merged: dict[str, dict[str, Any]] = {}
        for key, df in frames.items():
            for _, r in df.iterrows():
                sym = str(r["Symbol"]).strip()
                entry = merged.setdefault(
                    sym,
                    {
                        "symbol": sym,
                        "company_name": str(r["Company Name"]).strip(),
                        "isin": str(r["ISIN Code"]).strip(),
                        "sector": sym_to_sector.get(sym)
                        or str(r.get("Industry", "")).strip()
                        or "Diversified",
                        "industry": str(r.get("Industry", "")).strip(),
                        "is_bfsi": False,
                        "is_fno": False,
                        "is_nifty500": False,
                        "is_midsmall400": False,
                    },
                )
                if key == "n500":
                    entry["is_nifty500"] = True
                elif key in ("mid150", "small250"):
                    entry["is_midsmall400"] = True
        return merged

    def run(self, target_date: date) -> IngestResult:
        try:
            merged = self.fetch_all()
        except Exception as e:
            log.error("universe_fetch_failed", error=str(e))
            return IngestResult(self.SOURCE, status="FAILED", error=str(e))

        all_rows = list(merged.values())
        # Enforce Non-BFSI hard exclusion (AC4): discard BFSI stocks before writing to universe
        rows = [r for r in all_rows if not is_bfsi(r.get("industry"), r.get("sector"))]
        for r in rows:
            r["is_bfsi"] = False

        try:
            n = self.db.upsert("universe", rows, on_conflict="symbol")
        except Exception as e:
            log.error("universe_upsert_failed", error=str(e))
            return IngestResult(self.SOURCE, status="FAILED", error=str(e))

        log.info(
            "universe_done", total=len(rows), upserted=n, excluded_bfsi=len(all_rows) - len(rows)
        )
        return IngestResult(
            self.SOURCE,
            status="SUCCESS",
            target_date=target_date,
            rows_fetched=len(all_rows),
            rows_valid=len(rows),
            rows_rejected=len(all_rows) - len(rows),
            rows_upserted=n,
            rows_written=n,
            checksum=sha256_bytes(str(sorted(merged.keys())).encode()),
        )
