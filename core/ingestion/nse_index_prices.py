from __future__ import annotations

import io
from datetime import date
from typing import Any, cast

import pandas as pd

from core.database.client import DB
from core.ingestion.base import Ingestor, IngestResult
from core.utils.checksums import sha256_bytes
from core.utils.logging import get_logger
from core.utils.normalization import strip_column_names

log = get_logger("ingest.index")

URL = "https://archives.nseindia.com/content/indices/ind_close_all_{ddmmyyyy}.csv"

BENCHMARKS = {"NIFTY 500", "NIFTY 50"}
VIX_KEY = "INDIA VIX"
SECTOR_INDICES = {
    "NIFTY IT",
    "NIFTY PHARMA",
    "NIFTY AUTO",
    "NIFTY FMCG",
    "NIFTY METAL",
    "NIFTY ENERGY",
    "NIFTY REALTY",
    "NIFTY INFRA",
    "NIFTY MEDIA",
    "NIFTY CAPITAL GOODS",
    "NIFTY CONSUMER DURABLES",
    "NIFTY HEALTHCARE",
    "NIFTY INDIA DEFENCE",
    "NIFTY RAILWAYS",
    "NIFTY CHEMICALS",
}


class NSEIndexPricesIngestor(Ingestor):
    SOURCE = "nse_index_prices"
    SCHEDULE = "EOD"

    def __init__(self, http: Any, db: DB, config: Any) -> None:
        self.http = http
        self.db = db
        self.config = config

    def fetch(self, target_date: date) -> bytes:
        url = URL.format(ddmmyyyy=target_date.strftime("%d%m%Y"))
        log.info("index_fetch", url=url)
        return cast(bytes, self.http.get(url))

    def parse(
        self, raw: bytes, target_date: date, checksum: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
        df = pd.read_csv(io.BytesIO(raw))
        df.columns = strip_column_names(list(df.columns))
        name_col = "Index Name"
        close_col = "Closing Index Value"
        vol_col = "Volume"
        if name_col not in df.columns or close_col not in df.columns:
            raise ValueError(f"unexpected columns: {list(df.columns)}")

        benchmarks: list[dict[str, Any]] = []
        sectors: list[dict[str, Any]] = []
        vix_row: dict[str, Any] | None = None
        for _, r in df.iterrows():
            name = str(r[name_col]).strip()
            try:
                close = float(r[close_col])
            except (TypeError, ValueError):
                continue
            vol = None
            if vol_col in df.columns:
                try:
                    vol = int(float(r[vol_col]))
                except (TypeError, ValueError):
                    vol = None
            if name in BENCHMARKS:
                benchmarks.append(
                    {
                        "symbol": name,
                        "trade_date": target_date,
                        "close_price": close,
                        "volume": vol,
                        "raw_payload_checksum": checksum,
                    }
                )
            if name in SECTOR_INDICES:
                sectors.append(
                    {
                        "index_symbol": name,
                        "trade_date": target_date,
                        "close_price": close,
                        "raw_payload_checksum": checksum,
                    }
                )
            if name.upper() == VIX_KEY:
                vix_row = {"india_vix": close}
        return benchmarks, sectors, vix_row

    def run(self, target_date: date) -> IngestResult:
        try:
            raw = self.fetch(target_date)
        except Exception as e:
            log.error("index_fetch_failed", error=str(e))
            return IngestResult(self.SOURCE, status="FAILED", error=str(e))

        checksum = sha256_bytes(raw)
        try:
            benchmarks, sectors, vix = self.parse(raw, target_date, checksum)
        except Exception as e:
            log.error("index_parse_failed", error=str(e))
            return IngestResult(self.SOURCE, status="FAILED", checksum=checksum, error=str(e))

        if benchmarks:
            self.db.upsert("benchmark_prices", benchmarks, on_conflict="symbol,trade_date")
        if sectors:
            self.db.upsert("sector_indices", sectors, on_conflict="index_symbol,trade_date")

        n500 = next((b for b in benchmarks if b["symbol"] == "NIFTY 500"), None)
        sma50: float | None = None
        sma200: float | None = None
        trend: str | None = None

        if n500:
            try:
                prior_b = self.db.select(
                    "benchmark_prices",
                    columns="trade_date,close_price",
                    filters={"symbol": "NIFTY 500"},
                    order="trade_date.desc",
                    limit=250,
                )
                closes = [
                    float(b["close_price"])
                    for b in prior_b
                    if str(b.get("trade_date")) != str(target_date)
                ]
                closes.insert(0, float(n500["close_price"]))
                if len(closes) >= 50:
                    sma50 = round(sum(closes[:50]) / 50.0, 2)
                if len(closes) >= 200:
                    sma200 = round(sum(closes[:200]) / 200.0, 2)
                if sma50 and sma200:
                    trend = "BULLISH" if sma50 > sma200 else "BEARISH"
            except Exception:
                pass

        regime_row: dict[str, Any] = {
            "trade_date": target_date,
            "india_vix": vix["india_vix"] if vix else None,
            "nifty_500_close": n500["close_price"] if n500 else None,
            "nifty_500_sma_50": sma50,
            "nifty_500_sma_200": sma200,
            "nifty_trend": trend,
        }
        self.db.upsert("market_regime", [regime_row], on_conflict="trade_date")

        total = len(benchmarks) + len(sectors)
        log.info("index_done", benchmarks=len(benchmarks), sectors=len(sectors))
        return IngestResult(
            self.SOURCE,
            status="SUCCESS",
            target_date=target_date,
            rows_fetched=total,
            rows_valid=total,
            rows_upserted=total,
            rows_written=total,
            checksum=checksum,
        )
