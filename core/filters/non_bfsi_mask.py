"""
Layer 1: non-BFSI hard exclusion.

Pulled forward from its Week 4 slot in the plan, because nse_universe.py
needs is_bfsi() to tag rows at ingestion time. apply_non_bfsi_mask() and
enforce_non_bfsi() are the Week-4-scoped pieces (used by the actual
filtering pipeline, not ingestion) -- included here now since the file
is small and fully specified, so there's nothing left to add later.
"""
import re

BFSI_INDUSTRY_EXACT = {
    'Banks', 'Financial Technology (Fintech)', 'Finance', 'Insurance',
    'Asset Management Company', 'Investment Company', 'Housing Finance',
    'Other Financial Services', 'Financial Services',
    'Private Sector Bank', 'Public Sector Bank',
    'Non Banking Financial Company (NBFC)', 'Housing Finance Company',
    'Life Insurance', 'General Insurance', 'Financial Institution',
    'Broking & Allied Services'
}

BFSI_REGEX = re.compile(
    r'(Bank|Finance|Financial|Insurance|Asset Management|Housing Fin|'
    r'Investment|Broking|Capital Market)',
    re.IGNORECASE
)


def is_bfsi(industry: str | None, sector: str | None) -> bool:
    # Strict: any hit in either field = BFSI (pre-flight D7)
    for val in (industry or '', sector or ''):
        if val in BFSI_INDUSTRY_EXACT:
            return True
        if BFSI_REGEX.search(val):
            return True
    return False


def apply_non_bfsi_mask(rows: list[dict]) -> list[dict]:
    return [r for r in rows if not is_bfsi(r.get('Industry'), r.get('Sector'))]


class BFSIViolationError(Exception):
    pass


def enforce_non_bfsi(rows: list[dict]) -> list[dict]:
    for r in rows:
        if r.get('is_bfsi'):
            raise BFSIViolationError(f"BFSI row reached Layer 2: {r['symbol']}")
    return rows
