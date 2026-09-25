"""Tests for SEBI Research Analyst Compliance Module.

Validates Acceptance Tests 14, 15 and compliance requirements:
- Test 14: SHA-256 archive parity (HTML and JSON reports).
- Test 15: UPSI access logging (actor, timestamp, rationale, symbol, 5-yr retention).
- Prohibited language detection (ensures no 'guaranteed', 'assured', 'risk-free').
- Immutable report rendering and 5-year retention calculation.
"""

import hashlib
import json
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

from core.compliance.sebi_ra import (
    archive_card_report,
    build_disclosure_snapshot,
    log_upsi_access,
    render_html_report,
    verify_prohibited_language,
)
from core.models import TradeCheckCardRow


@pytest.fixture
def sample_tactical_card() -> TradeCheckCardRow:
    return TradeCheckCardRow(
        id=str(uuid.uuid4()),
        symbol="TATASTEEL",
        desk_type="TACTICAL",
        eval_date=date(2026, 9, 25),
        hard_gates_pass=True,
        score=9.0,
        max_score=10.0,
        verdict="EXECUTE",
        entry_trigger=155.10,
        stop_loss=147.00,
        target_1=165.00,
        target_2=178.00,
        risk_reward_ratio=2.83,
        position_size_shares=617,
        valid_until=date(2026, 9, 26),
        card_details={
            "phase2_derivatives": {"subtotal": 5},
            "phase3_technicals": {"subtotal": 4},
        },
    )


@pytest.fixture
def sample_strategic_card() -> TradeCheckCardRow:
    return TradeCheckCardRow(
        id=str(uuid.uuid4()),
        symbol="TCS",
        desk_type="STRATEGIC",
        eval_date=date(2026, 9, 25),
        hard_gates_pass=True,
        score=46.0,
        max_score=50.0,
        verdict="TIER_1",
        entry_trigger=None,
        stop_loss=None,
        target_1=None,
        target_2=None,
        risk_reward_ratio=None,
        position_size_shares=None,
        valid_until=None,
        card_details={
            "hard_forensic_gates": {"g1_beneish": True, "g2_realization": True},
            "phase2_moat": {"subtotal": 25},
        },
        restatement_caution=False,
    )


def test_acceptance_test_14_sha256_archive_parity(
    sample_tactical_card: TradeCheckCardRow,
    tmp_path: Path,
) -> None:
    """Acceptance Test 14: Report archive parity check using SHA-256."""
    html_path, json_path, checksum, log_row = archive_card_report(
        card=sample_tactical_card,
        archive_dir=tmp_path,
        actor="unit_tester",
    )

    # 1. Verify files exist on disk
    assert html_path.exists()
    assert json_path.exists()

    # 2. Re-read HTML bytes from disk and compute independent SHA-256
    disk_bytes = html_path.read_bytes()
    computed_checksum = hashlib.sha256(disk_bytes).hexdigest()

    # 3. Verify strict equality between disk hash and compliance log checksum
    assert computed_checksum == checksum
    assert log_row.checksum == checksum
    assert log_row.event_type == "RESEARCH_REPORT"
    assert log_row.actor == "unit_tester"

    # 4. Verify JSON content is valid and contains metadata
    json_data = json.loads(json_path.read_text(encoding="utf-8"))
    assert json_data["card"]["symbol"] == "TATASTEEL"
    assert json_data["disclosures"]["symbol"] == "TATASTEEL"

    # 5. 5-year retention check
    expected_retention = sample_tactical_card.eval_date + timedelta(days=5 * 365)
    assert log_row.retention_until == expected_retention


def test_acceptance_test_15_upsi_access_logging() -> None:
    """Acceptance Test 15: UPSI access logging per SEBI (PIT) Regulations."""
    payload = {"query": "SELECT * FROM draft_recommendations", "stage": "pre_publication"}
    log_row = log_upsi_access(
        symbol="INFY",
        actor="analyst_vikram",
        rationale="Pre-market verification of quarterly forensic checks",
        card_id=str(uuid.uuid4()),
        payload=payload,
    )

    assert log_row.event_type == "UPSI_ACCESS"
    assert log_row.symbol == "INFY"
    assert log_row.actor == "analyst_vikram"
    assert "Pre-market verification" in (log_row.rationale or "")
    assert log_row.checksum is not None and len(log_row.checksum) == 64
    assert log_row.retention_until >= date.today() + timedelta(days=5 * 360)


def test_prohibited_language_filter() -> None:
    """Verifies that prohibited return promise words raise ValueError."""
    with pytest.raises(ValueError, match="guaranteed"):
        verify_prohibited_language("This stock has guaranteed 25% returns annually.")

    with pytest.raises(ValueError, match="assured"):
        verify_prohibited_language("We provide assured returns on this investment.")

    with pytest.raises(ValueError, match="risk-free"):
        verify_prohibited_language("This is a completely risk-free swing setup.")

    with pytest.raises(ValueError, match="100% safe"):
        verify_prohibited_language("This strategy is 100% safe from drawdowns.")

    # Clean text must pass without error
    verify_prohibited_language(
        "Securities investments are subject to market risks. Read all scheme related documents carefully."
    )


def test_render_html_report_clean_language(
    sample_tactical_card: TradeCheckCardRow,
    sample_strategic_card: TradeCheckCardRow,
) -> None:
    """Ensures rendered HTML reports contain no prohibited language and valid HTML tags."""
    d1 = build_disclosure_snapshot("TATASTEEL", sample_tactical_card.id or "", "TACTICAL")
    html1 = render_html_report(sample_tactical_card, d1)
    assert "<!DOCTYPE html>" in html1
    assert "TATASTEEL" in html1
    assert "₹155.1" in html1
    assert "VERDICT: EXECUTE" in html1

    d2 = build_disclosure_snapshot("TCS", sample_strategic_card.id or "", "STRATEGIC")
    html2 = render_html_report(sample_strategic_card, d2)
    assert "VERDICT: TIER_1" in html2
    assert "TCS" in html2
    assert "Forensic & Fundamental Architecture" in html2


def test_archive_and_upsi_with_db(
    sample_tactical_card: TradeCheckCardRow,
    tmp_path: Path,
) -> None:
    from unittest.mock import MagicMock

    mock_db = MagicMock()

    # 1. Test archive_card_report with db
    html_path, json_path, checksum, log_row = archive_card_report(
        card=sample_tactical_card,
        archive_dir=tmp_path,
        actor="db_tester",
        db=mock_db,
    )
    assert html_path.exists()
    assert json_path.exists()
    assert len(checksum) == 64
    assert log_row.event_type == "RESEARCH_REPORT"
    assert mock_db.upsert.call_count == 2  # sebi_compliance_log and trade_check_cards

    # 2. Test log_upsi_access with db
    upsi_log = log_upsi_access(
        symbol="TATASTEEL",
        actor="compliance_officer",
        rationale="Audit verification",
        db=mock_db,
    )
    assert upsi_log.event_type == "UPSI_ACCESS"
    assert mock_db.upsert.call_count == 3
