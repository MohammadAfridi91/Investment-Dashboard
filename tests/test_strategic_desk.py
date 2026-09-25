"""Tests for Strategic Desk (Card 2) Execution Engine.

Validates Acceptance Test 10 and full suite of Card 2 rules:
- Test 10: 10 large-caps processed through Strategic Desk.
- Test 10 Critical Verification: All trade execution fields (entry, stop, targets, R:R, size)
  MUST BE STRICTLY NULL / None for Card 2.
- 17 Hard Forensic Gates verification.
- Moat, Sector Drill, and Valuation scoring phases.
- Verdict assignments: TIER_1 (>= 42), TIER_2 (>= 34), REJECT.
"""

from datetime import date

import pytest

from core.config import load_config
from core.engines.strategic_desk import StrategicDesk
from core.models import (
    AuditorHistoryRow,
    ForensicFinancialsRow,
    GovernanceEventRow,
    SurveillanceRegistryRow,
)


@pytest.fixture
def perfect_fin() -> ForensicFinancialsRow:
    return ForensicFinancialsRow(
        symbol="TCS",
        fiscal_year=2024,
        sector="IT Services",
        sales=240000.0,
        ebitda=65000.0,
        net_profit=45000.0,
        cfo=42000.0,  # CFO/PAT = 42/45 = 0.933 >= 0.80
        capex=4000.0,
        fcf=38000.0,
        gross_block=30000.0,
        cwip=1500.0,  # 1500/30000 = 0.05 <= 0.30
        net_worth=100000.0,
        contingent_liabilities=5000.0,  # 5000/100000 = 0.05 <= 0.15
        total_debt=0.0,
        net_debt=-30000.0,
        market_cap=1400000000000.0,  # 14 Lakh Cr >> 10,000 Cr
        roce=0.55,
        roce_5y_avg=0.50,
        roce_wacc_spread=0.40,  # >> 0.05
        roic_5y_avg=0.48,
        roiic_5y=0.45,  # >= 0.20
        wacc=0.10,
        net_debt_to_ebitda=-0.46,  # <= 1.0
        interest_coverage=50.0,  # >= 4.0
        dscr=10.0,  # >= 1.2
        beneish_m_score=-2.85,  # < -2.22
        altman_z_double_prime=12.5,  # >= 2.6
        piotroski_f_score=9,  # >= 7
        sloan_accrual=0.02,  # <= 0.10
        cfo_to_ebitda_5y=0.88,  # >= 0.70
        cfo_to_pat=0.933,
        fcf_years_positive=5,  # >= 4
        gross_margin_stable=True,
        cash_conversion_cycle=45.0,  # <= 60
        fixed_asset_turnover=8.0,  # >= 2.0
        capex_to_depreciation=1.2,  # >= 1.0
        capacity_utilization_pass=True,
        implied_dcf_growth=0.08,  # <= IT TAM 0.12
        fcf_yield=0.045,  # 4.5% >= 7.1% - 3.5% = 3.6%
        has_rpt_siphoning=False,
        esop_dilution_annual=0.005,  # <= 0.02
        restatement_flag=False,
    )


@pytest.fixture
def perfect_auditor() -> AuditorHistoryRow:
    return AuditorHistoryRow(
        symbol="TCS",
        fiscal_year=2024,
        auditor_firm="BSR & Co",  # Tier-1
        is_tier1=True,
        mid_term_resignation=False,
        has_qualified_opinion=False,
        caro_qualified=False,
    )


@pytest.fixture
def perfect_surv() -> SurveillanceRegistryRow:
    return SurveillanceRegistryRow(
        symbol="TCS",
        record_date=date(2026, 9, 25),
        promoter_pledge_pct=0.0,  # 0% <= 5%
        promoter_holding_change_4q=0.0,  # >= -0.02
    )


def test_strategic_desk_tier1_evaluation(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    card = desk.evaluate(
        symbol="TCS",
        eval_date=date(2026, 9, 25),
        fin=perfect_fin,
        auditor=perfect_auditor,
        surv=perfect_surv,
        gov_events=[],
        adtv_20d=2500000000.0,  # 250 Cr >= 100 Cr
        sector_name="IT Services",
    )
    assert card.hard_gates_pass is True
    assert card.score == 50.0  # Max score: 25 Moat + 15 Sector + 10 Valuation
    assert card.verdict == "TIER_1"
    # CRITICAL: Verify all trade execution fields are None
    assert card.entry_trigger is None
    assert card.stop_loss is None
    assert card.target_1 is None
    assert card.target_2 is None
    assert card.risk_reward_ratio is None
    assert card.position_size_shares is None
    assert card.valid_until is None


def test_acceptance_test_10_critical_trade_fields_are_null(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    """Acceptance Test 10: 10 large-caps evaluated and trade fields STRICTLY NULL."""
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    symbols = [
        "RELIANCE",
        "TCS",
        "INFY",
        "BHARTIARTL",
        "ITC",
        "LT",
        "HINDUNILVR",
        "ASIANPAINT",
        "SUNPHARMA",
        "TITAN",
    ]

    cards = []
    for sym in symbols:
        fin = perfect_fin.model_copy(update={"symbol": sym})
        aud = perfect_auditor.model_copy(update={"symbol": sym})
        surv = perfect_surv.model_copy(update={"symbol": sym})
        card = desk.evaluate(
            symbol=sym,
            eval_date=date(2026, 9, 25),
            fin=fin,
            auditor=aud,
            surv=surv,
            gov_events=[],
            adtv_20d=1500000000.0,  # 150 Cr >= 100 Cr
            sector_name="IT Services",
            is_bfsi=False,
        )
        cards.append(card)

    assert len(cards) == 10
    for card in cards:
        assert card.desk_type == "STRATEGIC"
        assert card.hard_gates_pass is True
        assert card.verdict in ("TIER_1", "TIER_2")
        # Strict verification of Section 12 & 19 constraint
        assert card.entry_trigger is None, f"{card.symbol} entry_trigger must be None"
        assert card.stop_loss is None, f"{card.symbol} stop_loss must be None"
        assert card.target_1 is None, f"{card.symbol} target_1 must be None"
        assert card.target_2 is None, f"{card.symbol} target_2 must be None"
        assert card.risk_reward_ratio is None, f"{card.symbol} risk_reward_ratio must be None"
        assert card.position_size_shares is None, f"{card.symbol} position_size_shares must be None"
        assert card.valid_until is None, f"{card.symbol} valid_until must be None"


def test_hard_gate_beneish_m_score_rejection(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    bad_fin = perfect_fin.model_copy(update={"beneish_m_score": -1.80})  # > -2.22 red flag
    card = desk.evaluate(
        symbol="TCS",
        eval_date=date(2026, 9, 25),
        fin=bad_fin,
        auditor=perfect_auditor,
        surv=perfect_surv,
        adtv_20d=2000000000.0,
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "REJECT"
    assert "Beneish M-Score" in str(card.card_details.get("rejection_reasons"))


def test_hard_gate_cash_realization_rejection(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    bad_fin = perfect_fin.model_copy(update={"cfo_to_pat": 0.65})  # < 0.80
    card = desk.evaluate(
        symbol="TCS",
        eval_date=date(2026, 9, 25),
        fin=bad_fin,
        auditor=perfect_auditor,
        surv=perfect_surv,
        adtv_20d=2000000000.0,
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "REJECT"


def test_hard_gate_auditor_resignation(
    perfect_fin: ForensicFinancialsRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    bad_auditor = AuditorHistoryRow(
        symbol="TCS",
        fiscal_year=2024,
        auditor_firm="Deloitte Haskins & Sells",
        is_tier1=True,
        mid_term_resignation=True,  # Fatal resignation
    )
    card = desk.evaluate(
        symbol="TCS",
        eval_date=date(2026, 9, 25),
        fin=perfect_fin,
        auditor=bad_auditor,
        surv=perfect_surv,
        adtv_20d=2000000000.0,
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "REJECT"


def test_hard_gate_fatal_governance_event(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    raid_event = GovernanceEventRow(
        symbol="TCS",
        event_date=date(2026, 9, 20),
        event_type="ED_RAID",
        severity="FATAL",
    )
    card = desk.evaluate(
        symbol="TCS",
        eval_date=date(2026, 9, 25),
        fin=perfect_fin,
        auditor=perfect_auditor,
        surv=perfect_surv,
        gov_events=[raid_event],
        adtv_20d=2000000000.0,
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "REJECT"


def test_card2_tier2_verdict(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    # Lower score to 35 (Tier-2 is >= 34, Tier-1 is >= 42)
    tier2_fin = perfect_fin.model_copy(
        update={
            "implied_dcf_growth": 0.20,  # Fails V1 (-5 pts)
            "fcf_yield": 0.02,  # Fails V2 (-5 pts)
            "fcf_years_positive": 2,  # Fails M4 (-5 pts)
        }
    )
    card = desk.evaluate(
        symbol="TCS",
        eval_date=date(2026, 9, 25),
        fin=tier2_fin,
        auditor=perfect_auditor,
        surv=perfect_surv,
        adtv_20d=2000000000.0,
        sector_name="IT Services",
    )
    assert card.hard_gates_pass is True
    assert card.score == 35.0
    assert card.verdict == "TIER_2"


def test_hard_gate_cwip_gross_block(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    fin = perfect_fin.model_copy(update={"cwip": 12000.0, "gross_block": 30000.0})  # 40% > 30%
    card = desk.evaluate(
        "TCS", date(2026, 9, 25), fin, perfect_auditor, perfect_surv, adtv_20d=2000000000.0
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "REJECT"


def test_hard_gate_contingent_liabilities(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    fin = perfect_fin.model_copy(
        update={"contingent_liabilities": 25000.0, "net_worth": 100000.0}
    )  # 25% > 15%
    card = desk.evaluate(
        "TCS", date(2026, 9, 25), fin, perfect_auditor, perfect_surv, adtv_20d=2000000000.0
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "REJECT"


def test_hard_gate_rpt_siphoning(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    fin = perfect_fin.model_copy(update={"has_rpt_siphoning": True})
    card = desk.evaluate(
        "TCS", date(2026, 9, 25), fin, perfect_auditor, perfect_surv, adtv_20d=2000000000.0
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "REJECT"


def test_hard_gate_promoter_pledge_high(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    surv = SurveillanceRegistryRow(
        symbol="TCS", record_date=date(2026, 9, 25), promoter_pledge_pct=10.0
    )  # 10% > 5%
    card = desk.evaluate(
        "TCS", date(2026, 9, 25), perfect_fin, perfect_auditor, surv, adtv_20d=2000000000.0
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "REJECT"


def test_hard_gate_altman_z_low(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    fin = perfect_fin.model_copy(update={"altman_z_double_prime": 2.2})  # < 2.6
    card = desk.evaluate(
        "TCS", date(2026, 9, 25), fin, perfect_auditor, perfect_surv, adtv_20d=2000000000.0
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "REJECT"


def test_hard_gate_piotroski_f_low(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    fin = perfect_fin.model_copy(update={"piotroski_f_score": 6})  # < 7
    card = desk.evaluate(
        "TCS", date(2026, 9, 25), fin, perfect_auditor, perfect_surv, adtv_20d=2000000000.0
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "REJECT"


def test_hard_gate_sloan_accrual_high(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    fin = perfect_fin.model_copy(update={"sloan_accrual": 0.15})  # > 0.10
    card = desk.evaluate(
        "TCS", date(2026, 9, 25), fin, perfect_auditor, perfect_surv, adtv_20d=2000000000.0
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "REJECT"


def test_hard_gate_interest_coverage_low(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    fin = perfect_fin.model_copy(update={"interest_coverage": 3.2})  # < 4.0
    card = desk.evaluate(
        "TCS", date(2026, 9, 25), fin, perfect_auditor, perfect_surv, adtv_20d=2000000000.0
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "REJECT"


def test_hard_gate_dscr_low(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    fin = perfect_fin.model_copy(update={"dscr": 1.05})  # < 1.2
    card = desk.evaluate(
        "TCS", date(2026, 9, 25), fin, perfect_auditor, perfect_surv, adtv_20d=2000000000.0
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "REJECT"


def test_hard_gate_size_liquidity_fail(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    # Market cap 5000 Cr < 10,000 Cr minimum
    fin = perfect_fin.model_copy(update={"market_cap": 50000000000.0})
    card = desk.evaluate(
        "SMALLCAP", date(2026, 9, 25), fin, perfect_auditor, perfect_surv, adtv_20d=2000000000.0
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "REJECT"


def test_hard_gate_promoter_holding_decline_excessive(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    surv = SurveillanceRegistryRow(
        symbol="TCS", record_date=date(2026, 9, 25), promoter_holding_change_4q=-0.05
    )  # 5% decline > 2%
    card = desk.evaluate(
        "TCS", date(2026, 9, 25), perfect_fin, perfect_auditor, surv, adtv_20d=2000000000.0
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "REJECT"


def test_hard_gate_bfsi_rejection(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    cfg = load_config()
    desk = StrategicDesk(cfg=cfg)
    card = desk.evaluate(
        "SBIN",
        date(2026, 9, 25),
        perfect_fin,
        perfect_auditor,
        perfect_surv,
        adtv_20d=2000000000.0,
        is_bfsi=True,
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "REJECT"


def test_strategic_desk_evaluate_from_db(
    perfect_fin: ForensicFinancialsRow,
    perfect_auditor: AuditorHistoryRow,
    perfect_surv: SurveillanceRegistryRow,
) -> None:
    from unittest.mock import MagicMock

    mock_db = MagicMock()
    mock_db.select.side_effect = lambda table, **kwargs: (
        [{"symbol": "TCS", "is_bfsi": False, "sector": "IT Services"}]
        if table == "universe"
        else [perfect_fin.model_dump(mode="json")]
        if table == "forensic_financials"
        else [perfect_auditor.model_dump(mode="json")]
        if table == "auditor_history"
        else [perfect_surv.model_dump(mode="json")]
        if table == "surveillance_registry"
        else [{"adtv_20d": 2500000000.0}]
        if table == "technical_indicators"
        else [{"gsec_10y_yield": 7.10}]
        if table == "market_regime"
        else []
    )
    desk = StrategicDesk(db=mock_db)
    card = desk.evaluate_from_db("TCS", date(2026, 9, 25))
    assert card is not None
    assert card.symbol == "TCS"
    assert card.verdict == "TIER_1"
    assert card.entry_trigger is None
