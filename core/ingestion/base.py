from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from core.utils.logging import get_logger

log = get_logger("ingestion")


@dataclass
class IngestResult:
    source: str
    status: str = "SUCCESS"
    target_date: date | None = None
    rows_fetched: int = 0
    rows_upserted: int = 0
    rows_valid: int = 0
    rows_rejected: int = 0
    rows_written: int = 0
    duration_ms: int = 0
    checksum: str = ""
    raw_checksum: str = ""
    error: str | None = None
    errors: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)


class Ingestor(ABC):
    SOURCE: str
    SCHEDULE: str

    @abstractmethod
    def run(self, target_date: date) -> IngestResult: ...

    def _timer(self) -> float:
        return time.monotonic()

    def run_safe(self, target_date: date) -> IngestResult:
        """Run the ingestor, converting any unexpected exception into a FAILED result.

        Guarantees one crashing source can never abort the rest of the pipeline and that every
        result carries a duration.
        """
        started = self._timer()
        try:
            result = self.run(target_date)
        except Exception as exc:
            source = getattr(self, "SOURCE", type(self).__name__)
            log.exception("ingestor_crashed", source=source)
            return IngestResult(
                source=source,
                status="FAILED",
                target_date=target_date,
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=int((self._timer() - started) * 1000),
            )
        if not result.duration_ms:
            result.duration_ms = int((self._timer() - started) * 1000)
        return result
