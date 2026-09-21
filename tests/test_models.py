from datetime import date

import pytest
from pydantic import ValidationError

from core.models import (
    CorporateActionRow,
    DailyPriceRow,
    DerivativeMetricsRow,
    InstitutionalDealRow,
    MarketRegimeRow,
    SurveillanceRegistryRow,
    UniverseRow,
)


def test_universe_row_defaults() -> None:
    r = UniverseRow(symbol="TCS", company_name="TCS Ltd", isin="INE467B01029")
    assert r.is_bfsi is False
    assert r.is_nifty500 is False


def test_daily_price_row_requires_ohlc() -> None:
    with pytest.raises(ValidationError):
        DailyPriceRow(symbol="TCS", trade_date=date.today())  # type: ignore[call-arg]


def test_market_regime_gsec_field_present() -> None:
    r = MarketRegimeRow(trade_date=date.today(), gsec_10y_yield=7.05)
    assert r.gsec_10y_yield == 7.05


def test_derivative_metrics_row() -> None:
    r = DerivativeMetricsRow(symbol="INFY", trade_date=date.today(), fno_oi=10000, fno_oi_change=500)
    assert r.symbol == "INFY"
    assert r.fno_oi == 10000
    assert r.is_fno_ban is False


def test_surveillance_registry_row() -> None:
    r = SurveillanceRegistryRow(symbol="ADANIENT", record_date=date.today(), asm_stage=2)
    assert r.asm_stage == 2
    assert r.is_t2t is False


def test_institutional_deal_row() -> None:
    r = InstitutionalDealRow(
        symbol="RELIANCE",
        deal_date=date.today(),
        deal_type="BULK",
        client_name="SBI MUTUAL FUND",
        trade_direction="BUY",
        quantity=50000,
        price=2900.0,
        is_institutional=True,
    )
    assert r.is_institutional is True
    assert r.is_wash_trade is False


def test_corporate_action_row() -> None:
    r = CorporateActionRow(
        symbol="TCS",
        ex_date=date.today(),
        action_type="BONUS",
        ratio=2.0,
        adjustment_factor=2.0,
    )
    assert r.adjustment_factor == 2.0


def test_auditor_history_row() -> None:
    from core.models import AuditorHistoryRow
    r = AuditorHistoryRow(
        symbol="INFY",
        fiscal_year=2024,
        auditor_firm="S.R. Batliboi & Co",
        is_tier1=True,
        mid_term_resignation=True,
    )
    assert r.is_tier1 is True
    assert r.mid_term_resignation is True


def test_governance_event_row() -> None:
    from core.models import GovernanceEventRow
    r = GovernanceEventRow(
        symbol="RELIANCE",
        event_date=date.today(),
        event_type="GST_RAID",
        severity="FATAL",
    )
    assert r.severity == "FATAL"


def test_forensic_financials_row() -> None:
    from core.models import ForensicFinancialsRow
    r = ForensicFinancialsRow(
        symbol="INFY",
        fiscal_year=2024,
        sales=153670.0,
        net_profit=26233.0,
        beneish_m_score=-2.45,
        altman_z_double_prime=4.2,
        piotroski_f_score=8,
    )
    assert r.sales == 153670.0
    assert r.beneish_m_score == -2.45
    assert r.piotroski_f_score == 8


