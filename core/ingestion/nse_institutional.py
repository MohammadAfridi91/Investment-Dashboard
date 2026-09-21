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
from core.utils.normalization import normalize_client_name, strip_column_names

log = get_logger("ingest.institutional")

BULK_DEALS_URL = "https://archives.nseindia.com/content/equities/bulk.csv"
BLOCK_DEALS_URL = "https://archives.nseindia.com/content/equities/block.csv"


def _parse_deal_date(val: Any) -> date | None:
    if val is None:
        return None
    s = str(val).strip()
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


class NSEInstitutionalIngestor(Ingestor):
    SOURCE = "nse_institutional"
    SCHEDULE = "EOD"

    def __init__(self, http: Any, db: DB, config: Config) -> None:
        self.http = http
        self.db = db
        self.config = config

    def _compile_institutional_regexes(self) -> list[re.Pattern[str]]:
        patterns: list[re.Pattern[str]] = []
        for pat_str in (
            self.config.institutional_regex.amc,
            self.config.institutional_regex.insurance,
            self.config.institutional_regex.fii,
        ):
            if pat_str:
                sub_pats = [p.strip() for p in pat_str.split("|") if p.strip()]
                bounded_pat = r"\b(?:" + "|".join(sub_pats) + r")\b"
                patterns.append(re.compile(bounded_pat, re.IGNORECASE))
        return patterns


    def parse_deals_csv(
        self,
        raw: bytes | None,
        deal_type: str,
        target_date: date,
        regexes: list[re.Pattern[str]],
    ) -> list[dict[str, Any]]:
        if not raw:
            return []
        try:
            df = pd.read_csv(io.BytesIO(raw), dtype=str, skipinitialspace=True)
            df.columns = strip_column_names(list(df.columns))

            # Column detection
            sym_col = next((c for c in df.columns if "SYMBOL" in c.upper()), None)
            date_col = next((c for c in df.columns if "DATE" in c.upper()), None)
            client_col = next((c for c in df.columns if "CLIENT" in c.upper()), None)
            dir_col = next((c for c in df.columns if any(k in c.upper() for k in ("BUY/SELL", "DEAL TYPE", "BUY", "SELL"))), None)
            qty_col = next((c for c in df.columns if "QUANTITY" in c.upper() or "QTY" in c.upper()), None)
            price_col = next((c for c in df.columns if "PRICE" in c.upper()), None)

            if not all([sym_col, client_col, qty_col, price_col]):
                log.warning("institutional_missing_columns", cols=list(df.columns))
                return []

            rows: list[dict[str, Any]] = []
            for _, r in df.iterrows():
                sym = str(r[sym_col]).strip()
                if not sym:
                    continue

                if date_col:
                    d = _parse_deal_date(r[date_col])
                    if d and d != target_date:
                        continue
                deal_dt = target_date

                raw_client = str(r[client_col]).strip()
                norm_client = normalize_client_name(raw_client)

                direction = "BUY"
                if dir_col and r[dir_col]:
                    raw_dir = str(r[dir_col]).strip().upper()
                    if raw_dir.startswith("S"):
                        direction = "SELL"

                try:
                    qty = int(float(str(r[qty_col]).replace(",", "")))
                    price = float(str(r[price_col]).replace(",", ""))
                except (ValueError, TypeError):
                    continue

                if qty <= 0 or price <= 0:
                    continue

                is_inst = any(p.search(norm_client) for p in regexes)

                rows.append(
                    {
                        "symbol": sym,
                        "deal_date": deal_dt.isoformat(),
                        "deal_type": deal_type,
                        "client_name": raw_client,
                        "normalized_client_name": norm_client,
                        "pan": None,
                        "trade_direction": direction,
                        "quantity": qty,
                        "price": price,
                        "is_institutional": is_inst,
                        "is_wash_trade": False,
                    }
                )
            return rows
        except Exception as e:
            log.warning("institutional_csv_parse_error", error=str(e))
            return []

    def _flag_wash_trades(self, rows: list[dict[str, Any]]) -> None:
        """Detect matched buy/sell trades by same client within ±10% qty and >= 1 Cr value."""
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for r in rows:
            key = (r["symbol"], str(r["deal_date"]), r["normalized_client_name"])
            grouped.setdefault(key, []).append(r)

        qty_tol = self.config.wash_trade.qty_match_pct
        min_val = self.config.wash_trade.min_value_inr

        for _, group in grouped.items():
            buys = [g for g in group if g["trade_direction"] == "BUY"]
            sells = [g for g in group if g["trade_direction"] == "SELL"]

            for b in buys:
                for s in sells:
                    max_q = max(b["quantity"], s["quantity"])
                    if max_q == 0:
                        continue
                    diff_pct = abs(b["quantity"] - s["quantity"]) / max_q
                    val_b = b["quantity"] * b["price"]
                    val_s = s["quantity"] * s["price"]

                    if diff_pct <= qty_tol and min(val_b, val_s) >= min_val:
                        b["is_wash_trade"] = True
                        s["is_wash_trade"] = True

    def _sync_derivative_institutional_buy(self, rows: list[dict[str, Any]], target_date: date) -> None:
        """Update has_institutional_net_buy on derivative_metrics if net institutional buy >= 5 Cr."""
        min_net_buy_inr = 50_000_000.0  # 5 Cr per Master Plan §12.2
        net_by_sym: dict[str, float] = {}
        for r in rows:
            if not r["is_institutional"]:
                continue
            s = r["symbol"]
            val = float(r["quantity"]) * float(r["price"])
            if r["trade_direction"] == "BUY":
                net_by_sym[s] = net_by_sym.get(s, 0.0) + val
            else:
                net_by_sym[s] = net_by_sym.get(s, 0.0) - val

        qualifying = [sym for sym, net_val in net_by_sym.items() if net_val >= min_net_buy_inr]

        if not qualifying:
            return

        try:
            deriv_rows = self.db.select_in(
                "derivative_metrics",
                "symbol",
                qualifying,
                columns="symbol,trade_date,has_institutional_net_buy",
            )
            to_update = [
                d for d in deriv_rows
                if str(d.get("trade_date")) == str(target_date) and not d.get("has_institutional_net_buy")
            ]
            for d in to_update:
                d["has_institutional_net_buy"] = True
            if to_update:
                self.db.upsert("derivative_metrics", to_update, on_conflict="symbol,trade_date")
                log.info("institutional_synced_to_derivatives", count=len(to_update))
        except Exception as e:
            log.warning("institutional_derivative_sync_failed", error=str(e))

    def run(self, target_date: date) -> IngestResult:
        t0 = self._timer()
        raw_bulk: bytes | None = None
        raw_block: bytes | None = None
        try:
            raw_bulk = cast(bytes, self.http.get(BULK_DEALS_URL))
        except Exception as e:
            log.warning("institutional_bulk_fetch_failed", error=str(e))

        try:
            raw_block = cast(bytes, self.http.get(BLOCK_DEALS_URL))
        except Exception as e:
            log.warning("institutional_block_fetch_failed", error=str(e))

        regexes = self._compile_institutional_regexes()
        bulk_rows = self.parse_deals_csv(raw_bulk, "BULK", target_date, regexes)
        block_rows = self.parse_deals_csv(raw_block, "BLOCK", target_date, regexes)
        all_rows = bulk_rows + block_rows

        self._flag_wash_trades(all_rows)
        self._sync_derivative_institutional_buy(all_rows, target_date)

        known = {u["symbol"] for u in self.db.select("universe", columns="symbol")}
        valid_rows = [r for r in all_rows if r["symbol"] in known] if known else all_rows

        written = 0
        if valid_rows:
            try:
                written = self.db.upsert(
                    "institutional_deals",
                    valid_rows,
                    on_conflict="symbol,deal_date,client_name,trade_direction,deal_type",
                )
            except Exception as e:
                log.error("institutional_upsert_failed", error=str(e))
                return IngestResult(self.SOURCE, status="FAILED", error=str(e))

        dur_ms = int((self._timer() - t0) * 1000)
        checksum = sha256_bytes((raw_bulk or b"") + (raw_block or b""))
        log.info("institutional_done", total=len(all_rows), written=written, duration_ms=dur_ms)
        return IngestResult(
            self.SOURCE,
            status="SUCCESS",
            target_date=target_date,
            rows_fetched=len(all_rows),
            rows_valid=len(valid_rows),
            rows_rejected=len(all_rows) - len(valid_rows),
            rows_upserted=written,
            rows_written=written,
            duration_ms=dur_ms,
            checksum=checksum,
        )
