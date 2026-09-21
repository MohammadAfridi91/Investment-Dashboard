from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database.client import DB

EXPECTED_TABLES = [
    "universe",
    "daily_prices",
    "benchmark_prices",
    "sector_indices",
    "corporate_events",
    "corporate_actions",
    "derivative_metrics",
    "technical_indicators",
    "surveillance_registry",
    "auditor_history",
    "forensic_financials",
    "institutional_deals",
    "market_regime",
    "governance_events",
    "trade_check_cards",
    "sebi_compliance_log",
    "pipeline_health",
]


def check_tables(db: DB) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for table in EXPECTED_TABLES:
        try:
            db.select(table, limit=1)
        except Exception as e:
            missing.append(f"{table} ({e})")
    return len(missing) == 0, missing


def check_bfsi_exclusion(db: DB) -> tuple[bool, int]:
    try:
        bfsi_rows = db.select("universe", columns="symbol", filters={"is_bfsi": True})
        count = len(bfsi_rows)
        return count == 0, count
    except Exception:
        return False, -1


def main() -> int:
    print("=" * 60)
    print("Dalal Street Engine — Acceptance Criteria Verification")
    print("=" * 60)

    try:
        db = DB()
    except Exception as e:
        print(f"[FAIL] Could not connect to Supabase: {e}")
        return 1

    # AC5: Tables check
    tables_ok, missing = check_tables(db)
    if tables_ok:
        print(f"[PASS] AC5: All {len(EXPECTED_TABLES)} tables verified in Supabase.")
    else:
        print(f"[FAIL] AC5: Missing or inaccessible tables: {missing}")

    # AC4: BFSI check
    bfsi_ok, count = check_bfsi_exclusion(db)
    if count == -1:
        print("[FAIL] AC4: Could not query universe table.")
    elif bfsi_ok:
        print(f"[PASS] AC4: BFSI exclusion verified. Count of is_bfsi=TRUE is {count}.")
    else:
        print(f"[FAIL] AC4: Expected 0 BFSI rows in universe, found {count}.")

    print("=" * 60)
    all_ok = tables_ok and bfsi_ok
    print(f"Overall Result: {'ALL CRITERIA PASSED' if all_ok else 'SOME CHECKS FAILED'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
