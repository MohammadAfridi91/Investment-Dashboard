"""
core/ingestion/nse_universe.py  (Source: N8, N9, N10)

Fetches the three constituent lists and unions them into `universe`.

Domain fix: the plan's URLs use archives.nseindia.com, which NSE migrated
away from. The live path is nsearchives.nseindia.com (same file layout).

fetch() pulls all three CSVs and joins them with a boundary marker so the
whole run gets a single reproducible checksum (any of the three sources
changing changes the checksum); parse() splits back apart on that marker.
"""
from datetime import date
from typing import Any

from core.filters.non_bfsi_mask import is_bfsi
from core.ingestion.base import Ingestor
from core.utils.http import fetch as http_fetch
from core.utils.http import get_session

BASE_URL = "https://nsearchives.nseindia.com/content/indices"

CONSTITUENT_FILES = {
    "ind_nifty500list.csv": "is_nifty500",
    "ind_niftymidcap150list.csv": "is_midsmall400",
    "ind_niftysmallcap250list.csv": "is_midsmall400",
}

_BOUNDARY = b"\n===NSE_FILE_BOUNDARY===\n"


class NSEUniverseIngestor(Ingestor):
    SOURCE = "nse_universe"
    SCHEDULE = "weekly (Monday 08:00 IST); Week 1: on-demand via CLI"

    def fetch(self, target_date: date) -> bytes:
        session = get_session()
        blobs = []
        for filename in CONSTITUENT_FILES:
            url = f"{BASE_URL}/{filename}"
            content = http_fetch(session, url, delay_ms=500)
            blobs.append(filename.encode() + b"\n" + content)
        return _BOUNDARY.join(blobs)

    def parse(self, raw: bytes, target_date: date) -> list[dict[str, Any]]:
        import csv
        import io

        merged: dict[str, dict[str, Any]] = {}

        for blob in raw.split(_BOUNDARY):
            filename, _, csv_bytes = blob.partition(b"\n")
            filename = filename.decode().strip()
            flag_field = CONSTITUENT_FILES[filename]

            text = csv_bytes.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                symbol = (row.get("Symbol") or "").strip()
                if not symbol:
                    continue
                industry = (row.get("Industry") or "").strip()
                # NSE's constituent CSVs don't carry a separate "Sector"
                # column distinct from Industry -- Industry is the only
                # classification field available here, so is_bfsi() gets
                # it twice (matches the function's (industry, sector)
                # signature without inventing a sector value).
                entry = merged.setdefault(symbol, {
                    "symbol": symbol,
                    "company_name": (row.get("Company Name") or "").strip(),
                    "isin": (row.get("ISIN Code") or "").strip(),
                    "sector": industry,
                    "industry": industry,
                    "is_nifty500": False,
                    "is_midsmall400": False,
                    "is_fno": False,
                })
                entry[flag_field] = True
                # Keep the most complete name/ISIN if a later file has gaps
                if not entry["company_name"] and row.get("Company Name"):
                    entry["company_name"] = row["Company Name"].strip()
                if not entry["isin"] and row.get("ISIN Code"):
                    entry["isin"] = row["ISIN Code"].strip()

        rows = list(merged.values())
        for r in rows:
            r["is_bfsi"] = is_bfsi(r["industry"], r["sector"])
        return rows

    def validate(
        self, rows: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        valid, rejected = [], []
        for r in rows:
            errs = []
            if not r.get("symbol"):
                errs.append("missing symbol")
            if not r.get("isin") or len(r["isin"]) != 12:
                errs.append(f"malformed ISIN: {r.get('isin')!r}")
            if not r.get("company_name"):
                errs.append("missing company_name")
            if errs:
                rejected.append({**r, "_validation_errors": errs})
            else:
                valid.append(r)
        return valid, rejected

    def upsert(self, rows: list[dict[str, Any]]) -> int:
        from core.database.client import get_client

        client = get_client()
        return client.bulk_upsert("universe", rows, conflict_cols=["symbol"])
