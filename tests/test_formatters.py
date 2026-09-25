"""Tests for Card 1, Card 2, and Market Regime formatters."""

from __future__ import annotations

from datetime import date

from core.alerts.formatters import (
    format_card1_ascii,
    format_card1_markdown,
    format_card2_ascii,
    format_card2_markdown,
    format_regime_markdown,
)
from core.models import MarketRegimeRow, TradeCheckCardRow


def test_format_card1_markdown_execute() -> None:
    card = TradeCheckCardRow(
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
        card_details={
            "gates": {"surveillance": True, "fno_mwpl": True, "liquidity": True},
            "derivatives_score": {"total": 4, "oi_buildup": True},
            "technicals_score": {"total": 5, "avwap_support": True},
            "active_confirmations": ["RS_RISING", "DELIVERY_SPIKE"],
        },
    )

    md = format_card1_markdown(card)
    assert "TATASTEEL" in md
    assert "EXECUTE" in md
    assert "₹155.00" in md
    assert "₹147.00" in md
    assert "2.87R" in md
    assert "RS_RISING" in md
    assert "SEBI RA Regulation" in md


def test_format_card1_markdown_abort() -> None:
    card = TradeCheckCardRow(
        symbol="XYZ",
        desk_type="TACTICAL",
        eval_date=date(2026, 9, 25),
        hard_gates_pass=False,
        score=2.0,
        max_score=10.0,
        verdict="ABORT",
        card_details={"fail_reason": "HARD_GATE_VIOLATION"},
    )

    md = format_card1_markdown(card)
    assert "XYZ" in md
    assert "ABORT" in md
    assert "Execution blocked or aborted" in md


def test_format_card1_ascii() -> None:
    card = TradeCheckCardRow(
        symbol="INFY",
        desk_type="TACTICAL",
        eval_date=date(2026, 9, 25),
        hard_gates_pass=True,
        score=8.5,
        max_score=10.0,
        verdict="EXECUTE",
        entry_trigger=1800.0,
        stop_loss=1750.0,
        target_1=1900.0,
        target_2=2000.0,
        risk_reward_ratio=3.0,
        position_size_shares=100,
        valid_until=date(2026, 9, 26),
    )

    ascii_card = format_card1_ascii(card)
    assert "┌───" in ascii_card
    assert "INFY" in ascii_card
    assert "EXECUTE" in ascii_card
    assert "₹1800.00" in ascii_card
    assert "└───" in ascii_card


def test_format_card2_markdown_tier1() -> None:
    card = TradeCheckCardRow(
        symbol="TCS",
        desk_type="STRATEGIC",
        eval_date=date(2026, 9, 25),
        hard_gates_pass=True,
        score=45.0,
        max_score=50.0,
        verdict="TIER_1",
        card_details={
            "forensic_gates": {"beneish_m_score": True, "altman_z": True},
            "moat_score": {"total": 25},
            "sector_score": {"total": 10},
            "valuation_score": {"total": 10},
        },
    )

    md = format_card2_markdown(card)
    assert "TCS" in md
    assert "TIER 1 (ELITE)" in md
    assert "45.0/50.0" in md
    assert "Execution fields are strictly NULL" in md
    assert "SEBI RA Regulation" in md


def test_format_card2_ascii() -> None:
    card = TradeCheckCardRow(
        symbol="HINDUNILVR",
        desk_type="STRATEGIC",
        eval_date=date(2026, 9, 25),
        hard_gates_pass=True,
        score=38.0,
        max_score=50.0,
        verdict="TIER_2",
        card_details={
            "moat_score": {"total": 20},
            "sector_score": {"total": 10},
            "valuation_score": {"total": 8},
        },
    )

    ascii_card = format_card2_ascii(card)
    assert "HINDUNILVR" in ascii_card
    assert "TIER_2" in ascii_card
    assert "38.0/50.0" in ascii_card


def test_format_regime_markdown() -> None:
    regime = MarketRegimeRow(
        trade_date=date(2026, 9, 25),
        india_vix=12.5,
        nifty_500_close=22500.0,
        fii_cash_net_cr=1500.0,
        dii_cash_net_cr=2200.0,
        gsec_10y_yield=0.0705,
        regime_classification="RISK_ON",
    )

    md = format_regime_markdown(regime)
    assert "2026-09-25" in md
    assert "RISK_ON" in md
    assert "12.50" in md
    assert "22,500.0" in md
    assert "7.05%" in md
