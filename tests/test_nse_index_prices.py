import textwrap
from datetime import date
from typing import Any

from core.ingestion.nse_index_prices import NSEIndexPricesIngestor
from core.utils.checksums import sha256_bytes

CSV = textwrap.dedent("""\
    Index Name, Index Date, Open Index Value, High Index Value, Low Index Value, Closing Index Value, Volume, Turnover (Rs. Cr.), P/E, P/B, Div Yield
    NIFTY 50, 02-Jan-2026, 21500.00, 21600.00, 21400.00, 21550.00, 0, 250000.00, 22.0, 3.5, 1.2
    NIFTY 500, 02-Jan-2026, 19500.00, 19600.00, 19400.00, 19550.00, 0, 300000.00, 20.0, 3.0, 1.3
    INDIA VIX, 02-Jan-2026, 14.50, 15.50, 14.00, 15.20, 0, 0, 0, 0, 0
    NIFTY IT, 02-Jan-2026, 40000.00, 40400.00, 39800.00, 40200.00, 0, 5000.00, 28.0, 8.0, 2.0
    NIFTY BANK, 02-Jan-2026, 48000.00, 48200.00, 47800.00, 48100.00, 0, 10000.00, 18.0, 2.5, 0.8
""").encode()


class DummyDB:
    def upsert(self, *a: Any, **k: Any) -> int:
        return 0

    def select(self, *a: Any, **k: Any) -> list[dict[str, Any]]:
        return []


class DummyCfg:
    pass


def test_parse_slices_benchmarks_sectors_vix() -> None:
    ing = NSEIndexPricesIngestor(http=None, db=DummyDB(), config=DummyCfg())  # type: ignore[arg-type]
    b, s, v = ing.parse(CSV, date(2026, 1, 2), sha256_bytes(CSV))
    bench_syms = {x["symbol"] for x in b}
    sect_syms = {x["index_symbol"] for x in s}
    assert "NIFTY 500" in bench_syms and "NIFTY 50" in bench_syms
    assert "NIFTY IT" in sect_syms
    assert "NIFTY BANK" not in sect_syms
    assert v == {"india_vix": 15.20}
