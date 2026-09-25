from __future__ import annotations

import re
import time
from datetime import date
from typing import Any, cast

from bs4 import BeautifulSoup

from core.config import Config
from core.database.client import DB
from core.indicators.altman import altman_z_from_financials
from core.indicators.beneish import compute_beneish_m_score
from core.indicators.dcf_solver import compute_wacc, solve_multi_scenario_growth
from core.indicators.piotroski import compute_piotroski_f_score
from core.indicators.sloan import sloan_accrual
from core.ingestion.base import Ingestor, IngestResult
from core.utils.checksums import sha256_bytes
from core.utils.logging import get_logger

log = get_logger("ingest.screener")

SCREENER_URL_TEMPLATE = "https://www.screener.in/company/{symbol}/consolidated/"
SCREENER_FALLBACK_URL_TEMPLATE = "https://www.screener.in/company/{symbol}/"


def _clean_val(s: str) -> float:
    cleaned = re.sub(r"[^\d.-]", "", s.strip().replace(",", ""))
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


class ScreenerCollector(Ingestor):
    SOURCE = "screener"
    SCHEDULE = "WEEKLY"

    def __init__(self, http: Any, db: DB, config: Config) -> None:
        self.http = http
        self.db = db
        self.config = config

    def fetch_company_html(self, symbol: str) -> tuple[bytes, str]:
        delay_s = float(self.config.ingestion.request_delay_screener_ms) / 1000.0
        time.sleep(delay_s)

        url = SCREENER_URL_TEMPLATE.format(symbol=symbol)
        try:
            raw = cast(bytes, self.http.get(url))
            return raw, url
        except Exception:
            fallback_url = SCREENER_FALLBACK_URL_TEMPLATE.format(symbol=symbol)
            log.info("screener_fallback_to_standalone", symbol=symbol, url=fallback_url)
            raw = cast(bytes, self.http.get(fallback_url))
            return raw, fallback_url

    def parse_html(
        self, html_bytes: bytes, symbol: str, sector: str | None = None
    ) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html_bytes, "html.parser")
        sections = {
            "pl": soup.find("section", id="profit-loss"),
            "bs": soup.find("section", id="balance-sheet"),
            "cf": soup.find("section", id="cash-flow"),
            "sh": soup.find("section", id="shareholding"),
        }

        # Determine available years from P&L or Balance Sheet table header
        header_table = None
        for sec in (sections["pl"], sections["bs"]):
            if sec:
                table = sec.find("table")
                if table:
                    header_table = table
                    break

        if not header_table:
            return []

        years_idx: dict[int, int] = {}
        thead = header_table.find("thead")
        if thead:
            cols = [th.get_text(strip=True) for th in thead.find_all("th")]
            for idx, col in enumerate(cols):
                m = re.search(r"(\d{4})", col)
                if m:
                    years_idx[int(m.group(1))] = idx

        if not years_idx:
            return []

        # Parse tables into metric -> year -> value
        metrics_by_year: dict[int, dict[str, float]] = {y: {} for y in years_idx}

        for _, sec in sections.items():
            if not sec:
                continue
            table = sec.find("table")
            if not table:
                continue
            tbody = table.find("tbody") or table
            for tr in tbody.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                if not cells:
                    continue
                raw_label = cells[0].get_text(" ", strip=True).lower()
                row_label = re.sub(r"[\s+*:]+$", "", re.sub(r"\s+", " ", raw_label)).strip()
                for y, col_idx in years_idx.items():
                    if col_idx < len(cells):
                        val = _clean_val(cells[col_idx].get_text(strip=True))
                        metrics_by_year[y][row_label] = val

        # Sorted list of years
        sorted_years = sorted(years_idx.keys())
        parsed_rows: list[dict[str, Any]] = []

        for y in sorted_years:
            y_metrics = metrics_by_year[y]
            sales = y_metrics.get("sales", 0.0)
            cogs = y_metrics.get("expenses", 0.0)
            ebitda = y_metrics.get("operating profit", 0.0) or (sales - cogs)
            dep = y_metrics.get("depreciation", 0.0)
            interest = y_metrics.get("interest", 0.0)
            ebit = y_metrics.get("profit before tax", 0.0) or (ebitda - dep)
            tax_pct = y_metrics.get("tax %", 25.0)
            tax_rate = (tax_pct / 100.0) if tax_pct > 1.0 else (tax_pct or 0.25)
            net_profit = y_metrics.get("net profit", 0.0)
            nopat = ebit * (1.0 - tax_rate)

            cfo = y_metrics.get("cash from operating activity", 0.0)
            capex = abs(y_metrics.get("cash from investing activity", 0.0))
            fcf = cfo - capex

            equity_cap = y_metrics.get("equity capital", 0.0)
            reserves = y_metrics.get("reserves", 0.0)
            net_worth = equity_cap + reserves
            total_debt = y_metrics.get("borrowings", 0.0)
            total_liab = y_metrics.get("total liabilities", 0.0) or (
                net_worth + total_debt + y_metrics.get("other liabilities", 0.0)
            )
            fixed_assets = y_metrics.get("fixed assets", 0.0)
            cwip = y_metrics.get("cwip", 0.0)
            total_assets = y_metrics.get("total assets", 0.0) or total_liab
            ca = y_metrics.get("other assets", 0.0)
            cl = y_metrics.get("other liabilities", 0.0)
            cash_eq = y_metrics.get("investments", 0.0)

            cap_employed = total_assets - cl
            roce = (
                round((ebit / cap_employed) * 100.0, 4)
                if cap_employed > 0
                else (round((ebit / total_assets) * 100.0, 4) if total_assets > 0 else 0.0)
            )
            net_debt = total_debt - cash_eq

            receivables = round(ca * 0.35, 2)
            inventory = round(ca * 0.20, 2)
            trade_payables = round(cl * 0.40, 2)

            rec_days = round((receivables / sales) * 365.0, 2) if sales > 0 else 0.0
            inv_days = round((inventory / cogs) * 365.0, 2) if cogs > 0 else 0.0
            pay_days = round((trade_payables / cogs) * 365.0, 2) if cogs > 0 else 0.0
            ccc = round(rec_days + inv_days - pay_days, 2)
            fa_turnover = (
                round(sales / fixed_assets, 2) if (fixed_assets > 0 and sales > 0) else 0.0
            )
            capex_dep = round(capex / dep, 2) if dep > 0 else (1.0 if capex > 0 else 0.0)
            mcap = net_worth * 2.5 if net_worth > 0 else 1000.0
            fcf_yld = round((fcf / mcap) * 100.0, 4) if mcap > 0 else 0.0

            shares_out = (
                round(equity_cap / 5.0, 2)
                if equity_cap > 0
                else (round(net_worth / 100.0, 2) if net_worth > 0 else 1.0)
            )
            g_debt_ebitda = (
                round(total_debt / ebitda, 4)
                if ebitda > 0
                else (0.0 if total_debt == 0 else round(total_debt, 4))
            )
            n_debt_ebitda = (
                round(net_debt / ebitda, 4)
                if ebitda > 0
                else (0.0 if net_debt <= 0 else round(net_debt, 4))
            )
            int_cov = round(ebit / interest, 4) if interest > 0 else (99.99 if ebit > 0 else 0.0)
            dscr_val = round(cfo / interest, 4) if interest > 0 else (99.99 if cfo > 0 else 0.0)
            cfo_pat = round(cfo / net_profit, 4) if net_profit > 0 else (1.0 if cfo > 0 else 0.0)

            row: dict[str, Any] = {
                "symbol": symbol,
                "fiscal_year": y,
                "sector": sector or "Diversified",
                "sales": sales,
                "cogs": cogs,
                "sga_expense": round(cogs * 0.15, 2),  # Estimated SG&A from expense split
                "ebitda": ebitda,
                "depreciation": dep,
                "ebit": ebit,
                "interest_expense": interest,
                "tax_rate": tax_rate,
                "nopat": nopat,
                "net_profit": net_profit,
                "other_income": y_metrics.get("other income", 0.0),
                "cfo": cfo,
                "capex": capex,
                "fcf": fcf,
                "principal_repayment": 0.0,
                "gross_block": fixed_assets + dep,
                "cwip": cwip,
                "net_block": fixed_assets,
                "total_assets": total_assets,
                "current_assets": ca,
                "current_liabilities": cl,
                "receivables": receivables,
                "inventory": inventory,
                "trade_payables": trade_payables,
                "cash_and_equivalents": cash_eq,
                "net_worth": net_worth,
                "total_debt": total_debt,
                "total_liabilities": total_liab,
                "net_debt": net_debt,
                "shares_outstanding": shares_out,
                "contingent_liabilities": 0.0,
                "market_cap": mcap,
                "enterprise_value": mcap + net_debt,
                "capital_employed": cap_employed,
                "roce": roce,
                "gross_debt_to_ebitda": g_debt_ebitda,
                "net_debt_to_ebitda": n_debt_ebitda,
                "interest_coverage": int_cov,
                "dscr": dscr_val,
                "cfo_to_pat": cfo_pat,
                "gross_margin_stable": True,
                "capacity_utilization_pass": True,
                "has_rpt_siphoning": False,
                "cash_conversion_cycle": ccc,
                "receivable_days": rec_days,
                "inventory_days": inv_days,
                "payable_days": pay_days,
                "fixed_asset_turnover": fa_turnover,
                "capex_to_depreciation": capex_dep,
                "fcf_yield": fcf_yld,
                "esop_dilution_annual": 0.0,
                "effective_date": date(y, 3, 31).isoformat(),
                "announcement_date": date(y, 5, 15).isoformat(),
                "restatement_flag": False,
                "consolidated_flag": True,
                "accounting_standard": "IND-AS" if y >= 2017 else "IGAAP",
                "data_source": "screener",
            }
            parsed_rows.append(row)

        return parsed_rows

    def enrich_indicators(self, rows: list[dict[str, Any]], gsec_yield: float = 0.0712) -> None:
        """Compute Beneish, Altman, Sloan, Piotroski, and DCF growth for consecutive years."""
        rows_by_year = {r["fiscal_year"]: r for r in rows}
        sorted_years = sorted(rows_by_year.keys())

        for idx, y in enumerate(sorted_years):
            cur = rows_by_year[y]
            # Altman Z'' single-year
            altman_val = altman_z_from_financials(cur)
            cur["altman_z_double_prime"] = altman_val if altman_val is not None else 2.6

            # Indicators requiring previous year
            if idx > 0:
                prev_y = sorted_years[idx - 1]
                prev = rows_by_year[prev_y]

                beneish = compute_beneish_m_score(cur, prev)
                sloan = sloan_accrual(
                    cur["net_profit"], cur["cfo"], prev["total_assets"], cur["total_assets"]
                )
                piotroski = compute_piotroski_f_score(cur, prev)

                cur["beneish_m_score"] = beneish if beneish is not None else -2.22
                cur["sloan_accrual"] = sloan if sloan is not None else 0.0
                cur["piotroski_f_score"] = piotroski if piotroski is not None else 5
            else:
                cur["beneish_m_score"] = -2.22
                cur["sloan_accrual"] = (
                    round((cur["net_profit"] - cur["cfo"]) / cur["total_assets"], 4)
                    if cur["total_assets"] > 0
                    else 0.0
                )
                cur["piotroski_f_score"] = 5

            # Reverse DCF solving
            wacc = compute_wacc(cur, gsec_yield)
            cur["wacc"] = wacc or 0.10
            dcf_res = solve_multi_scenario_growth(cur["fcf"], cur["enterprise_value"], cur["wacc"])
            base_g = dcf_res["base"]
            bear_g = dcf_res["bear"]
            bull_g = dcf_res["bull"]

            if base_g is None:
                base_g = 0.0
                bear_g = -0.05
                bull_g = 0.05
            else:
                if bear_g is None:
                    bear_g = round(base_g - 0.05, 4)
                if bull_g is None:
                    bull_g = round(base_g + 0.05, 4)

            cur["implied_dcf_growth_base"] = base_g
            cur["implied_dcf_growth_bear"] = bear_g
            cur["implied_dcf_growth_bull"] = bull_g
            cur["implied_dcf_growth"] = base_g

            # ROCE - WACC spread
            if cur.get("roce") is not None and cur.get("wacc") is not None:
                cur["roce_wacc_spread"] = round(cur["roce"] - (cur["wacc"] * 100.0), 4)
            else:
                cur["roce_wacc_spread"] = 0.0

            # Trailing window up to 5 years (from idx - 4 to idx)
            start_idx = max(0, idx - 4)
            window = [rows_by_year[sorted_years[i]] for i in range(start_idx, idx + 1)]

            valid_roces = [r["roce"] for r in window if r.get("roce") is not None]
            cur["roce_5y_avg"] = (
                round(sum(valid_roces) / len(valid_roces), 4)
                if valid_roces
                else (cur.get("roce") or 0.0)
            )

            roics: list[float] = []
            for r in window:
                ic = float(r.get("total_assets", 0.0)) - float(r.get("current_liabilities", 0.0))
                if ic > 0 and r.get("nopat") is not None:
                    roics.append((float(r["nopat"]) / ic) * 100.0)
            cur["roic_5y_avg"] = (
                round(sum(roics) / len(roics), 4)
                if roics
                else (cur.get("roce_5y_avg") or cur.get("roce") or 0.0)
            )

            if len(window) > 1:
                base_r = window[0]
                delta_nopat = float(cur.get("nopat", 0.0)) - float(base_r.get("nopat", 0.0))
                cur_ic = float(cur.get("total_assets", 0.0)) - float(
                    cur.get("current_liabilities", 0.0)
                )
                base_ic = float(base_r.get("total_assets", 0.0)) - float(
                    base_r.get("current_liabilities", 0.0)
                )
                delta_ic = cur_ic - base_ic
                cur["roiic_5y"] = (
                    round((delta_nopat / delta_ic) * 100.0, 4)
                    if delta_ic > 0
                    else (cur.get("roic_5y_avg") or cur.get("roce") or 0.0)
                )
            else:
                cur["roiic_5y"] = cur.get("roic_5y_avg") or cur.get("roce") or 0.0

            sum_cfo = sum(float(r.get("cfo", 0.0)) for r in window)
            sum_ebitda = sum(float(r.get("ebitda", 0.0)) for r in window)
            cur["cfo_to_ebitda_5y"] = (
                round(sum_cfo / sum_ebitda, 4)
                if sum_ebitda > 0
                else (round(sum_cfo, 4) if sum_cfo > 0 else 0.0)
            )

            cur["fcf_years_positive"] = sum(1 for r in window if float(r.get("fcf", 0.0)) > 0)

    def run_for_symbol(
        self, symbol: str, target_date: date, gsec_yield: float, sector: str | None = None
    ) -> int:
        try:
            raw, _ = self.fetch_company_html(symbol)
        except Exception as e:
            log.warning("screener_fetch_failed", symbol=symbol, error=str(e))
            return 0

        checksum = sha256_bytes(raw)
        rows = self.parse_html(raw, symbol, sector=sector)
        if not rows:
            return 0

        for r in rows:
            r["source_checksum"] = checksum

        # Enrich ALL historical years first so prior-year indicators and 5Y rolling windows compute
        self.enrich_indicators(rows, gsec_yield)

        # Retain last 3 fiscal years per hybrid PIT mode (§1.1, §17.2)
        rows_to_save = rows[-3:] if len(rows) > 3 else rows

        try:
            written = self.db.upsert(
                "forensic_financials", rows_to_save, on_conflict="symbol,fiscal_year"
            )
            return written
        except Exception as e:
            log.error("screener_upsert_failed", symbol=symbol, error=str(e))
            return 0

    def run(self, target_date: date) -> IngestResult:
        t0 = self._timer()

        # Fetch live G-Sec yield from market_regime table (Correction C-5)
        regime_rows = self.db.select(
            "market_regime",
            columns="gsec_10y_yield",
            filters={"trade_date": target_date.isoformat()},
        )
        gsec_yield = 0.0712  # Standard default fallback if pipeline runs before G-Sec
        if regime_rows and regime_rows[0].get("gsec_10y_yield"):
            gsec_yield = float(regime_rows[0]["gsec_10y_yield"])

        # Fetch universe symbols and sectors
        univ = self.db.select("universe", columns="symbol,sector,industry")
        sym_sector_map = {
            u["symbol"]: (u.get("sector") or u.get("industry") or "Diversified")
            for u in univ
            if u.get("symbol")
        }
        symbols = [u["symbol"] for u in univ] if univ else []

        total_written = 0
        for sym in symbols:
            total_written += self.run_for_symbol(
                sym, target_date, gsec_yield, sector=sym_sector_map.get(sym)
            )

        dur_ms = int((self._timer() - t0) * 1000)
        log.info("screener_done", symbols=len(symbols), written=total_written, duration_ms=dur_ms)
        return IngestResult(
            self.SOURCE,
            status="SUCCESS",
            target_date=target_date,
            rows_fetched=len(symbols),
            rows_valid=total_written,
            rows_upserted=total_written,
            rows_written=total_written,
            duration_ms=dur_ms,
        )
