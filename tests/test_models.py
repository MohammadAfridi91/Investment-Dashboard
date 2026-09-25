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
    r = DerivativeMetricsRow(
        symbol="INFY", trade_date=date.today(), fno_oi=10000, fno_oi_change=500
    )
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


def test_corporate_event_row() -> None:
    from core.models import CorporateEventRow, CorporateEventsRow

    r = CorporateEventRow(
        symbol="TCS",
        event_date=date.today(),
        event_type="AGM",
        purpose="Annual General Meeting",
        is_sebi_regulatory=False,
        source="bse_api",
    )
    assert r.symbol == "TCS"
    assert r.event_type == "AGM"
    assert r.purpose == "Annual General Meeting"
    assert r.is_sebi_regulatory is False
    assert r.source == "bse_api"

    # Parity alias check
    r2 = CorporateEventsRow(
        symbol="INFY",
        event_date=date.today(),
        event_type="EARNINGS",
    )
    assert r2.symbol == "INFY"
    assert r2.is_sebi_regulatory is False


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


def test_technical_indicators_row() -> None:
    from core.models import TechnicalIndicatorsRow

    r = TechnicalIndicatorsRow(
        symbol="TCS",
        trade_date=date.today(),
        ema_20=3850.5,
        ema_50=3800.0,
        sma_200=3600.0,
        atr_14=45.2,
        atr_compression=True,
        mansfield_rs_500=4.5,
        avwap_swing_low=3780.0,
        vpvr_hvn=3820.0,
        is_vpvr_breakout=True,
        fractal_swing_low_20d=3750.0,
        vpvr_hvn_levels=[3800.0, 3820.0, 3850.0],
    )
    assert r.symbol == "TCS"
    assert r.ema_20 == 3850.5
    assert r.atr_compression is True
    assert r.is_vpvr_breakout is True
    assert len(r.vpvr_hvn_levels or []) == 3


def test_trade_check_card_row() -> None:
    from core.models import TradeCheckCardRow

    r = TradeCheckCardRow(
        symbol="TATASTEEL",
        desk_type="TACTICAL",
        eval_date=date(2026, 9, 25),
        hard_gates_pass=True,
        score=9.0,
        max_score=10.0,
        verdict="EXECUTE",
        entry_trigger=155.0,
        stop_loss=147.0,
        target_1=165.0,
        target_2=178.0,
        risk_reward_ratio=2.87,
        position_size_shares=600,
        valid_until=date(2026, 9, 26),
    )
    assert r.symbol == "TATASTEEL"
    assert r.desk_type == "TACTICAL"
    assert r.verdict == "EXECUTE"
    assert r.entry_trigger == 155.0


def test_sebi_compliance_log_row() -> None:
    from core.models import SebiComplianceLogRow

    r = SebiComplianceLogRow(
        event_type="RESEARCH_REPORT",
        symbol="TATASTEEL",
        actor="system",
        payload={"report": "test"},
        retention_until=date(2031, 9, 25),
        checksum="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
    )
    assert r.event_type == "RESEARCH_REPORT"
    assert r.symbol == "TATASTEEL"
    assert len(r.checksum) == 64
