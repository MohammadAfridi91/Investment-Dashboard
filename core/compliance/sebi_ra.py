"""SEBI Research Analyst (RA) Compliance Module.

Implements SEBI (Research Analysts) Regulations, 2014 compliance:
- Zero third-party PDF generators (HTML + JSON immutable archive only)
- Immutable archive at data/compliance/reports/{card_id}.html and .json
- SHA-256 checksum calculation & database recording
- 5-year statutory retention tracking (retention_until)
- Prohibited language filter (no 'guaranteed', 'assured', 'risk-free', '100% safe')
- Mandatory RA disclosures & conflict of interest disclosures
- UPSI (Unpublished Price Sensitive Information) access logging
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from core.database.client import DB
from core.models import SebiComplianceLogRow, TradeCheckCardRow

PROHIBITED_REGEX = re.compile(
    r"\b(guaranteed|assured|risk-free|100% safe|zero risk)\b",
    re.IGNORECASE,
)


def verify_prohibited_language(text: str) -> None:
    """Verifies that text does not contain prohibited return promises under SEBI regulations.

    Raises:
        ValueError: If prohibited promise language is found.
    """
    match = PROHIBITED_REGEX.search(text)
    if match:
        raise ValueError(
            f"SEBI Compliance Violation: Prohibited promise language detected: '{match.group(0)}'"
        )


def build_disclosure_snapshot(
    symbol: str,
    card_id: str,
    desk_type: str,
    analyst_name: str = "Dalal Street Automated Research Desk",
    reg_number: str = "INH000099999",
) -> dict[str, Any]:
    """Generates standard SEBI Research Analyst disclosure snapshot."""
    disclosures = {
        "analyst_name": analyst_name,
        "sebi_registration_number": reg_number,
        "symbol": symbol,
        "card_id": card_id,
        "desk_type": desk_type,
        "statutory_warning": (
            "Securities investments are subject to market risks. "
            "Read all related documents carefully before investing."
        ),
        "analyst_ownership": (
            "The Research Analyst and associates do not have financial interest "
            "exceeding 1% in the subject company as of the date of this report."
        ),
        "conflict_of_interest": (
            "No material conflict of interest exists with the subject company. "
            "No compensation has been received from the subject company in the preceding 12 months."
        ),
        "risk_affirmation": (
            "Equity investments are subject to market volatility and potential capital loss. "
            "Past performance does not indicate future results."
        ),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    # Verify no prohibited language in generated disclosures
    for val in disclosures.values():
        if isinstance(val, str):
            verify_prohibited_language(val)
    return disclosures


def render_html_report(
    card: TradeCheckCardRow,
    disclosures: dict[str, Any],
    additional_context: dict[str, Any] | None = None,
) -> str:
    """Renders a self-contained HTML research report matching SEBI RA standards."""
    eval_date_str = card.eval_date.isoformat()
    verdict_class = (
        "verdict-execute" if card.verdict in ("EXECUTE", "TIER_1", "TIER_2") else "verdict-abort"
    )

    tactical_section = ""
    strategic_section = ""

    if card.desk_type == "TACTICAL":
        tactical_section = f"""
        <div class="card-section">
            <h3>Tactical Trade Architecture</h3>
            <table class="data-table">
                <tr><th>Parameter</th><th>Value</th></tr>
                <tr><td>Entry Trigger</td><td>{"₹" + str(card.entry_trigger) if card.entry_trigger else "N/A"}</td></tr>
                <tr><td>Stop Loss</td><td>{"₹" + str(card.stop_loss) if card.stop_loss else "N/A"}</td></tr>
                <tr><td>Target 1 (HVN Confluence)</td><td>{"₹" + str(card.target_1) if card.target_1 else "N/A"}</td></tr>
                <tr><td>Target 2 (Resistance)</td><td>{"₹" + str(card.target_2) if card.target_2 else "N/A"}</td></tr>
                <tr><td>Risk:Reward Ratio</td><td>{str(card.risk_reward_ratio) + ":1" if card.risk_reward_ratio else "N/A"}</td></tr>
                <tr><td>Position Size (Shares)</td><td>{str(card.position_size_shares) if card.position_size_shares else "0"}</td></tr>
                <tr><td>Order Validity</td><td>{card.valid_until.isoformat() if card.valid_until else "EOD (T+1)"}</td></tr>
            </table>
        </div>
        """
    else:
        gates = card.card_details.get("hard_forensic_gates", {})
        gates_rows = "".join(
            f"<tr><td>{html.escape(k)}</td><td>{'PASS' if v else 'FAIL'}</td></tr>"
            for k, v in gates.items()
        )
        strategic_section = f"""
        <div class="card-section">
            <h3>Forensic & Fundamental Architecture</h3>
            <table class="data-table">
                <tr><th>Forensic Gate</th><th>Status</th></tr>
                {gates_rows}
            </table>
            <p><strong>Restatement Caution:</strong> {"CAUTION: Financial restatement detected" if card.restatement_caution else "None"}</p>
        </div>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SEBI RA Research Report - {html.escape(card.symbol)} ({html.escape(card.desk_type)})</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #1e293b;
            background-color: #f8fafc;
            margin: 0;
            padding: 24px;
        }}
        .report-container {{
            max-width: 860px;
            margin: 0 auto;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 32px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}
        .header {{
            border-bottom: 2px solid #0f172a;
            padding-bottom: 16px;
            margin-bottom: 24px;
        }}
        .header h1 {{
            margin: 0 0 8px 0;
            color: #0f172a;
            font-size: 24px;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 12px;
            font-weight: 600;
            border-radius: 4px;
            font-size: 14px;
            margin-right: 8px;
        }}
        .badge-tactical {{ background-color: #e0e7ff; color: #3730a3; }}
        .badge-strategic {{ background-color: #fef3c7; color: #92400e; }}
        .verdict-execute {{ background-color: #dcfce7; color: #166534; }}
        .verdict-abort {{ background-color: #fee2e2; color: #991b1b; }}
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 16px 0;
        }}
        .data-table th, .data-table td {{
            border: 1px solid #e2e8f0;
            padding: 8px 12px;
            text-align: left;
        }}
        .data-table th {{
            background-color: #f1f5f9;
            font-weight: 600;
        }}
        .disclaimer-box {{
            background-color: #f8fafc;
            border-left: 4px solid #64748b;
            padding: 16px;
            margin-top: 32px;
            font-size: 12px;
            color: #475569;
        }}
        .meta-info {{
            font-size: 13px;
            color: #64748b;
            margin-top: 8px;
        }}
    </style>
</head>
<body>
    <div class="report-container">
        <div class="header">
            <h1>Automated Research Report: {html.escape(card.symbol)}</h1>
            <div>
                <span class="badge {"badge-tactical" if card.desk_type == "TACTICAL" else "badge-strategic"}">{html.escape(card.desk_type)} DESK</span>
                <span class="badge {verdict_class}">VERDICT: {html.escape(card.verdict)}</span>
                <span class="badge">SCORE: {card.score:.1f} / {card.max_score:.1f}</span>
            </div>
            <div class="meta-info">
                Evaluation Date: {eval_date_str} | Card ID: {html.escape(card.id or "N/A")}
            </div>
        </div>

        {tactical_section}
        {strategic_section}

        <div class="disclaimer-box">
            <h4>Statutory Disclosures under SEBI (Research Analysts) Regulations, 2014</h4>
            <p><strong>Analyst:</strong> {html.escape(disclosures.get("analyst_name", ""))}</p>
            <p><strong>SEBI Registration:</strong> {html.escape(disclosures.get("sebi_registration_number", ""))}</p>
            <p><strong>Statutory Warning:</strong> {html.escape(disclosures.get("statutory_warning", ""))}</p>
            <p><strong>Ownership & Conflict:</strong> {html.escape(disclosures.get("analyst_ownership", ""))} {html.escape(disclosures.get("conflict_of_interest", ""))}</p>
            <p><strong>Risk Warning:</strong> {html.escape(disclosures.get("risk_affirmation", ""))}</p>
        </div>
    </div>
</body>
</html>
"""
    verify_prohibited_language(html_content)
    return html_content


def archive_card_report(
    card: TradeCheckCardRow,
    disclosures: dict[str, Any] | None = None,
    archive_dir: str | Path = "data/compliance/reports",
    actor: str = "dalal_street_engine",
    db: DB | None = None,
) -> tuple[Path, Path, str, SebiComplianceLogRow]:
    """Archives trade check card as immutable HTML and JSON documents, logging SEBI compliance.

    Args:
        card: Evaluated TradeCheckCardRow.
        disclosures: SEBI disclosures dictionary (built if None).
        archive_dir: Directory where reports are saved.
        actor: System component or user executing archiving.
        db: Optional DB client to persist log row.

    Returns:
        Tuple of (html_path, json_path, sha256_checksum, SebiComplianceLogRow).
    """
    card_id = card.id or str(uuid.uuid4())
    card.id = card_id

    if disclosures is None:
        disclosures = build_disclosure_snapshot(
            symbol=card.symbol,
            card_id=card_id,
            desk_type=card.desk_type,
        )

    # 1. Render HTML report & verify prohibited language
    html_content = render_html_report(card, disclosures)

    # 2. Prepare JSON payload
    card_data = card.model_dump(mode="json")
    json_payload: dict[str, Any] = {
        "card": card_data,
        "disclosures": disclosures,
        "archived_at": datetime.now(UTC).isoformat(),
        "actor": actor,
    }
    json_content = json.dumps(json_payload, indent=2, sort_keys=True)

    # 3. Create target directory
    out_dir = Path(archive_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    html_path = out_dir / f"{card_id}.html"
    json_path = out_dir / f"{card_id}.json"

    # 4. Write files
    html_bytes = html_content.encode("utf-8")
    html_path.write_bytes(html_bytes)
    json_path.write_bytes(json_content.encode("utf-8"))

    # 5. Compute SHA-256 of HTML report for regulatory integrity
    checksum = hashlib.sha256(html_bytes).hexdigest()

    # 6. Retention date (5 years from evaluation date)
    retention_until = card.eval_date + timedelta(days=5 * 365)

    # 7. Construct SEBI Compliance Log Row
    log_row = SebiComplianceLogRow(
        id=str(uuid.uuid4()),
        event_type="RESEARCH_REPORT",
        event_ts=datetime.now(UTC),
        symbol=card.symbol,
        card_id=card_id,
        actor=actor,
        payload={
            "html_file": f"{card_id}.html",
            "json_file": f"{card_id}.json",
            "desk_type": card.desk_type,
            "verdict": card.verdict,
            "score": card.score,
        },
        rationale=f"Automated {card.desk_type} Trade Check Card evaluation for {card.symbol} with verdict {card.verdict}",
        disclosure_text=disclosures.get("statutory_warning"),
        retention_until=retention_until,
        checksum=checksum,
    )

    # 8. Persist to DB if provided
    if db is not None:
        db.upsert(
            "sebi_compliance_log",
            [log_row.model_dump(mode="json")],
            on_conflict="id",
        )
        card_dump = card.model_dump(mode="json")
        card_dump["sebi_disclosure_snapshot"] = disclosures
        db.upsert(
            "trade_check_cards",
            [card_dump],
            on_conflict="id",
        )

    return html_path, json_path, checksum, log_row


def log_upsi_access(
    symbol: str,
    actor: str,
    rationale: str,
    card_id: str | None = None,
    payload: dict[str, Any] | None = None,
    db: DB | None = None,
) -> SebiComplianceLogRow:
    """Logs access to Unpublished Price Sensitive Information (UPSI) or pre-publication reports."""
    payload_data = payload or {}
    payload_bytes = json.dumps(payload_data, sort_keys=True).encode("utf-8")
    checksum = hashlib.sha256(payload_bytes).hexdigest()
    today = date.today()
    retention_until = today + timedelta(days=5 * 365)

    log_row = SebiComplianceLogRow(
        id=str(uuid.uuid4()),
        event_type="UPSI_ACCESS",
        event_ts=datetime.now(UTC),
        symbol=symbol,
        card_id=card_id,
        actor=actor,
        payload=payload_data,
        rationale=rationale,
        disclosure_text="Internal UPSI access log per SEBI (PIT) Regulations, 2015",
        retention_until=retention_until,
        checksum=checksum,
    )

    if db is not None:
        db.upsert(
            "sebi_compliance_log",
            [log_row.model_dump(mode="json")],
            on_conflict="id",
        )

    return log_row
