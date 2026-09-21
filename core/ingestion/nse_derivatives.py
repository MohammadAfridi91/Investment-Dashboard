from __future__ import annotations

import io
import zipfile
from datetime import date, datetime
from typing import Any, cast

import numpy as np
import pandas as pd

from core.config import Config
from core.database.client import DB
from core.ingestion.base import Ingestor, IngestResult
from core.utils.checksums import sha256_bytes
from core.utils.logging import get_logger
from core.utils.normalization import strip_column_names

log = get_logger("ingest.derivatives")

BHAVCOPY_URL_TEMPLATE = (
    "https://archives.nseindia.com/content/historical/DERIVATIVES/"
    "{year}/{month}/fo{dd}{month}{year}bhav.csv.zip"
)
MWPL_URL_TEMPLATE = "https://archives.nseindia.com/content/nsccl/cor_mwp_{ddmmyyyy}.csv"
BAN_LIST_URL = "https://archives.nseindia.com/content/fo/fo_secban.csv"


def _parse_date_str(s: str) -> date | None:
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


class NSEDerivativesIngestor(Ingestor):
    SOURCE = "nse_derivatives"
    SCHEDULE = "EOD"

    def __init__(self, http: Any, db: DB, config: Config) -> None:
        self.http = http
        self.db = db
        self.config = config

    def fetch_bhavcopy(self, target_date: date) -> bytes:
        urls = [
            f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{target_date.strftime('%Y%m%d')}_F_0000.csv.zip",
            BHAVCOPY_URL_TEMPLATE.format(
                year=target_date.strftime("%Y"),
                month=target_date.strftime("%b").upper(),
                dd=target_date.strftime("%d"),
            ),
            (
                "https://nsearchives.nseindia.com/content/historical/DERIVATIVES/"
                f"{target_date.strftime('%Y')}/{target_date.strftime('%b').upper()}/"
                f"fo{target_date.strftime('%d')}{target_date.strftime('%b').upper()}{target_date.strftime('%Y')}bhav.csv.zip"
            ),
        ]
        last_err: Exception | None = None
        for url in urls:
            log.info("derivatives_fetch_bhavcopy", url=url)
            try:
                return cast(bytes, self.http.get(url))
            except Exception as e:
                last_err = e
        raise RuntimeError(f"Failed to fetch F&O bhavcopy from all endpoints: {last_err}")

    def fetch_mwpl(self, target_date: date) -> bytes | None:
        url = MWPL_URL_TEMPLATE.format(ddmmyyyy=target_date.strftime("%d%m%Y"))
        log.info("derivatives_fetch_mwpl", url=url)
        try:
            return cast(bytes, self.http.get(url))
        except Exception as e:
            log.warning("derivatives_mwpl_fetch_failed", error=str(e))
            return None

    def fetch_ban_list(self) -> bytes | None:
        log.info("derivatives_fetch_ban_list", url=BAN_LIST_URL)
        try:
            return cast(bytes, self.http.get(BAN_LIST_URL))
        except Exception as e:
            log.warning("derivatives_ban_list_fetch_failed", error=str(e))
            return None

    def _extract_csv_bytes(self, raw: bytes) -> bytes:
        if raw.startswith(b"PK"):
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                name = zf.namelist()[0]
                return zf.read(name)
        return raw

    def parse_mwpl(self, raw: bytes | None) -> dict[str, float]:
        if not raw:
            return {}
        try:
            df = pd.read_csv(io.BytesIO(raw), dtype=str, skipinitialspace=True)
            df.columns = strip_column_names(list(df.columns))
            sym_col = next((c for c in df.columns if "SYMBOL" in c.upper()), None)
            util_col = next(
                (c for c in df.columns if any(k in c.upper() for k in ("UTILIZATION", "LIMIT EXHAUSTED", "PERCENT"))),
                None,
            )
            if not sym_col or not util_col:
                return {}
            result: dict[str, float] = {}
            for _, r in df.iterrows():
                s = str(r[sym_col]).strip()
                try:
                    val = float(str(r[util_col]).replace("%", "").strip())
                    result[s] = val
                except (ValueError, TypeError):
                    continue
            return result
        except Exception as e:
            log.warning("derivatives_mwpl_parse_error", error=str(e))
            return {}

    def parse_ban_list(self, raw: bytes | None) -> set[str]:
        if not raw:
            return set()
        try:
            text = raw.decode("utf-8-sig", errors="ignore")
            banned: set[str] = set()
            for line in text.splitlines():
                s = line.strip().strip(",")
                if s and not s.lower().startswith("securities in ban") and not s.lower().startswith("symbol"):
                    banned.add(s)
            return banned
        except Exception as e:
            log.warning("derivatives_ban_parse_error", error=str(e))
            return set()

    def parse_bhavcopy(
        self,
        raw_csv: bytes,
        target_date: date,
        mwpl_map: dict[str, float],
        ban_set: set[str],
    ) -> tuple[list[dict[str, Any]], set[str]]:
        df = pd.read_csv(io.BytesIO(raw_csv), dtype=str, skipinitialspace=True)
        df.columns = strip_column_names(list(df.columns))

        if "TckrSymb" in df.columns:
            col_map = {
                "TckrSymb": "SYMBOL",
                "XpryDt": "EXPIRY_DT",
                "StrkPric": "STRIKE_PR",
                "OptnTp": "OPTION_TYP",
                "OpnIntrst": "OPEN_INT",
                "ChngInOpnIntrst": "CHG_IN_OI",
                "ClsPric": "CLOSE",
                "SttlmPric": "SETTLE_PR",
                "UndrlygPric": "UNDERLYING",
            }
            df.rename(columns=col_map, inplace=True)
            inst_map = {
                "STF": "FUTSTK",
                "STO": "OPTSTK",
                "IDF": "FUTIDX",
                "IDO": "OPTIDX",
            }
            if "FinInstrmTp" in df.columns:
                df["INSTRUMENT"] = df["FinInstrmTp"].str.strip().map(lambda x: inst_map.get(x, x))

        req_cols = {"INSTRUMENT", "SYMBOL", "EXPIRY_DT", "OPEN_INT"}
        if not req_cols.issubset(set(df.columns)):
            raise ValueError(f"F&O bhavcopy missing required columns: {req_cols - set(df.columns)}")

        df["INSTRUMENT"] = df["INSTRUMENT"].str.strip()
        df["SYMBOL"] = df["SYMBOL"].str.strip()

        futstk = df[df["INSTRUMENT"] == "FUTSTK"].copy()
        optstk = df[df["INSTRUMENT"] == "OPTSTK"].copy()

        fno_symbols = set(futstk["SYMBOL"].unique())
        if not fno_symbols:
            return [], set()

        # Fetch spot prices for today from daily_prices
        spot_rows = self.db.select_in(
            "daily_prices",
            "symbol",
            list(fno_symbols),
            columns="symbol,trade_date,close_price",
        )
        spot_map = {
            r["symbol"]: float(r["close_price"])
            for r in spot_rows
            if str(r.get("trade_date")) == str(target_date) and r.get("close_price") is not None
        }

        # Pre-fetch prior derivative metrics for symbols to calculate deltas
        prior_rows = self.db.select_in(
            "derivative_metrics",
            "symbol",
            list(fno_symbols),
            columns="symbol,trade_date,fno_oi,cost_of_carry,pcr,basis_pct,rollover_pct",
        )
        prior_by_sym: dict[str, list[dict[str, Any]]] = {}
        for pr in prior_rows:
            if str(pr.get("trade_date")) < str(target_date):
                prior_by_sym.setdefault(pr["symbol"], []).append(pr)

        rows: list[dict[str, Any]] = []

        for sym, sym_futs in futstk.groupby("SYMBOL"):
            sym_str = str(sym)
            contracts: list[dict[str, Any]] = []
            for _, r in sym_futs.iterrows():
                exp = _parse_date_str(str(r["EXPIRY_DT"]))
                if not exp:
                    continue
                try:
                    oi = int(float(r["OPEN_INT"]))
                    chg_oi = int(float(r.get("CHG_IN_OI", 0) or 0))
                    close_p = float(r.get("CLOSE", 0) or r.get("SETTLE_PR", 0) or 0)
                except (ValueError, TypeError):
                    continue
                contracts.append({"expiry": exp, "oi": oi, "chg_oi": chg_oi, "close": close_p})

            if not contracts:
                continue

            contracts.sort(key=lambda x: x["expiry"])
            near = contracts[0]
            next_month = contracts[1] if len(contracts) > 1 else None

            total_oi = sum(c["oi"] for c in contracts)
            spot = spot_map.get(sym_str)

            # Prior metrics
            priors = sorted(prior_by_sym.get(sym_str, []), key=lambda x: str(x["trade_date"]), reverse=True)
            prev = priors[0] if priors else None

            prev_oi = int(prev["fno_oi"]) if prev and prev.get("fno_oi") is not None else None
            oi_change = (total_oi - prev_oi) if prev_oi is not None else sum(c["chg_oi"] for c in contracts)
            prev_coc = float(prev["cost_of_carry"]) if prev and prev.get("cost_of_carry") is not None else None
            prev_pcr = float(prev["pcr"]) if prev and prev.get("pcr") is not None else None
            prev_basis = float(prev["basis_pct"]) if prev and prev.get("basis_pct") is not None else None

            # 20d rollover avg
            roll_hist = [float(p["rollover_pct"]) for p in priors[:20] if p.get("rollover_pct") is not None]
            avg_roll_20d = round(float(np.mean(roll_hist)), 2) if roll_hist else None

            # Cost of Carry & Basis calculation
            # If near expiry <= 3 days away, use next-month contract
            coc_contract = near
            days_to_exp = (near["expiry"] - target_date).days
            if days_to_exp <= 3 and next_month:
                coc_contract = next_month
                days_to_exp = (next_month["expiry"] - target_date).days

            coc: float | None = None
            basis: float | None = None
            basis_pct: float | None = None
            if spot and spot > 0 and days_to_exp > 0 and coc_contract["close"] > 0:
                f_price = coc_contract["close"]
                coc = round(((f_price - spot) / spot) * (365.0 / days_to_exp) * 100.0, 4)
                basis = round(f_price - spot, 2)
                basis_pct = round((basis / spot) * 100.0, 4)

            # Rollover %
            rollover_pct: float | None = None
            if next_month and (near["oi"] + next_month["oi"]) > 0:
                rollover_pct = round((next_month["oi"] / (near["oi"] + next_month["oi"])) * 100.0, 2)

            # PCR and Max Pain from OPTSTK
            pcr: float | None = None
            max_pain: float | None = None
            sym_opts = optstk[optstk["SYMBOL"] == sym_str] if not optstk.empty else pd.DataFrame()

            if not sym_opts.empty:
                pe_oi = 0
                ce_oi = 0
                strike_map: dict[float, dict[str, int]] = {}

                for _, r in sym_opts.iterrows():
                    typ = str(r.get("OPTION_TYP", "")).strip().upper()
                    try:
                        stk = float(r["STRIKE_PR"])
                        oi_val = int(float(r["OPEN_INT"]))
                    except (ValueError, TypeError):
                        continue

                    if typ == "PE":
                        pe_oi += oi_val
                        strike_map.setdefault(stk, {"CE": 0, "PE": 0})["PE"] += oi_val
                    elif typ == "CE":
                        ce_oi += oi_val
                        strike_map.setdefault(stk, {"CE": 0, "PE": 0})["CE"] += oi_val

                if ce_oi > 0:
                    pcr = round(pe_oi / ce_oi, 4)

                # Max pain calculation
                if strike_map:
                    strikes = sorted(strike_map.keys())
                    min_pain = float("inf")
                    best_strike = strikes[0]
                    for s in strikes:
                        pain = 0.0
                        for k, v in strike_map.items():
                            if s > k:
                                pain += (s - k) * v["CE"]
                            elif s < k:
                                pain += (k - s) * v["PE"]
                        if pain < min_pain:
                            min_pain = pain
                            best_strike = s
                    max_pain = float(best_strike)

            oi_pcr_change = round(pcr - prev_pcr, 4) if (pcr is not None and prev_pcr is not None) else None

            candidate: dict[str, Any] = {
                "symbol": sym_str,
                "trade_date": target_date.isoformat(),
                "fno_oi": total_oi,
                "fno_oi_change": oi_change,
                "prev_fno_oi": prev_oi,
                "cost_of_carry": coc,
                "prev_cost_of_carry": prev_coc,
                "pcr": pcr,
                "prev_pcr": prev_pcr,
                "oi_pcr_change": oi_pcr_change,
                "mwpl_pct": mwpl_map.get(sym_str),
                "is_fno_ban": sym_str in ban_set,
                "has_institutional_net_buy": False,
                "rollover_pct": rollover_pct,
                "avg_rollover_pct_20d": avg_roll_20d,
                "basis": basis,
                "basis_pct": basis_pct,
                "prev_basis_pct": prev_basis,
                "iv_skew": None,
                "max_pain": max_pain,
                "oi_concentration_top5": None,
                "spot_price": spot,
            }
            rows.append(candidate)

        return rows, fno_symbols

    def _sync_universe_fno(self, fno_symbols: set[str]) -> None:
        """Update universe.is_fno = TRUE for F&O symbols."""
        try:
            univ = self.db.select("universe", columns="symbol,company_name,isin,is_fno")
            if not univ:
                return
            to_update: list[dict[str, Any]] = []
            for u in univ:
                s = u["symbol"]
                is_fno = s in fno_symbols
                if u.get("is_fno") != is_fno:
                    u["is_fno"] = is_fno
                    to_update.append(u)
            if to_update:
                self.db.upsert("universe", to_update, on_conflict="symbol")
                log.info("derivatives_sync_universe_fno", updated=len(to_update))
        except Exception as e:
            log.warning("derivatives_universe_fno_sync_failed", error=str(e))

    def run(self, target_date: date) -> IngestResult:
        t0 = self._timer()
        try:
            raw_bhav = self.fetch_bhavcopy(target_date)
        except Exception as e:
            log.error("derivatives_bhavcopy_fetch_failed", error=str(e))
            return IngestResult(self.SOURCE, status="FAILED", error=str(e))

        checksum = sha256_bytes(raw_bhav)
        raw_csv = self._extract_csv_bytes(raw_bhav)

        raw_mwpl = self.fetch_mwpl(target_date)
        mwpl_map = self.parse_mwpl(raw_mwpl)

        raw_ban = self.fetch_ban_list()
        ban_set = self.parse_ban_list(raw_ban)

        try:
            rows, fno_symbols = self.parse_bhavcopy(raw_csv, target_date, mwpl_map, ban_set)
        except Exception as e:
            log.error("derivatives_parse_failed", error=str(e))
            return IngestResult(self.SOURCE, status="FAILED", checksum=checksum, error=str(e))

        if not rows:
            return IngestResult(self.SOURCE, status="SKIPPED", checksum=checksum, error="no rows parsed")

        # Sync is_fno flag to universe
        self._sync_universe_fno(fno_symbols)

        # Write to derivative_metrics only for symbols known in universe to preserve FK
        known = {u["symbol"] for u in self.db.select("universe", columns="symbol")}
        valid_rows = [r for r in rows if r["symbol"] in known] if known else rows

        written = 0
        if valid_rows:
            try:
                written = self.db.upsert("derivative_metrics", valid_rows, on_conflict="symbol,trade_date")
            except Exception as e:
                log.error("derivatives_upsert_failed", error=str(e))
                return IngestResult(
                    self.SOURCE,
                    status="FAILED",
                    checksum=checksum,
                    rows_fetched=len(rows),
                    error=str(e),
                )

        dur_ms = int((self._timer() - t0) * 1000)
        log.info("derivatives_done", total=len(rows), written=written, duration_ms=dur_ms)
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
        )
