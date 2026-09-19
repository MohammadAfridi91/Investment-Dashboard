"""
core/ingestion/nse_index_prices.py  (Source: N5)

Fetches the daily index-close file and fans it out to three tables:
NIFTY 500 / NIFTY 50 closes -> benchmark_prices, the 15 sector indices ->
sector_indices, India VIX + NIFTY 500 SMA(50)/SMA(200) -> a *partial*
market_regime row (only the columns this ingestor knows about -- the rest
of that table's columns are filled in by later-week modules and are left
untouched, since bulk_upsert's SET clause is built from whatever keys
are actually in each row dict).

Domain fix: same as nse_universe.py -- archives.nseindia.com ->
nsearchives.nseindia.com.

One thing NOT independently re-verified this session (unlike bhavcopy,
where the UDiFF change was confirmed directly): the exact column header
names below (`Index Name`, `Closing Index Value`, etc.) are NSE's
long-stable index-summary format, which wasn't part of the UDiFF change
-- but worth a first-run sanity check against the real header row rather
than taking on full faith.
"""
from datetime import date, timedelta
from typing import Any

from core.ingestion.base import Ingestor
from core.utils.http import fetch as http_fetch
from core.utils.http import get_session

BASE_URL = "https://nsearchives.nseindia.com/content/indices"

BENCHMARK_INDICES = {"NIFTY 500", "NIFTY 50"}

SECTOR_INDICES = {
    "NIFTY IT", "NIFTY PHARMA", "NIFTY AUTO", "NIFTY FMCG", "NIFTY METAL",
    "NIFTY ENERGY", "NIFTY REALTY", "NIFTY INFRA", "NIFTY MEDIA",
    "NIFTY CAPITAL GOODS", "NIFTY CONSUMER DURABLES", "NIFTY HEALTHCARE",
    "NIFTY INDIA DEFENCE", "NIFTY RAILWAYS", "NIFTY CHEMICALS",
}


class NSEIndexPricesIngestor(Ingestor):
    SOURCE = "nse_index_prices"
    SCHEDULE = "daily"

    def fetch(self, target_date: date) -> bytes:
        session = get_session()
        filename = f"ind_close_all_{target_date.strftime('%d%m%Y')}.csv"
        return http_fetch(session, f"{BASE_URL}/{filename}", delay_ms=500)

    def parse(self, raw: bytes, target_date: date) -> list[dict[str, Any]]:
        import csv
        import io

        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))

        rows: list[dict[str, Any]] = []
        india_vix_close = None

        for row in reader:
            name = (row.get("Index Name") or "").strip()
            close_str = row.get("Closing Index Value")
            if not name or not close_str:
                continue
            try:
                close_price = float(close_str)
            except ValueError:
                continue

            if name.upper() == "INDIA VIX":
                india_vix_close = close_price
                continue

            if name in BENCHMARK_INDICES:
                rows.append({
                    "_target_table": "benchmark_prices",
                    "symbol": name,
                    "trade_date": target_date,
                    "close_price": close_price,
                    "volume": self._safe_int(row.get("Volume")),
                })
            elif name in SECTOR_INDICES:
                rows.append({
                    "_target_table": "sector_indices",
                    "index_symbol": name,
                    "trade_date": target_date,
                    "close_price": close_price,
                })

        nifty500_close = next(
            (r["close_price"] for r in rows
             if r["_target_table"] == "benchmark_prices" and r["symbol"] == "NIFTY 500"),
            None,
        )
        if nifty500_close is not None:
            sma50, sma200 = self._nifty500_smas(target_date, nifty500_close)
            regime_row = {"_target_table": "market_regime", "trade_date": target_date}
            if india_vix_close is not None:
                regime_row["india_vix"] = india_vix_close
            regime_row["nifty_500_close"] = nifty500_close
            if sma50 is not None:
                regime_row["nifty_500_sma_50"] = sma50
            if sma200 is not None:
                regime_row["nifty_500_sma_200"] = sma200
            rows.append(regime_row)

        return rows

    @staticmethod
    def _safe_int(val: str | None) -> int | None:
        if not val:
            return None
        try:
            return int(float(val))
        except ValueError:
            return None

    @staticmethod
    def _nifty500_smas(
        target_date: date, today_close: float
    ) -> tuple[float | None, float | None]:
        """Trailing SMA(50)/SMA(200) for NIFTY 500, including today's
        just-parsed close. Looks back 280 calendar days (>> 200 trading
        sessions, generous margin for weekends/holidays) via one bulk
        SQL query rather than per-day round trips."""
        from core.database.client import get_client

        client = get_client()
        lookback_start = target_date - timedelta(days=280)
        with client.pg() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT close_price FROM benchmark_prices
                WHERE symbol = 'NIFTY 500'
                  AND trade_date >= %s AND trade_date < %s
                ORDER BY trade_date DESC
                LIMIT 199
                """,
                (lookback_start, target_date),
            )
            history = [row[0] for row in cur.fetchall()]

        closes = [today_close, *history]
        sma50 = sum(closes[:50]) / len(closes[:50]) if closes else None
        sma200 = sum(closes[:200]) / len(closes[:200]) if closes else None
        return sma50, sma200

    def validate(
        self, rows: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        valid, rejected = [], []
        for r in rows:
            if r["_target_table"] in ("benchmark_prices", "sector_indices") and \
                    (r.get("close_price") is None or r["close_price"] <= 0):
                rejected.append({**r, "_validation_errors": ["non-positive close_price"]})
            else:
                valid.append(r)
        return valid, rejected

    def upsert(self, rows: list[dict[str, Any]]) -> int:
        from core.database.client import get_client

        client = get_client()
        by_table: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            r = dict(r)
            table = r.pop("_target_table")
            by_table.setdefault(table, []).append(r)

        conflict_cols = {
            "benchmark_prices": ["symbol", "trade_date"],
            "sector_indices": ["index_symbol", "trade_date"],
            "market_regime": ["trade_date"],
        }
        written = 0
        for table, table_rows in by_table.items():
            written += client.bulk_upsert(table, table_rows, conflict_cols[table])
        return written
