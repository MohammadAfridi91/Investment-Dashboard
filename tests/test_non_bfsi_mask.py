from __future__ import annotations

from typing import Any

import pytest

from core.filters.non_bfsi_mask import (
    BFSIViolation,
    apply_non_bfsi_mask,
    enforce_non_bfsi,
    is_bfsi,
)


def test_is_bfsi_exact_matches() -> None:
    assert is_bfsi("Banks", "Financial Services") is True
    assert is_bfsi("Financial Technology (Fintech)", "Financial Services") is True
    assert is_bfsi("Housing Finance Company", "Finance") is True
    assert is_bfsi("Life Insurance", "Insurance") is True
    assert is_bfsi("Asset Management Company", "Financial Services") is True
    assert is_bfsi("Broking & Allied Services", "Financial Services") is True


def test_is_bfsi_regex_matches() -> None:
    assert is_bfsi("Small Finance Bank", "Banks") is True
    assert is_bfsi("Capital Market Solutions", "Services") is True
    assert is_bfsi("General Insurance Provider", "Insurance") is True
    assert is_bfsi(None, "Housing Finance") is True
    assert is_bfsi("Private Sector Bank", None) is True


def test_non_bfsi_industries_pass() -> None:
    assert is_bfsi("Computers - Software", "Information Technology") is False
    assert is_bfsi("Pharmaceuticals", "Healthcare") is False
    assert is_bfsi("Passenger Cars & Utility Vehicles", "Automobile and Auto Components") is False
    assert is_bfsi("Iron & Steel", "Metals & Mining") is False
    assert is_bfsi("Power Generation", "Power") is False
    assert is_bfsi(None, None) is False


def test_apply_non_bfsi_mask() -> None:
    rows = [
        {"symbol": "TCS", "industry": "Computers - Software", "sector": "Information Technology"},
        {"symbol": "HDFCBANK", "industry": "Private Sector Bank", "sector": "Financial Services"},
        {"symbol": "INFY", "industry": "Computers - Software", "sector": "Information Technology"},
        {"symbol": "SBIN", "industry": "Public Sector Bank", "sector": "Financial Services"},
        {"symbol": "RELIANCE", "industry": "Refineries", "sector": "Oil Gas & Consumable Fuels"},
    ]
    filtered = apply_non_bfsi_mask(rows)
    symbols = [r["symbol"] for r in filtered]
    assert symbols == ["TCS", "INFY", "RELIANCE"]


def test_bfsi_hard_reject_raises_violation() -> None:
    """Verification Plan Test 2: Inject test BFSI row -> BFSIViolation raised."""
    # Valid non-BFSI rows pass through
    clean_rows = [
        {"symbol": "TCS", "industry": "Computers - Software", "sector": "IT"},
        {"symbol": "INFY", "industry": "Computers - Software", "sector": "IT"},
    ]
    assert enforce_non_bfsi(clean_rows) == clean_rows

    # Injected BFSI row with explicit flag raises BFSIViolation
    poisoned_rows_flag = [
        {"symbol": "TCS", "industry": "Computers - Software", "sector": "IT"},
        {"symbol": "HDFCBANK", "is_bfsi": True},
    ]
    with pytest.raises(BFSIViolation) as exc_info:
        enforce_non_bfsi(poisoned_rows_flag)
    assert "HDFCBANK" in str(exc_info.value)

    # Injected BFSI row with BFSI industry name raises BFSIViolation
    poisoned_rows_industry: list[dict[str, Any]] = [
        {"symbol": "KOTAKBANK", "industry": "Private Sector Bank", "sector": "Financial Services"},
    ]
    with pytest.raises(BFSIViolation) as exc_info_ind:
        enforce_non_bfsi(poisoned_rows_industry)
    assert "KOTAKBANK" in str(exc_info_ind.value)
