"""
core/ingestion/nse_bhavcopy.py  (rewritten against UDiFF; plan targeted
the discontinued sec_bhavdata_full format -- see learnings.md)

NSE discontinued the old equity bhavcopy CSV (sec_bhavdata_full_DDMMYYYY,
plain CSV, column names like SYMBOL/CLOSE/DELIV_PER) on 2024-07-08,
replacing it with UDiFF: a zip containing a CSV with different columns
(TckrSymb/ClsPric/etc.), at a different domain
(nsearchives.nseindia.com, not archives.nseindia.com).

OHLC/volume/turnover below is written against the confirmed, live UDiFF
format. Two things follow from the format change that the plan didn't
anticipate:

1. UDiFF has no direct average-price column (the old format's AVG_PRICE).
   bhavcopy_avg_price is computed as traded_value / volume instead --
   mathematically a volume-weighted average price, which is what
   AVG_PRICE was approximating anyway.

2. Delivery quantity/percentage is NOT in the UDiFF bhavcopy at all --
   post-UDiFF it's a separate NSE report, and this session's research
   didn't turn up its exact bulk-download URL (see
   scripts/probe_delivery_source.py, meant to be run somewhere with real
   NSE access to nail it down empirically). Until that's resolved,
   delivery_qty/delivery_pct/delivery_value/delivery_percentile_20d/
   delivery_trend_5d are all left NULL -- NOT a guessed value -- via
   migration 009, which dropped the NOT NULL constraint on
   delivery_qty/delivery_pct specifically because storing 0 here would
   look like real "zero delivery" data to every downstream calc.
   compute_delivery_percentile_20d() and compute_delivery_trend_5d() are
   written and ready; they'll just work the moment delivery_value starts
   arriving from a real source, without needing to be revisited.
"""
import zipfile
from datetime import date, timedelta
from io import BytesIO
from typing import Any

from core.ingestion.base import Ingestor
from core.utils.http import fetch as http_fetch
from core.utils.http import get_session
from core.utils.validation import validate_ohlc

BASE_URL = "https://nsearchives.nseindia.com/content/cm"
VALID_SERIES = {"EQ", "BE"}

# 52w window per correction C-10: 252 trading sessions, not the 375-session
# backfill depth. 380 calendar days back is a generous margin over 252
# trading sessions (accounts for weekends + ~12-14 holidays/year).
LOOKBACK_52W_DAYS = 380
DELIVERY_PERCENTILE_WINDOW = 20


class NSEBhavcopyIngestor(Ingestor):
    SOURCE = "nse_bhavcopy"
    SCHEDULE = "daily EOD"

    def fetch(self, target_date: date) -> bytes:
        session = get_session()
        filename = f"BhavCopy_NSE_CM_0_0_0_{target_date.strftime('%Y%m%d')}_F_0000.csv.zip"
        return http_fetch(session, f"{BASE_URL}/{filename}", delay_ms=500)

    def parse(self, raw: bytes, target_date: date) -> list[dict[str, Any]]:
        import csv
        import io

        with zipfile.ZipFile(BytesIO(raw)) as zf:
            csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            text = zf.read(csv_name).decode("utf-8-sig")

        reader = csv.DictReader(io.StringIO(text))
        rows: list[dict[str, Any]] = []

        for row in reader:
            series = (row.get("SctySrs") or "").strip()
            if series not in VALID_SERIES:
                continue

            try:
                open_price = float(row["OpnPric"])
                high_price = float(row["HghPric"])
                low_price = float(row["LwPric"])
                close_price = float(row["ClsPric"])
                prev_close = float(row["PrvsClsgPric"])
                volume = int(float(row["TtlTradgVol"]))
                traded_value = float(row["TtlTrfVal"])
            except (KeyError, ValueError):
                continue

            avg_price = round(traded_value / volume, 4) if volume > 0 else close_price

            rows.append({
                "symbol": row["TckrSymb"].strip(),
                "trade_date": target_date,
                "open_price": open_price,
                "high_price": high_price,
                "low_price": low_price,
                "close_price": close_price,
                "prev_close": prev_close,
                "adjusted_close": close_price,  # Week 1: apply_adjustments() stub is identity
                "bhavcopy_avg_price": avg_price,
                "session_avg_price": avg_price,
                "volume": volume,
                "delivery_qty": None,   # see module docstring
                "delivery_pct": None,   # see module docstring
                "delivery_value": None,
                "delivery_percentile_20d": None,
                "delivery_trend_5d": None,
                "traded_value": traded_value,
                "data_source": "nse_udiff_bhavcopy",
            })

        self._fill_52w_high_low(rows, target_date)
        return rows

    @staticmethod
    def _fill_52w_high_low(rows: list[dict[str, Any]], target_date: date) -> None:
        """One bulk query for all symbols' trailing high/low, rather than
        900 individual round trips."""
        from core.database.client import get_client

        if not rows:
            return

        symbols = [r["symbol"] for r in rows]
        client = get_client()
        lookback_start = target_date - timedelta(days=LOOKBACK_52W_DAYS)

        with client.pg() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT symbol, MAX(high_price), MIN(low_price)
                FROM daily_prices
                WHERE trade_date >= %s AND trade_date < %s
                  AND symbol = ANY(%s)
                GROUP BY symbol
                """,
                (lookback_start, target_date, symbols),
            )
            history = {sym: (hi, lo) for sym, hi, lo in cur.fetchall()}

        for r in rows:
            hist_h, hist_l = history.get(r["symbol"], (None, None))
            r["high_52w"] = max(r["high_price"], hist_h) if hist_h is not None else r["high_price"]
            r["low_52w"] = min(r["low_price"], hist_l) if hist_l is not None else r["low_price"]

    def validate(
        self, rows: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        valid, rejected = [], []
        for r in rows:
            # validate_ohlc's delivery_qty > volume check needs a number;
            # delivery_qty is genuinely None right now (see docstring), so
            # substitute 0 for JUST this check -- 0 can never exceed a
            # non-negative volume, so it's a true no-op, not a smuggled
            # default into the stored row (r itself is untouched).
            check_row = {**r, "delivery_qty": r["delivery_qty"] or 0}
            errs = validate_ohlc(check_row)
            if errs:
                rejected.append({**r, "_validation_errors": errs})
            else:
                valid.append(r)
        return valid, rejected

    def upsert(self, rows: list[dict[str, Any]]) -> int:
        from core.database.client import get_client

        client = get_client()
        return client.bulk_upsert("daily_prices", rows, conflict_cols=["symbol", "trade_date"])


def compute_delivery_percentile_20d(
    today_delivery_value: float | None, prior_20_values: list[float]
) -> float | None:
    """Percentile rank of today's delivery_value vs the prior 20 sessions
    (excluding today), per plan step 8. Returns None while delivery_value
    is unavailable -- ready to use the moment it isn't."""
    if today_delivery_value is None or not prior_20_values:
        return None
    below = sum(1 for v in prior_20_values if v < today_delivery_value)
    return round(100 * below / len(prior_20_values), 2)


def compute_delivery_trend_5d(last_5_values: list[float]) -> float | None:
    """Linear slope over the last 5 sessions' delivery_value, per plan
    step 9. Returns None until delivery_value is available."""
    if len(last_5_values) < 5:
        return None
    n = len(last_5_values)
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(last_5_values) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, last_5_values, strict=True))
    den = sum((x - x_mean) ** 2 for x in xs)
    return round(num / den, 4) if den else None
