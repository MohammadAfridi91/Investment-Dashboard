from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any


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
    def run(self, target_date: date) -> IngestResult:
        ...

    def _timer(self) -> float:
        return time.monotonic()
