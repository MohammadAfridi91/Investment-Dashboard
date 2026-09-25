"""Strategic Desk Execution Engine (Card 2).

Evaluates high-conviction structural compounders across Nifty 500 / MidSmall 400 (non-BFSI):
- Phase 1: 17 Hard Forensic Gates (Beneish, Realization, Auditor Tier-1 & Resignation,
           CARO, CWIP/GB, Contingent Liab/NW, RPT, Pledge, Altman Z'', Piotroski,
           Sloan, CFO/EBITDA, Interest Coverage, DSCR, Governance events, Size/Liquidity,
           Promoter holding decline).
- Phase 2: Moat Scoring (25 Points) - ROIC spread, 5-yr ROIC, ROIIC & ESOP, FCF consistency, ND/EBITDA.
- Phase 3: Sector Drill Scoring (15 Points) - CCC efficiency, FAT trend, Capex reinvestment.
- Phase 4: Valuation Scoring (10 Points) - DCF implied growth vs Sector TAM, FCF yield.
- Verdicts: TIER_1 (>= 42), TIER_2 (>= 34), REJECT (< 34 or failed hard gates).
- Critical: Trade execution fields (entry, stop, targets, R:R, size) are STRICTLY None.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from core.config import Config, load_config
from core.database.client import DB
from core.models import (
    AuditorHistoryRow,
    ForensicFinancialsRow,
    GovernanceEventRow,
    SurveillanceRegistryRow,
    TradeCheckCardRow,
)


class StrategicDesk:
    """Card 2 Strategic Evaluation Engine."""

    def __init__(self, db: DB | None = None, cfg: Config | None = None) -> None:
        self.db = db
        self.cfg = cfg or load_config()

    def evaluate(
        self,
        symbol: str,
        eval_date: date,
        fin: ForensicFinancialsRow,
        auditor: AuditorHistoryRow | None = None,
        surv: SurveillanceRegistryRow | None = None,
        gov_events: list[GovernanceEventRow] | None = None,
        adtv_20d: float | None = None,
        gsec_yield: float = 0.071,
        sector_name: str | None = None,
        prior_fin: ForensicFinancialsRow | None = None,
        is_bfsi: bool = False,
    ) -> TradeCheckCardRow:
        """Evaluates Card 2 strategic criteria for a single symbol."""
        card_id = str(uuid.uuid4())
        rejection_reasons: list[str] = []

        if is_bfsi:
            rejection_reasons.append("BFSI sector prohibited for Card 2 non-BFSI strategic desk")

        # -------------------------------------------------------------
        # Phase 1: 17 Hard Forensic Gates
        # -------------------------------------------------------------

        # Gate 1: Beneish M-Score < -2.22
        g1_beneish = fin.beneish_m_score is not None and fin.beneish_m_score < -2.22
        if not g1_beneish:
            rejection_reasons.append(
                f"Beneish M-Score {fin.beneish_m_score} >= -2.22 (earnings manipulation risk)"
            )

        # Gate 2: Cash Realization (CFO/PAT >= 0.80)
        cfo_pat = fin.cfo_to_pat
        if cfo_pat is None and fin.cfo is not None and fin.net_profit and fin.net_profit > 0:
            cfo_pat = fin.cfo / fin.net_profit
        g2_realization = cfo_pat is not None and cfo_pat >= self.cfg.card2.cfo_pat_min
        if not g2_realization:
            rejection_reasons.append(f"Cash realization {cfo_pat} < {self.cfg.card2.cfo_pat_min}")

        # Gate 3: Tier-1 Auditor & No Mid-term Resignation
        is_tier1 = False
        if auditor is not None:
            if auditor.is_tier1 or any(
                t.lower() in auditor.auditor_firm.lower() for t in self.cfg.tier1_auditors
            ):
                is_tier1 = True
            auditor_no_resign = not auditor.mid_term_resignation
        else:
            is_tier1 = False
            auditor_no_resign = surv is None or not surv.has_auditor_resignation

        g3_auditor = is_tier1 and auditor_no_resign
        if not g3_auditor:
            rejection_reasons.append("Auditor is not Tier-1 or mid-term resignation occurred")

        # Gate 4: CARO Clean & Unqualified
        if auditor is not None:
            g4_caro = (not auditor.caro_qualified) and (not auditor.has_qualified_opinion)
        else:
            g4_caro = True
        if not g4_caro:
            rejection_reasons.append("Auditor report has CARO qualifications or modified opinion")

        # Gate 5: CWIP / Gross Block <= 0.30
        if fin.gross_block and fin.gross_block > 0 and fin.cwip is not None:
            cwip_ratio = fin.cwip / fin.gross_block
            g5_cwip = cwip_ratio <= self.cfg.card2.cwip_max_card2
        else:
            cwip_ratio = 0.0
            g5_cwip = True
        if not g5_cwip:
            rejection_reasons.append(
                f"CWIP/Gross Block ratio {cwip_ratio:.2f} > {self.cfg.card2.cwip_max_card2}"
            )

        # Gate 6: Contingent Liabilities / Net Worth <= 0.15
        if fin.net_worth and fin.net_worth > 0 and fin.contingent_liabilities is not None:
            obs_ratio = fin.contingent_liabilities / fin.net_worth
            g6_obs = obs_ratio <= self.cfg.card2.obs_max
        else:
            obs_ratio = 0.0
            g6_obs = True
        if not g6_obs:
            rejection_reasons.append(
                f"Contingent liabilities / NW ratio {obs_ratio:.2f} > {self.cfg.card2.obs_max}"
            )

        # Gate 7: RPT Clean
        g7_rpt = not fin.has_rpt_siphoning
        if not g7_rpt:
            rejection_reasons.append("Related Party Transaction siphoning flag detected")

        # Gate 8: Promoter Pledge <= 5% (0.05)
        pledge_val = (
            (surv.promoter_pledge_pct if surv else 0.0) / 100.0
            if surv and surv.promoter_pledge_pct > 1.0
            else (surv.promoter_pledge_pct if surv else 0.0)
        )
        g8_pledge = pledge_val <= self.cfg.card2.pledge_max_card2
        if not g8_pledge:
            rejection_reasons.append(
                f"Promoter pledge {pledge_val * 100:.1f}% > {self.cfg.card2.pledge_max_card2 * 100:.1f}%"
            )

        # Gate 9: Altman Z'' >= 2.6
        g9_altman = (
            fin.altman_z_double_prime is not None
            and fin.altman_z_double_prime >= self.cfg.card2.altman_z_min
        )
        if not g9_altman:
            rejection_reasons.append(
                f"Altman Z'' {fin.altman_z_double_prime} < {self.cfg.card2.altman_z_min}"
            )

        # Gate 10: Piotroski F-Score >= 7
        g10_piotroski = (
            fin.piotroski_f_score is not None
            and fin.piotroski_f_score >= self.cfg.card2.piotroski_f_min
        )
        if not g10_piotroski:
            rejection_reasons.append(
                f"Piotroski F-score {fin.piotroski_f_score} < {self.cfg.card2.piotroski_f_min}"
            )

        # Gate 11: Sloan Accrual <= 0.10
        g11_sloan = (
            fin.sloan_accrual is not None
            and abs(fin.sloan_accrual) <= self.cfg.card2.sloan_accrual_max
        )
        if not g11_sloan:
            rejection_reasons.append(
                f"Sloan accrual {fin.sloan_accrual} > {self.cfg.card2.sloan_accrual_max}"
            )

        # Gate 12: CFO / EBITDA >= 0.70
        cfo_ebitda = fin.cfo_to_ebitda_5y
        if cfo_ebitda is None and fin.cfo and fin.ebitda and fin.ebitda > 0:
            cfo_ebitda = fin.cfo / fin.ebitda
        g12_cfo_ebitda = cfo_ebitda is not None and cfo_ebitda >= 0.70
        if not g12_cfo_ebitda:
            rejection_reasons.append(f"CFO / EBITDA {cfo_ebitda} < 0.70")

        # Gate 13: Interest Coverage >= 4.0
        g13_ic = (
            fin.interest_coverage is not None
            and fin.interest_coverage >= self.cfg.card2.interest_coverage_min
        )
        if not g13_ic:
            rejection_reasons.append(
                f"Interest coverage {fin.interest_coverage} < {self.cfg.card2.interest_coverage_min}"
            )

        # Gate 14: DSCR >= 1.2
        g14_dscr = fin.dscr is not None and fin.dscr >= self.cfg.card2.dscr_min
        if not g14_dscr:
            rejection_reasons.append(f"DSCR {fin.dscr} < {self.cfg.card2.dscr_min}")

        # Gate 15: Governance Clean (no fatal governance events)
        fatal_event_found = False
        fatal_types = set(self.cfg.governance_fatal)
        if gov_events:
            for ev in gov_events:
                if ev.event_type in fatal_types or (ev.severity and ev.severity.upper() == "FATAL"):
                    fatal_event_found = True
                    break
        g15_gov = not fatal_event_found
        if not g15_gov:
            rejection_reasons.append("Fatal governance event detected")

        # Gate 16: Size & Liquidity (MCap >= ₹10,000 Cr & ADTV >= ₹100 Cr)
        mcap_ok = fin.market_cap is not None and fin.market_cap >= self.cfg.card2.market_cap_min_inr
        adtv_ok = adtv_20d is not None and adtv_20d >= self.cfg.card2.adtv_min_inr
        g16_size_liq = mcap_ok and adtv_ok
        if not g16_size_liq:
            rejection_reasons.append(
                f"Size/Liquidity failed (MCap: {fin.market_cap}, ADTV: {adtv_20d})"
            )

        # Gate 17: Promoter Holding Decline <= 2%
        promoter_change = surv.promoter_holding_change_4q if surv else None
        if promoter_change is not None:
            # -0.02 means 2% drop
            g17_promoter = promoter_change >= -self.cfg.card2.promoter_holding_decline_max
        else:
            g17_promoter = True
        if not g17_promoter:
            rejection_reasons.append(
                f"Promoter holding decline {promoter_change} exceeds {self.cfg.card2.promoter_holding_decline_max}"
            )

        all_gates = [
            g1_beneish,
            g2_realization,
            g3_auditor,
            g4_caro,
            g5_cwip,
            g6_obs,
            g7_rpt,
            g8_pledge,
            g9_altman,
            g10_piotroski,
            g11_sloan,
            g12_cfo_ebitda,
            g13_ic,
            g14_dscr,
            g15_gov,
            g16_size_liq,
            g17_promoter,
        ]
        hard_gates_pass = (not is_bfsi) and all(all_gates)

        # -------------------------------------------------------------
        # Phase 2: Moat (25 Points Max)
        # -------------------------------------------------------------
        # M1: ROIC - WACC spread >= 5% (5 pts)
        m1_roic_spread = False
        if fin.roce_wacc_spread is not None:
            m1_roic_spread = fin.roce_wacc_spread >= self.cfg.card2.roce_wacc_spread_min
        elif fin.roic_5y_avg is not None and fin.wacc is not None:
            m1_roic_spread = (fin.roic_5y_avg - fin.wacc) >= self.cfg.card2.roic_wacc_spread_min

        # M2: 5-year average ROIC >= 15% (5 pts)
        m2_roic_avg = False
        if fin.roic_5y_avg is not None:
            m2_roic_avg = fin.roic_5y_avg >= 0.15
        elif fin.roce_5y_avg is not None:
            m2_roic_avg = fin.roce_5y_avg >= 0.15

        # M3: ROIIC >= 20% & ESOP dilution <= 2% (5 pts)
        m3_roiic_esop = False
        if fin.roiic_5y is not None and fin.roiic_5y >= self.cfg.card2.roiic_min:
            esop_ok = (
                fin.esop_dilution_annual is None
                or fin.esop_dilution_annual <= self.cfg.card2.esop_dilution_max
            )
            m3_roiic_esop = esop_ok

        # M4: FCF positive >= 4 consecutive years (5 pts)
        m4_fcf_consist = (
            fin.fcf_years_positive is not None
            and fin.fcf_years_positive >= self.cfg.card2.fcf_positive_years_min
        )

        # M5: Gross Margin Stable & Net Debt / EBITDA <= 1.0 (5 pts)
        gm_ok = fin.gross_margin_stable
        nd_ok = (
            fin.net_debt_to_ebitda is None or fin.net_debt_to_ebitda <= self.cfg.card2.nd_ebitda_max
        )
        m5_margin_debt = gm_ok and nd_ok

        moat_score = (
            (5 if m1_roic_spread else 0)
            + (5 if m2_roic_avg else 0)
            + (5 if m3_roiic_esop else 0)
            + (5 if m4_fcf_consist else 0)
            + (5 if m5_margin_debt else 0)
        )

        # -------------------------------------------------------------
        # Phase 3: Sector Drill (15 Points Max)
        # -------------------------------------------------------------
        # S1: Cash Conversion Cycle <= 2-yr prior or <= 60 days (5 pts)
        s1_ccc = False
        if (
            prior_fin is not None
            and prior_fin.cash_conversion_cycle is not None
            and fin.cash_conversion_cycle is not None
        ):
            s1_ccc = fin.cash_conversion_cycle <= prior_fin.cash_conversion_cycle
        elif fin.cash_conversion_cycle is not None:
            s1_ccc = fin.cash_conversion_cycle <= 60.0

        # S2: Fixed Asset Turnover > 2-yr prior or >= 2.0 (5 pts)
        s2_fat = False
        if (
            prior_fin is not None
            and prior_fin.fixed_asset_turnover is not None
            and fin.fixed_asset_turnover is not None
        ):
            s2_fat = fin.fixed_asset_turnover >= prior_fin.fixed_asset_turnover
        elif fin.fixed_asset_turnover is not None:
            s2_fat = fin.fixed_asset_turnover >= 2.0

        # S3: Capacity Reinvestment / Capex to Depreciation > 1.0 (5 pts)
        s3_capex = False
        if fin.capex_to_depreciation is not None:
            s3_capex = fin.capex_to_depreciation >= 1.0
        else:
            s3_capex = fin.capacity_utilization_pass

        sector_score = (5 if s1_ccc else 0) + (5 if s2_fat else 0) + (5 if s3_capex else 0)

        # -------------------------------------------------------------
        # Phase 4: Valuation (10 Points Max)
        # -------------------------------------------------------------
        sec_name = sector_name or fin.sector or "Default"
        tam_growth = self.cfg.sector_tam_growth.get(
            sec_name, self.cfg.sector_tam_growth.get("Default", 0.14)
        )

        # V1: DCF Implied Growth <= Sector TAM (5 pts)
        v1_dcf_growth = fin.implied_dcf_growth is not None and fin.implied_dcf_growth <= tam_growth

        # V2: FCF Yield >= G-Sec - 3.5% (5 pts)
        fcf_yield_threshold = gsec_yield - 0.035
        v2_fcf_yield = fin.fcf_yield is not None and fin.fcf_yield >= fcf_yield_threshold

        valuation_score = (5 if v1_dcf_growth else 0) + (5 if v2_fcf_yield else 0)

        total_score = float(moat_score + sector_score + valuation_score)
        max_score = 50.0

        # Verdict
        if not hard_gates_pass:
            verdict = "REJECT"
        elif total_score >= self.cfg.card2.tier1_min:
            verdict = "TIER_1"
        elif total_score >= self.cfg.card2.tier2_min:
            verdict = "TIER_2"
        else:
            verdict = "REJECT"

        card_details: dict[str, Any] = {
            "hard_forensic_gates": {
                "g1_beneish_m_score": g1_beneish,
                "g2_cash_realization": g2_realization,
                "g3_tier1_auditor": g3_auditor,
                "g4_caro_unqualified": g4_caro,
                "g5_cwip_gross_block": g5_cwip,
                "g6_obs_net_worth": g6_obs,
                "g7_rpt_clean": g7_rpt,
                "g8_promoter_pledge": g8_pledge,
                "g9_altman_z_double_prime": g9_altman,
                "g10_piotroski_f_score": g10_piotroski,
                "g11_sloan_accrual": g11_sloan,
                "g12_cfo_to_ebitda": g12_cfo_ebitda,
                "g13_interest_coverage": g13_ic,
                "g14_dscr": g14_dscr,
                "g15_governance_clean": g15_gov,
                "g16_size_and_liquidity": g16_size_liq,
                "g17_promoter_holding_decline": g17_promoter,
            },
            "phase2_moat": {
                "m1_roic_spread": m1_roic_spread,
                "m2_roic_avg": m2_roic_avg,
                "m3_roiic_esop": m3_roiic_esop,
                "m4_fcf_consistency": m4_fcf_consist,
                "m5_margin_debt": m5_margin_debt,
                "subtotal": moat_score,
            },
            "phase3_sector": {
                "s1_cash_conversion_cycle": s1_ccc,
                "s2_fixed_asset_turnover": s2_fat,
                "s3_capacity_reinvestment": s3_capex,
                "subtotal": sector_score,
            },
            "phase4_valuation": {
                "v1_dcf_growth_vs_tam": v1_dcf_growth,
                "tam_growth_reference": tam_growth,
                "v2_fcf_yield_vs_gsec": v2_fcf_yield,
                "gsec_yield_reference": gsec_yield,
                "subtotal": valuation_score,
            },
            "rejection_reasons": rejection_reasons,
        }

        # CRITICAL ACCEPTANCE CRITERIA: Card 2 trade execution fields MUST BE NULL
        return TradeCheckCardRow(
            id=card_id,
            symbol=symbol,
            desk_type="STRATEGIC",
            eval_date=eval_date,
            hard_gates_pass=hard_gates_pass,
            score=total_score,
            max_score=max_score,
            verdict=verdict,
            entry_trigger=None,
            stop_loss=None,
            target_1=None,
            target_2=None,
            risk_reward_ratio=None,
            position_size_shares=None,
            valid_until=None,
            card_details=card_details,
            sebi_disclosure_snapshot=None,
            restatement_caution=fin.restatement_flag,
        )

    def evaluate_from_db(self, symbol: str, eval_date: date) -> TradeCheckCardRow | None:
        """Fetches data from database and evaluates Card 2 for a symbol."""
        if not self.db:
            raise RuntimeError("Database client not configured in StrategicDesk")

        # 1. Check universe
        u_rows = self.db.select("universe", filters={"symbol": symbol}, limit=1)
        if not u_rows:
            return None
        u = u_rows[0]
        is_bfsi = bool(u.get("is_bfsi", False))
        sector_name = u.get("sector")

        # 2. Latest forensic financials
        fin_rows = self.db.select(
            "forensic_financials",
            filters={"symbol": symbol},
            order="fiscal_year",
            limit=5,
        )
        if not fin_rows:
            return None
        fin_rows.sort(key=lambda r: int(r.get("fiscal_year") or 0), reverse=True)
        fin = ForensicFinancialsRow.model_validate(fin_rows[0])
        prior_fin = ForensicFinancialsRow.model_validate(fin_rows[1]) if len(fin_rows) > 1 else None

        # 3. Auditor history
        auditor: AuditorHistoryRow | None = None
        a_rows = self.db.select(
            "auditor_history",
            filters={"symbol": symbol},
            order="fiscal_year",
            limit=5,
        )
        if a_rows:
            a_rows.sort(key=lambda r: int(r.get("fiscal_year") or 0), reverse=True)
            auditor = AuditorHistoryRow.model_validate(a_rows[0])

        # 4. Surveillance
        surv: SurveillanceRegistryRow | None = None
        s_rows = self.db.select(
            "surveillance_registry",
            filters={"symbol": symbol, "record_date": eval_date.isoformat()},
            limit=1,
        )
        if s_rows:
            surv = SurveillanceRegistryRow.model_validate(s_rows[0])

        # 5. Governance events
        gov_events: list[GovernanceEventRow] = []
        g_rows = self.db.select("governance_events", filters={"symbol": symbol})
        if g_rows:
            gov_events = [GovernanceEventRow.model_validate(r) for r in g_rows]

        # 6. ADTV from technical indicators or daily prices
        adtv_20d: float | None = None
        t_rows = self.db.select(
            "technical_indicators",
            filters={"symbol": symbol, "trade_date": eval_date.isoformat()},
            limit=1,
        )
        if t_rows and t_rows[0].get("adtv_20d") is not None:
            adtv_20d = float(t_rows[0]["adtv_20d"])
        else:
            p_rows = self.db.select(
                "daily_prices",
                filters={"symbol": symbol, "trade_date": eval_date.isoformat()},
                limit=1,
            )
            if p_rows:
                adtv_20d = float(p_rows[0].get("traded_value", 0.0))

        # 7. G-Sec yield from market_regime
        gsec_yield = 0.071
        r_rows = self.db.select(
            "market_regime",
            filters={"trade_date": eval_date.isoformat()},
            limit=1,
        )
        if r_rows and r_rows[0].get("gsec_10y_yield") is not None:
            gsec_yield = float(r_rows[0]["gsec_10y_yield"]) / 100.0

        return self.evaluate(
            symbol=symbol,
            eval_date=eval_date,
            fin=fin,
            auditor=auditor,
            surv=surv,
            gov_events=gov_events,
            adtv_20d=adtv_20d,
            gsec_yield=gsec_yield,
            sector_name=sector_name,
            prior_fin=prior_fin,
            is_bfsi=is_bfsi,
        )
