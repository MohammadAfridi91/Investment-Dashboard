from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from core.database.client import DB
from core.ingestion.base import Ingestor, IngestResult
from core.utils.checksums import sha256_bytes
from core.utils.logging import get_logger
from core.utils.normalization import strip_column_names
from core.utils.validation import ValidationError, require_ohlc_consistency, validate_ohlc

log = get_logger("ingest.bhavcopy")

BASE_URL = "https://archives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
SERIES_KEEP = {"EQ", "BE"}


class NSEBhavcopyIngestor(Ingestor):
    SOURCE = "nse_bhavcopy"
    SCHEDULE = "EOD"

    def __init__(self, http: Any, db: DB, config: Any) -> None:
        self.http = http
        self.db = db
        self.config = config

    def fetch(self, target_date: date) -> bytes:
        url = BASE_URL.format(ddmmyyyy=target_date.strftime("%d%m%Y"))
        log.info("bhavcopy_fetch", url=url, date=str(target_date))
        return cast(bytes, self.http.get(url))

    def parse(
        self, raw: bytes, target_date: date, checksum: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False, skipinitialspace=True)
        df.columns = strip_column_names(list(df.columns))
        required = {
            "SYMBOL",
            "SERIES",
            "OPEN_PRICE",
            "HIGH_PRICE",
            "LOW_PRICE",
            "CLOSE_PRICE",
            "PREV_CLOSE",
            "AVG_PRICE",
            "TTL_TRD_QNTY",
            "TURNOVER_LACS",
            "DELIV_QTY",
            "DELIV_PER",
        }
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"bhavcopy missing columns: {missing}")
        df["SERIES"] = df["SERIES"].str.strip()
        df = df[df["SERIES"].isin(SERIES_KEEP)].copy()

        rows: list[dict[str, Any]] = []
        quarantine: list[dict[str, Any]] = []
        for _, r in df.iterrows():
            sym = str(r["SYMBOL"]).strip()
            try:
                open_p = float(r["OPEN_PRICE"])
                high_p = float(r["HIGH_PRICE"])
                low_p = float(r["LOW_PRICE"])
                close_p = float(r["CLOSE_PRICE"])
                prev_close = float(r["PREV_CLOSE"])
                avg = float(r["AVG_PRICE"])

                if close_p == 0 and open_p == 0 and high_p == 0 and low_p == 0:
                    continue

                require_ohlc_consistency(open_p, high_p, low_p, close_p, f"{sym}: ")
                vol = int(float(r["TTL_TRD_QNTY"] or 0))
                turn_lacs = float(r["TURNOVER_LACS"] or 0)
                dq = int(float(r["DELIV_QTY"] or 0))
                dp = float(r["DELIV_PER"] or 0)

                candidate: dict[str, Any] = {
                    "symbol": sym,
                    "trade_date": target_date,
                    "open_price": open_p,
                    "high_price": high_p,
                    "low_price": low_p,
                    "close_price": close_p,
                    "prev_close": prev_close,
                    "adjusted_close": close_p,
                    "bhavcopy_avg_price": avg,
                    "session_avg_price": avg,
                    "volume": vol,
                    "delivery_qty": dq,
                    "delivery_pct": dp,
                    "delivery_value": (dq * avg) if dq and avg else None,
                    "traded_value": turn_lacs * 100_000.0,
                    "circuit_band": 20.0,
                    "data_source": self.SOURCE,
                    "raw_payload_checksum": checksum,
                }

                val_errors = validate_ohlc(candidate)
                if val_errors:
                    candidate["errors"] = val_errors
                    quarantine.append(candidate)
                    continue

                rows.append(candidate)
            except (ValueError, ValidationError) as e:
                log.warning("bhavcopy_row_skip", symbol=sym, error=str(e))
                quarantine.append({"symbol": sym, "error": str(e), "raw": r.to_dict()})
                continue

        if quarantine:
            self._write_quarantine(quarantine, target_date)

        return rows, quarantine

    def _write_quarantine(self, quarantine: list[dict[str, Any]], target_date: date) -> None:
        err_dir = Path("data/errors")
        err_dir.mkdir(parents=True, exist_ok=True)
        q_path = err_dir / f"quarantine_{target_date.isoformat()}.jsonl"
        with q_path.open("a", encoding="utf-8") as f:
            for item in quarantine:
                f.write(json.dumps(item, default=str) + "\n")

    def _decorate_52w_and_delivery(self, rows: list[dict[str, Any]], target_date: date) -> None:
        if not rows:
            return
        # 52-week window = 252 trading sessions per v6.5 Correction C-10
        window = getattr(self.config.ingestion, "high_52w_window_sessions", 252)
        symbols = [r["symbol"] for r in rows]
        hist = self.db.select_in(
            "daily_prices",
            "symbol",
            symbols,
            columns="symbol,trade_date,close_price,delivery_value,delivery_pct",
        )
        by_sym: dict[str, list[dict[str, Any]]] = {}
        for h in hist:
            by_sym.setdefault(h["symbol"], []).append(h)

        for r in rows:
            s = r["symbol"]
            prior = sorted(
                [h for h in by_sym.get(s, []) if str(h["trade_date"]) < str(target_date)],
                key=lambda x: str(x["trade_date"]),
            )
            closes = [float(h["close_price"]) for h in prior[-window:]]
            closes.append(float(r["close_price"]))
            r["high_52w"] = max(closes)
            r["low_52w"] = min(closes)

            dv_prior = [
                float(h["delivery_value"])
                for h in prior[-20:]
                if h.get("delivery_value") is not None
            ]
            today_dv = r.get("delivery_value")
            if today_dv is not None and len(dv_prior) >= 5:
                arr = np.array(dv_prior)
                r["delivery_percentile_20d"] = float(
                    (arr < today_dv).sum() / len(arr) * 100.0
                )
            else:
                r["delivery_percentile_20d"] = None

            dp5 = [float(h["delivery_pct"]) for h in prior[-4:]]
            dp5.append(float(r["delivery_pct"]))
            if len(dp5) >= 3:
                x = np.arange(len(dp5))
                r["delivery_trend_5d"] = float(np.polyfit(x, dp5, 1)[0])
            else:
                r["delivery_trend_5d"] = None

    def run(self, target_date: date) -> IngestResult:
        try:
            raw = self.fetch(target_date)
        except Exception as e:
            log.error("bhavcopy_fetch_failed", error=str(e))
            return IngestResult(self.SOURCE, status="FAILED", error=str(e))

        checksum = sha256_bytes(raw)
        try:
            rows, quarantine = self.parse(raw, target_date, checksum)
        except Exception as e:
            log.error("bhavcopy_parse_failed", error=str(e))
            return IngestResult(self.SOURCE, status="FAILED", checksum=checksum, error=str(e))

        if not rows:
            return IngestResult(
                self.SOURCE,
                status="SKIPPED",
                checksum=checksum,
                error="no valid EQ/BE rows",
            )

        known = {u["symbol"] for u in self.db.select("universe", columns="symbol")}
        valid_rows = [r for r in rows if r["symbol"] in known] if known else rows

        self._decorate_52w_and_delivery(valid_rows, target_date)

        try:
            n = self.db.upsert("daily_prices", valid_rows, on_conflict="symbol,trade_date")
        except Exception as e:
            log.error("bhavcopy_upsert_failed", error=str(e))
            return IngestResult(
                self.SOURCE,
                status="FAILED",
                checksum=checksum,
                rows_fetched=len(rows),
                error=str(e),
            )

        log.info("bhavcopy_done", rows=len(valid_rows), upserted=n, quarantined=len(quarantine))
        return IngestResult(
            self.SOURCE,
            status="SUCCESS",
            target_date=target_date,
            rows_fetched=len(rows) + len(quarantine),
            rows_valid=len(valid_rows),
            rows_rejected=len(quarantine),
            rows_upserted=n,
            rows_written=n,
            checksum=checksum,
        )
