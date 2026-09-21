import textwrap
from datetime import date
from typing import Any

from core.ingestion.nse_bhavcopy import NSEBhavcopyIngestor
from core.utils.checksums import sha256_bytes

CSV = textwrap.dedent("""\
    SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER
    TCS, EQ, 02-Jan-2026, 3900.00, 3920.00, 3960.00, 3905.00, 3950.00, 3950.00, 3930.00, 1200000, 47000.00, 50000, 800000, 66.67
    RELIANCE, EQ, 02-Jan-2026, 2500.00, 2510.00, 2540.00, 2505.00, 2530.00, 2530.00, 2520.00, 2500000, 63000.00, 80000, 1500000, 60.00
    SOMEBOND, N1, 02-Jan-2026, 100.00, 100.00, 100.00, 100.00, 100.00, 100.00, 100.00, 0, 0, 0, 0, 0.00
    NOTRADE, EQ, 02-Jan-2026, 50.00, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
""").encode()


class DummyDB:
    def select(self, *a: Any, **k: Any) -> list[dict[str, Any]]:
        return []

    def select_in(self, *a: Any, **k: Any) -> list[dict[str, Any]]:
        return []

    def upsert(self, *a: Any, **k: Any) -> int:
        return 0


class IngestionSettings:
    high_52w_window_sessions = 252


class DummyCfg:
    ingestion = IngestionSettings()


def _ingestor() -> NSEBhavcopyIngestor:
    return NSEBhavcopyIngestor(http=None, db=DummyDB(), config=DummyCfg())  # type: ignore[arg-type]


def test_parse_filters_non_eq() -> None:
    rows, _ = _ingestor().parse(CSV, date(2026, 1, 2), sha256_bytes(CSV))
    syms = {r["symbol"] for r in rows}
    assert "TCS" in syms and "RELIANCE" in syms
    assert "SOMEBOND" not in syms


def test_parse_skips_zero_ohlc() -> None:
    rows, _ = _ingestor().parse(CSV, date(2026, 1, 2), sha256_bytes(CSV))
    assert all(r["symbol"] != "NOTRADE" for r in rows)


def test_parse_computes_traded_value() -> None:
    rows, _ = _ingestor().parse(CSV, date(2026, 1, 2), sha256_bytes(CSV))
    tcs = next(r for r in rows if r["symbol"] == "TCS")
    assert tcs["traded_value"] == 47000.00 * 100_000
    assert tcs["session_avg_price"] == 3930.00
    assert tcs["delivery_value"] == 800000 * 3930.00


def test_parse_checksum_propagated() -> None:
    chk = sha256_bytes(CSV)
    rows, _ = _ingestor().parse(CSV, date(2026, 1, 2), chk)
    assert all(r["raw_payload_checksum"] == chk for r in rows)
