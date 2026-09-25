from __future__ import annotations

import io
import re
from datetime import date, datetime
from typing import Any, cast

import pandas as pd

from core.config import Config
from core.database.client import DB
from core.ingestion.base import Ingestor, IngestResult
from core.utils.checksums import sha256_bytes
from core.utils.logging import get_logger
from core.utils.normalization import strip_column_names

log = get_logger("ingest.corporate_actions")

ACTIONS_URL = "https://archives.nseindia.com/content/equities/Actions.csv"
ACTIONS_API_URL = "https://www.nseindia.com/api/corporates-corporateActions?index=equities"

SPLIT_RE = re.compile(
    r"(?:Split|Sub-Division|Face Value).*?(\d+(?:\.\d+)?).*?(?:to|To|TO)\s*(?:Rs\.?)?\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
BONUS_RE = re.compile(r"Bonus.*?(\d+)\s*:\s*(\d+)", re.IGNORECASE)
DIVIDEND_RE = re.compile(r"Dividend.*?(?:Rs\.?)?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


def _parse_action_date(val: Any) -> date | None:
    if val is None:
        return None
    s = str(val).strip()
    if s in ("-", "", "NA"):
        return None
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_action_purpose(
    purpose: str,
) -> tuple[str, float, float | None, float | None, float | None]:
    """Parse corporate action purpose string.

    Returns: (action_type, adjustment_factor, ratio, face_value_change, dividend_amount)
    """
    p = purpose.strip()

    # Split check
    m_split = SPLIT_RE.search(p)
    if m_split:
        try:
            old_fv = float(m_split.group(1))
            new_fv = float(m_split.group(2))
            if new_fv > 0:
                factor = old_fv / new_fv
                return "SPLIT", factor, factor, new_fv, None
        except (ValueError, ZeroDivisionError):
            pass

    # Bonus check
    m_bonus = BONUS_RE.search(p)
    if m_bonus:
        try:
            x = float(m_bonus.group(1))
            y = float(m_bonus.group(2))
            if y > 0:
                factor = (x + y) / y
                return "BONUS", factor, factor, None, None
        except (ValueError, ZeroDivisionError):
            pass

    # Dividend check
    m_div = DIVIDEND_RE.search(p)
    if m_div:
        try:
            amt = float(m_div.group(1))
            return "DIVIDEND", 1.0, None, None, amt
        except ValueError:
            return "DIVIDEND", 1.0, None, None, None

    if "RIGHT" in p.upper():
        return "RIGHTS", 1.0, None, None, None

    return "OTHER", 1.0, None, None, None


def apply_adjustments(db: DB, target_date: date) -> int:
    """Apply corporate action adjustments to historical daily_prices.adjusted_close.

    For each action on or effective target_date with factor != 1.0:
    All historical daily_prices rows with trade_date < ex_date get:
        adjusted_close = close_price / adjustment_factor
    """
    actions = db.select(
        "corporate_actions",
        filters={"ex_date": target_date.isoformat()},
    )
    splitting_actions = [a for a in actions if float(a.get("adjustment_factor", 1.0)) != 1.0]
    if not splitting_actions:
        return 0

    total_adjusted = 0
    for act in splitting_actions:
        sym = act["symbol"]
        factor = float(act["adjustment_factor"])
        ex_dt = act["ex_date"]

        # Fetch historical prices for this symbol before ex_date
        hist_rows = db.select(
            "daily_prices",
            columns="symbol,trade_date,close_price,open_price,high_price,low_price,prev_close,adjusted_close,bhavcopy_avg_price,session_avg_price,volume,delivery_qty,delivery_pct,traded_value,circuit_band,high_52w,low_52w,data_source",
            filters={"symbol": sym},
        )
        pre_ex_rows = [r for r in hist_rows if str(r.get("trade_date")) < str(ex_dt)]
        if not pre_ex_rows:
            continue

        for r in pre_ex_rows:
            r["adjusted_close"] = round(float(r["close_price"]) / factor, 4)

        try:
            db.upsert("daily_prices", pre_ex_rows, on_conflict="symbol,trade_date")
            total_adjusted += len(pre_ex_rows)
            log.info(
                "applied_corporate_action_adjustment",
                symbol=sym,
                factor=factor,
                rows=len(pre_ex_rows),
            )
        except Exception as e:
            log.error("corporate_action_adjustment_failed", symbol=sym, error=str(e))

    return total_adjusted


class CorporateActionsIngestor(Ingestor):
    SOURCE = "corporate_actions"
    SCHEDULE = "EOD"

    def __init__(self, http: Any, db: DB, config: Config) -> None:
        self.http = http
        self.db = db
        self.config = config

    def parse(self, raw: bytes, target_date: date) -> list[dict[str, Any]]:
        # Check if response is JSON from live NSE API
        if raw.strip().startswith((b"[", b"{")):
            import json

            data = json.loads(raw.decode("utf-8-sig", errors="ignore"))
            rows: list[dict[str, Any]] = []
            if isinstance(data, list):
                for it in data:
                    series = str(it.get("series", "")).strip().upper()
                    if series and series not in ("EQ", "BE", ""):
                        continue
                    ex_dt = _parse_action_date(it.get("exDate"))
                    if not ex_dt or ex_dt != target_date:
                        continue
                    sym = str(it.get("symbol", "")).strip().upper()
                    if not sym:
                        continue
                    purpose = str(it.get("subject", "")).strip()
                    rec_dt = _parse_action_date(it.get("recDate"))
                    action_typ, factor, ratio, fv_chg, div_amt = parse_action_purpose(purpose)
                    rows.append(
                        {
                            "symbol": sym,
                            "ex_date": ex_dt.isoformat(),
                            "record_date": rec_dt.isoformat() if rec_dt else None,
                            "action_type": action_typ,
                            "ratio": ratio,
                            "face_value_change": fv_chg,
                            "dividend_amount": div_amt,
                            "adjustment_factor": factor,
                            "source": "nse_actions_api",
                        }
                    )
            return rows

        df = pd.read_csv(io.BytesIO(raw), dtype=str, skipinitialspace=True)
        df.columns = strip_column_names(list(df.columns))

        sym_col = next((c for c in df.columns if "SYMBOL" in c.upper()), None)
        ex_col = next((c for c in df.columns if "EX" in c.upper() and "DATE" in c.upper()), None)
        purpose_col = next((c for c in df.columns if "PURPOSE" in c.upper()), None)
        series_col = next((c for c in df.columns if "SERIES" in c.upper()), None)
        rec_col = next(
            (c for c in df.columns if "RECORD" in c.upper() and "DATE" in c.upper()), None
        )

        if not all([sym_col, ex_col, purpose_col]):
            raise ValueError(f"Actions CSV missing required columns: {list(df.columns)}")

        rows = []
        for _, r in df.iterrows():
            if series_col:
                series = str(r[series_col]).strip().upper()
                if series not in ("EQ", "BE", ""):
                    continue

            ex_dt = _parse_action_date(r[ex_col])
            if not ex_dt or ex_dt != target_date:
                continue

            sym = str(r[sym_col]).strip()
            if not sym:
                continue

            purpose = str(r[purpose_col]).strip()
            rec_dt = _parse_action_date(r[rec_col]) if rec_col else None

            action_typ, factor, ratio, fv_chg, div_amt = parse_action_purpose(purpose)

            rows.append(
                {
                    "symbol": sym,
                    "ex_date": ex_dt.isoformat(),
                    "record_date": rec_dt.isoformat() if rec_dt else None,
                    "action_type": action_typ,
                    "ratio": ratio,
                    "face_value_change": fv_chg,
                    "dividend_amount": div_amt,
                    "adjustment_factor": factor,
                    "source": "nse_actions_csv",
                }
            )

        return rows

    def run(self, target_date: date) -> IngestResult:
        t0 = self._timer()
        raw: bytes | None = None
        for url in (ACTIONS_URL, ACTIONS_API_URL):
            try:
                raw = cast(bytes, self.http.get(url))
                if raw and len(raw) > 20:
                    break
            except Exception as e:
                log.warning("corporate_actions_fetch_try_failed", url=url, error=str(e))
                continue

        if not raw:
            log.error(
                "corporate_actions_fetch_failed", error="All corporate actions endpoints failed"
            )
            return IngestResult(
                self.SOURCE, status="FAILED", error="All corporate actions endpoints failed"
            )

        checksum = sha256_bytes(raw)
        try:
            rows = self.parse(raw, target_date)
        except Exception as e:
            log.error("corporate_actions_parse_failed", error=str(e))
            return IngestResult(self.SOURCE, status="FAILED", checksum=checksum, error=str(e))

        known = {u["symbol"] for u in self.db.select("universe", columns="symbol")}
        valid_rows = [r for r in rows if r["symbol"] in known] if known else rows

        written = 0
        if valid_rows:
            try:
                written = self.db.upsert(
                    "corporate_actions",
                    valid_rows,
                    on_conflict="symbol,ex_date,action_type",
                )
            except Exception as e:
                log.error("corporate_actions_upsert_failed", error=str(e))
                return IngestResult(self.SOURCE, status="FAILED", checksum=checksum, error=str(e))

        # Apply adjustments to daily_prices
        adj_count = apply_adjustments(self.db, target_date)

        dur_ms = int((self._timer() - t0) * 1000)
        log.info(
            "corporate_actions_done",
            rows=len(rows),
            written=written,
            adjusted=adj_count,
            duration_ms=dur_ms,
        )
        return IngestResult(
            self.SOURCE,
            status="SUCCESS",
            target_date=target_date,
            rows_fetched=len(rows),
            rows_valid=len(valid_rows),
            rows_rejected=len(rows) - len(valid_rows),
            rows_upserted=written,
            rows_written=written,
            duration_ms=dur_ms,
            checksum=checksum,
            extras={"prices_adjusted": adj_count},
        )
