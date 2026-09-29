"""SEBI Research Analyst (RA) Compliance Module.

Implements SEBI (Research Analysts) Regulations, 2014 compliance:
- Zero third-party PDF generators (HTML + JSON immutable archive only)
- Immutable archive: exclusive-create files at data/compliance/reports/{card_id}.html/.json
  PLUS a durable, append-only, byte-exact copy in the compliance_report_archive table
  (runner disks are ephemeral, so the DB copy is the system of record)
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
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from dateutil.relativedelta import relativedelta

from core.database.client import DB
from core.models import SebiComplianceLogRow, TradeCheckCardRow

RETENTION_YEARS = 5
# Safety margin so retention is never *shorter* than the statutory period (leap years, TZ skew).
RETENTION_MARGIN_DAYS = 30

REG_NUMBER_ENV = "SEBI_RA_REGISTRATION_NUMBER"
_REG_NUMBER_RE = re.compile(r"^INH\d{9}$")
_KNOWN_PLACEHOLDER_REG_NUMBERS = {"INH000099999", "INH000000000"}

DEFAULT_OWNERSHIP_DISCLOSURE = (
    "The Research Analyst and associates do not have financial interest "
    "exceeding 1% in the subject company as of the date of this report."
)
DEFAULT_CONFLICT_DISCLOSURE = (
    "No material conflict of interest exists with the subject company. "
    "No compensation has been received from the subject company in the preceding 12 months."
)


class ComplianceConfigError(RuntimeError):
    """Required compliance configuration is missing or invalid."""


class ArchiveError(RuntimeError):
    """An archived report already exists or could not be written."""


def retention_until(start: date, years: int = RETENTION_YEARS) -> date:
    """Calendar-aware retention end date (`years` years plus a safety margin)."""
    return start + relativedelta(years=years) + timedelta(days=RETENTION_MARGIN_DAYS)


def resolve_registration_number(explicit: str | None = None) -> str:
    """Return the SEBI RA registration number or fail loudly.

    Never fabricates a number: an invented registration number in an archived regulatory
    document is worse than no report.
    """
    reg = (explicit or os.environ.get(REG_NUMBER_ENV, "")).strip().upper()
    if not reg:
        raise ComplianceConfigError(
            f"{REG_NUMBER_ENV} is not set; refusing to generate SEBI RA reports without it"
        )
    if not _REG_NUMBER_RE.match(reg) or reg in _KNOWN_PLACEHOLDER_REG_NUMBERS:
        raise ComplianceConfigError(
            f"{REG_NUMBER_ENV} must be a real SEBI RA number of the form INH#########"
        )
    return reg


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
    reg_number: str | None = None,
) -> dict[str, Any]:
    """Generates standard SEBI Research Analyst disclosure snapshot.

    The registration number comes from `reg_number` or the SEBI_RA_REGISTRATION_NUMBER
    environment variable. Ownership / conflict statements default to the standard wording and
    can be overridden via SEBI_RA_OWNERSHIP_DISCLOSURE / SEBI_RA_CONFLICT_DISCLOSURE; they are
    attestations the registrant must be able to stand behind.
    """
    reg_number = resolve_registration_number(reg_number)
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
        "analyst_ownership": os.environ.get(
            "SEBI_RA_OWNERSHIP_DISCLOSURE", DEFAULT_OWNERSHIP_DISCLOSURE
        ),
        "conflict_of_interest": os.environ.get(
            "SEBI_RA_CONFLICT_DISCLOSURE", DEFAULT_CONFLICT_DISCLOSURE
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


@dataclass
class ArchiveBundle:
    """Everything produced by archiving one card, ready for (batched) persistence."""

    card_id: str
    html_path: Path
    json_path: Path
    checksum: str
    log_row: SebiComplianceLogRow
    archive_row: dict[str, Any]
    card_row: dict[str, Any]


def _write_exclusive(path: Path, data: bytes) -> None:
    try:
        with open(path, "xb") as fh:  # exclusive create: never overwrite an archived report
            fh.write(data)
    except FileExistsError as exc:
        raise ArchiveError(f"Archived report already exists and is immutable: {path}") from exc


def write_card_archive(
    card: TradeCheckCardRow,
    disclosures: dict[str, Any] | None = None,
    archive_dir: str | Path = "data/compliance/reports",
    actor: str = "dalal_street_engine",
) -> ArchiveBundle:
    """Render + write the immutable HTML/JSON archive files. Does not touch the database."""
    card_id = card.id or str(uuid.uuid4())
    card.id = card_id

    if disclosures is None:
        disclosures = build_disclosure_snapshot(
            symbol=card.symbol,
            card_id=card_id,
            desk_type=card.desk_type,
        )

    html_content = render_html_report(card, disclosures)  # also verifies prohibited language

    archived_at = datetime.now(UTC)
    card_data = card.model_dump(mode="json")
    json_payload: dict[str, Any] = {
        "card": card_data,
        "disclosures": disclosures,
        "archived_at": archived_at.isoformat(),
        "actor": actor,
    }
    json_bytes = json.dumps(json_payload, indent=2, sort_keys=True).encode("utf-8")
    html_bytes = html_content.encode("utf-8")

    out_dir = Path(archive_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{card_id}.html"
    json_path = out_dir / f"{card_id}.json"

    _write_exclusive(html_path, html_bytes)
    try:
        _write_exclusive(json_path, json_bytes)
    except ArchiveError:
        html_path.unlink(missing_ok=True)  # do not leave a half-written archive behind
        raise

    checksum = hashlib.sha256(html_bytes).hexdigest()
    json_checksum = hashlib.sha256(json_bytes).hexdigest()
    retain_until = retention_until(card.eval_date)

    log_row = SebiComplianceLogRow(
        id=str(uuid.uuid4()),
        event_type="RESEARCH_REPORT",
        event_ts=archived_at,
        symbol=card.symbol,
        card_id=card_id,
        actor=actor,
        payload={
            "html_file": f"{card_id}.html",
            "json_file": f"{card_id}.json",
            "desk_type": card.desk_type,
            "verdict": card.verdict,
            "score": card.score,
            "json_checksum": json_checksum,
        },
        rationale=f"Automated {card.desk_type} Trade Check Card evaluation for {card.symbol} with verdict {card.verdict}",
        disclosure_text=disclosures.get("statutory_warning"),
        retention_until=retain_until,
        checksum=checksum,
    )

    card_row = card.model_dump(mode="json")
    card_row["sebi_disclosure_snapshot"] = disclosures

    return ArchiveBundle(
        card_id=card_id,
        html_path=html_path,
        json_path=json_path,
        checksum=checksum,
        log_row=log_row,
        archive_row={
            "card_id": card_id,
            "symbol": card.symbol,
            "desk_type": card.desk_type,
            "eval_date": card.eval_date.isoformat(),
            "checksum_sha256": checksum,
            "json_checksum_sha256": json_checksum,
            "report_html": html_content,
            "report_json": json_bytes.decode("utf-8"),
            "archived_at": archived_at.isoformat(),
            "retention_until": retain_until.isoformat(),
        },
        card_row=card_row,
    )


def persist_archives(db: DB, bundles: list[ArchiveBundle], chunk_size: int = 50) -> None:
    """Persist archived reports durably and append-only.

    Order matters: the byte-exact archive copy is written first, then the compliance log, then
    the (mutable) card row. Any failure raises so the caller can mark the run failed.
    """
    if not bundles:
        return
    db.insert("compliance_report_archive", [b.archive_row for b in bundles], chunk_size=chunk_size)
    db.insert("sebi_compliance_log", [b.log_row.model_dump(mode="json") for b in bundles])
    db.upsert("trade_check_cards", [b.card_row for b in bundles], on_conflict="id")


def archive_card_report(
    card: TradeCheckCardRow,
    disclosures: dict[str, Any] | None = None,
    archive_dir: str | Path = "data/compliance/reports",
    actor: str = "dalal_street_engine",
    db: DB | None = None,
) -> tuple[Path, Path, str, SebiComplianceLogRow]:
    """Archives a trade check card as immutable HTML/JSON files and logs SEBI compliance.

    Returns:
        Tuple of (html_path, json_path, sha256_checksum, SebiComplianceLogRow).

    Raises:
        ArchiveError: if an archive for this card already exists (archives are write-once).
        ComplianceConfigError: if the SEBI RA registration number is not configured.
    """
    bundle = write_card_archive(card, disclosures, archive_dir, actor)
    if db is not None:
        persist_archives(db, [bundle])
    return bundle.html_path, bundle.json_path, bundle.checksum, bundle.log_row


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
    today = datetime.now(UTC).date()

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
        retention_until=retention_until(today),
        checksum=checksum,
    )

    if db is not None:
        db.insert("sebi_compliance_log", [log_row.model_dump(mode="json")])

    return log_row
