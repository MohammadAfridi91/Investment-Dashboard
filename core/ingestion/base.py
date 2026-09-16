"""
Base ingestor contract.

`run()` implements the fetch -> checksum -> parse -> validate -> upsert
orchestration. The plan leaves `run()`'s body unspecified (just `...`) --
this is that implementation. Concrete ingestors only need to implement
fetch/parse/upsert, and override `validate()` when they have row-shape-
specific checks (nse_bhavcopy.py uses validate_ohlc from validation.py;
row shapes without OHLC fields, like nse_universe.py, can leave the
default pass-through in place or add their own simple checks).
"""
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from core.utils.checksums import sha256_hex

QUARANTINE_DIR = Path("data/errors")


@dataclass
class IngestResult:
    source: str
    target_date: date
    rows_fetched: int
    rows_valid: int
    rows_rejected: int
    rows_written: int
    duration_ms: int
    raw_checksum: str
    errors: list[str]


class Ingestor(ABC):
    SOURCE: str
    SCHEDULE: str

    @abstractmethod
    def fetch(self, target_date: date) -> bytes: ...

    @abstractmethod
    def parse(self, raw: bytes, target_date: date) -> list[dict[str, Any]]: ...

    @abstractmethod
    def upsert(self, rows: list[dict[str, Any]]) -> int: ...

    def fallback(self, target_date: date) -> bytes | None:
        return None

    def validate(
        self, rows: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Default: everything passes. Override for row-shape-specific
        checks. Returns (valid_rows, rejected_rows); each rejected row
        carries a '_validation_errors' key so the quarantine file records
        *why* it was rejected, not just that it was.
        """
        return rows, []

    def _write_quarantine(self, target_date: date, rejected: list[dict[str, Any]]) -> None:
        if not rejected:
            return
        QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
        path = QUARANTINE_DIR / f"quarantine_{self.SOURCE}_{target_date.isoformat()}.jsonl"
        with path.open("a") as f:
            for row in rejected:
                f.write(json.dumps(row, default=str) + "\n")

    def run(self, target_date: date) -> IngestResult:
        start = time.monotonic()
        errors: list[str] = []
        raw: bytes | None = None

        try:
            raw = self.fetch(target_date)
        except Exception as e:
            errors.append(f"fetch failed: {e}")
            try:
                raw = self.fallback(target_date)
                if raw is not None:
                    errors.append("primary fetch failed, used fallback source")
            except Exception as fe:
                errors.append(f"fallback failed: {fe}")

        if raw is None:
            return IngestResult(
                source=self.SOURCE, target_date=target_date,
                rows_fetched=0, rows_valid=0, rows_rejected=0, rows_written=0,
                duration_ms=int((time.monotonic() - start) * 1000),
                raw_checksum="", errors=errors or ["no data available from any source"],
            )

        raw_checksum = sha256_hex(raw)

        try:
            parsed = self.parse(raw, target_date)
        except Exception as e:
            errors.append(f"parse failed: {e}")
            return IngestResult(
                source=self.SOURCE, target_date=target_date,
                rows_fetched=0, rows_valid=0, rows_rejected=0, rows_written=0,
                duration_ms=int((time.monotonic() - start) * 1000),
                raw_checksum=raw_checksum, errors=errors,
            )

        rows_fetched = len(parsed)
        valid_rows, rejected_rows = self.validate(parsed)
        self._write_quarantine(target_date, rejected_rows)
        errors.extend(
            f"rejected {r.get('symbol', '?')}: {r.get('_validation_errors')}"
            for r in rejected_rows
        )

        rows_written = 0
        if valid_rows:
            try:
                rows_written = self.upsert(valid_rows)
            except Exception as e:
                errors.append(f"upsert failed: {e}")

        return IngestResult(
            source=self.SOURCE, target_date=target_date,
            rows_fetched=rows_fetched, rows_valid=len(valid_rows),
            rows_rejected=len(rejected_rows), rows_written=rows_written,
            duration_ms=int((time.monotonic() - start) * 1000),
            raw_checksum=raw_checksum, errors=errors,
        )
