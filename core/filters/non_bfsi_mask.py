from __future__ import annotations

import re
from typing import Any

BFSI_INDUSTRY_EXACT: set[str] = {
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

BFSI_REGEX: re.Pattern[str] = re.compile(
    r"(Bank|Finance|Financial|Insurance|Asset Management|Housing Fin|"
    r"Investment|Broking|Capital Market)",
    re.IGNORECASE,
)


def is_bfsi(industry: str | None, sector: str | None) -> bool:
    """Check if industry or sector matches BFSI exact set or regex pattern."""
    for val in (industry or "", sector or ""):
        if not val:
            continue
        if val in BFSI_INDUSTRY_EXACT:
            return True
        if BFSI_REGEX.search(val):
            return True
    return False


def apply_non_bfsi_mask(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter out BFSI rows from input list."""
    return [
        r
        for r in rows
        if not is_bfsi(
            r.get("Industry") or r.get("industry"),
            r.get("Sector") or r.get("sector"),
        )
    ]


class BFSIViolation(Exception):  # noqa: N818
    """Raised when a BFSI row reaches Layer 2 evaluation."""

    pass


def enforce_non_bfsi(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enforce that zero BFSI rows are present. Raises BFSIViolation if found."""
    for r in rows:
        if r.get("is_bfsi") or is_bfsi(
            r.get("Industry") or r.get("industry"),
            r.get("Sector") or r.get("sector"),
        ):
            raise BFSIViolation(f"BFSI row reached Layer 2: {r.get('symbol')}")
    return rows
