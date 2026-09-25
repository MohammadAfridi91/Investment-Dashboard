"""Tests for Tactical Desk (Card 1) Execution Engine.

Validates Acceptance Tests 9, 11, 12 and full suite of Card 1 rules:
- Test 9: 10 liquid F&O names processed through Tactical Desk.
- Test 11: RISK_OFF regime gate blocks tactical execution (threshold = 99 -> ABORT).
- Test 12: Active confirmations (>= 2 of 4 required -> ABORT if < 2).
- All 7 Hard Gates (Surveillance, MWPL, Circuit, Liquidity, Price, Earnings, Gap).
- Derivatives & Technicals scoring.
"""

from datetime import date

import pytest

from core.config import load_config
from core.engines.tactical_desk import TacticalDesk
from core.models import (
    DailyPriceRow,
    DerivativeMetricsRow,
    MarketRegimeRow,
    SurveillanceRegistryRow,
    TechnicalIndicatorsRow,
)


@pytest.fixture
def base_price() -> DailyPriceRow:
    return DailyPriceRow(
        symbol="TATASTEEL",
        trade_date=date(2026, 9, 25),
        open_price=150.0,
        high_price=155.0,
        low_price=148.0,
        close_price=154.0,
        prev_close=149.0,
        adjusted_close=154.0,
        bhavcopy_avg_price=152.0,
        session_avg_price=152.5,
        volume=20000000,
        delivery_qty=10000000,
        delivery_pct=50.0,
        delivery_value=1540000000.0,
        delivery_percentile_20d=85.0,
        delivery_trend_5d=1.2,
        traded_value=3080000000.0,  # ~308 Cr >> 15 Cr
        circuit_band=20.0,
        high_52w=180.0,
        low_52w=110.0,
    )


@pytest.fixture
def base_deriv() -> DerivativeMetricsRow:
    return DerivativeMetricsRow(
        symbol="TATASTEEL",
        trade_date=date(2026, 9, 25),
        fno_oi=50000000,
        fno_oi_change=3000000,
        prev_fno_oi=45000000,  # +11.1% buildup >= 5%
        cost_of_carry=0.08,
        prev_cost_of_carry=0.06,  # positive & rising
        pcr=0.95,
        prev_pcr=0.90,  # in [0.60, 1.25] and rising
        mwpl_pct=45.0,  # < 82%
        is_fno_ban=False,
        has_institutional_net_buy=True,
        rollover_pct=75.0,
        avg_rollover_pct_20d=65.0,  # confirmation 1
        basis_pct=0.015,
        prev_basis_pct=0.010,  # confirmation 2
        iv_skew=1.8,  # confirmation 3 (< 3%)
        max_pain=158.0,  # confirmation 4 (> 154)
        spot_price=154.0,
    )


@pytest.fixture
def base_tech() -> TechnicalIndicatorsRow:
    return TechnicalIndicatorsRow(
        symbol="TATASTEEL",
        trade_date=date(2026, 9, 25),
        ema_20=150.0,
        ema_50=145.0,
        sma_200=130.0,  # 150 > 145 > 130 and close 154 > 150
        atr_14=4.0,
        atr_sma_20=6.0,
        atr_compression=True,  # 4/6 = 0.67 < 0.80
        mansfield_rs_500=0.05,
        prev_mansfield_rs_500=0.03,  # positive & rising
        avwap_swing_low=146.0,
        avwap_earnings=142.0,
        vpvr_hvn=148.0,
        is_vpvr_breakout=True,
        fractal_swing_low_20d=147.0,
        vpvr_hvn_levels=[165.0, 175.0],
        swing_high_levels_250d=[178.0],
        adtv_20d=300000000.0,  # 30 Cr >= 15 Cr
    )


@pytest.fixture
def base_surv() -> SurveillanceRegistryRow:
    return SurveillanceRegistryRow(
        symbol="TATASTEEL",
        record_date=date(2026, 9, 25),
        asm_stage=0,
        gsm_stage=0,
        days_to_earnings=30,
    )


@pytest.fixture
def base_regime() -> MarketRegimeRow:
    return MarketRegimeRow(
        trade_date=date(2026, 9, 25),
        regime_classification="RISK_ON",
    )


def test_tactical_desk_all_pass_verdict_execute(
    base_price: DailyPriceRow,
    base_deriv: DerivativeMetricsRow,
    base_tech: TechnicalIndicatorsRow,
    base_surv: SurveillanceRegistryRow,
    base_regime: MarketRegimeRow,
) -> None:
    cfg = load_config()
    desk = TacticalDesk(cfg=cfg)
    card = desk.evaluate(
        symbol="TATASTEEL",
        eval_date=date(2026, 9, 25),
        price=base_price,
        deriv=base_deriv,
        tech=base_tech,
        surv=base_surv,
        regime=base_regime,
        is_bfsi=False,
        is_fno=True,
    )
    assert card.hard_gates_pass is True
    assert card.score == 10.0  # 5 deriv + 5 tech
    assert card.verdict == "EXECUTE"
    assert card.entry_trigger is not None
    assert card.stop_loss is not None
    assert card.target_1 is not None
    assert card.target_2 is not None
    assert card.risk_reward_ratio is not None
    assert card.risk_reward_ratio >= 2.50
    assert card.position_size_shares is not None and card.position_size_shares > 0
    assert card.valid_until == date(2026, 9, 26)


def test_acceptance_test_11_risk_off_regime_blocks_execution(
    base_price: DailyPriceRow,
    base_deriv: DerivativeMetricsRow,
    base_tech: TechnicalIndicatorsRow,
    base_surv: SurveillanceRegistryRow,
) -> None:
    """Acceptance Test 11: Regime gate blocks execution when market is in RISK_OFF."""
    cfg = load_config()
    desk = TacticalDesk(cfg=cfg)
    risk_off_regime = MarketRegimeRow(
        trade_date=date(2026, 9, 25),
        regime_classification="RISK_OFF",
    )
    card = desk.evaluate(
        symbol="TATASTEEL",
        eval_date=date(2026, 9, 25),
        price=base_price,
        deriv=base_deriv,
        tech=base_tech,
        surv=base_surv,
        regime=risk_off_regime,
        is_bfsi=False,
        is_fno=True,
    )
    # Score is 10, but RISK_OFF threshold is 99 -> ABORT
    assert card.verdict == "ABORT"
    assert card.entry_trigger is None
    assert "RISK_OFF" in str(card.card_details.get("rejection_reasons"))


def test_acceptance_test_12_active_confirmations_insufficient(
    base_price: DailyPriceRow,
    base_tech: TechnicalIndicatorsRow,
    base_surv: SurveillanceRegistryRow,
    base_regime: MarketRegimeRow,
) -> None:
    """Acceptance Test 12: Less than 2 active confirmations must trigger ABORT."""
    cfg = load_config()
    desk = TacticalDesk(cfg=cfg)
    # Derivative metrics with ONLY 1 active confirmation (iv_skew ok, all others failing)
    deriv = DerivativeMetricsRow(
        symbol="TATASTEEL",
        trade_date=date(2026, 9, 25),
        fno_oi=50000000,
        fno_oi_change=3000000,
        prev_fno_oi=45000000,
        cost_of_carry=0.08,
        prev_cost_of_carry=0.06,
        pcr=0.95,
        prev_pcr=0.90,
        mwpl_pct=45.0,
        has_institutional_net_buy=True,
        rollover_pct=50.0,
        avg_rollover_pct_20d=60.0,  # Fail
        basis_pct=-0.01,
        prev_basis_pct=-0.02,  # Fail (negative)
        iv_skew=1.5,  # Pass (< 3%)
        max_pain=140.0,  # Fail (< spot 154)
        spot_price=154.0,
    )
    card = desk.evaluate(
        symbol="TATASTEEL",
        eval_date=date(2026, 9, 25),
        price=base_price,
        deriv=deriv,
        tech=base_tech,
        surv=base_surv,
        regime=base_regime,
        is_bfsi=False,
        is_fno=True,
    )
    assert card.verdict == "ABORT"
    assert "Active confirmations" in str(card.card_details.get("rejection_reasons"))


def test_hard_gate_surveillance_asm(
    base_price: DailyPriceRow,
    base_deriv: DerivativeMetricsRow,
    base_tech: TechnicalIndicatorsRow,
    base_regime: MarketRegimeRow,
) -> None:
    cfg = load_config()
    desk = TacticalDesk(cfg=cfg)
    surv_asm = SurveillanceRegistryRow(
        symbol="TATASTEEL",
        record_date=date(2026, 9, 25),
        asm_stage=2,  # ASM stage 2 is fatal
    )
    card = desk.evaluate(
        symbol="TATASTEEL",
        eval_date=date(2026, 9, 25),
        price=base_price,
        deriv=base_deriv,
        tech=base_tech,
        surv=surv_asm,
        regime=base_regime,
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "ABORT"


def test_hard_gate_mwpl_exceeded(
    base_price: DailyPriceRow,
    base_tech: TechnicalIndicatorsRow,
    base_surv: SurveillanceRegistryRow,
    base_regime: MarketRegimeRow,
) -> None:
    cfg = load_config()
    desk = TacticalDesk(cfg=cfg)
    deriv = DerivativeMetricsRow(
        symbol="TATASTEEL",
        trade_date=date(2026, 9, 25),
        fno_oi=50000000,
        fno_oi_change=1000,
        mwpl_pct=85.5,  # > 82%
    )
    card = desk.evaluate(
        symbol="TATASTEEL",
        eval_date=date(2026, 9, 25),
        price=base_price,
        deriv=deriv,
        tech=base_tech,
        surv=base_surv,
        regime=base_regime,
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "ABORT"


def test_delivery_percentile_hard_rule(
    base_price: DailyPriceRow,
    base_deriv: DerivativeMetricsRow,
    base_tech: TechnicalIndicatorsRow,
    base_surv: SurveillanceRegistryRow,
    base_regime: MarketRegimeRow,
) -> None:
    cfg = load_config()
    desk = TacticalDesk(cfg=cfg)
    # Delivery percentile 75 < 80 minimum
    low_deliv_price = base_price.model_copy(update={"delivery_percentile_20d": 75.0})
    card = desk.evaluate(
        symbol="TATASTEEL",
        eval_date=date(2026, 9, 25),
        price=low_deliv_price,
        deriv=base_deriv,
        tech=base_tech,
        surv=base_surv,
        regime=base_regime,
    )
    assert card.verdict == "ABORT"
    assert "Delivery value percentile < 80th percentile" in str(
        card.card_details.get("rejection_reasons")
    )


def test_acceptance_test_9_ten_liquid_fno_names(
    base_price: DailyPriceRow,
    base_deriv: DerivativeMetricsRow,
    base_tech: TechnicalIndicatorsRow,
    base_surv: SurveillanceRegistryRow,
    base_regime: MarketRegimeRow,
) -> None:
    """Acceptance Test 9: 10 liquid F&O names processed by Tactical Desk."""
    cfg = load_config()
    desk = TacticalDesk(cfg=cfg)
    fno_symbols = [
        "RELIANCE",
        "TCS",
        "INFY",
        "BHARTIARTL",
        "ITC",
        "LT",
        "HINDUNILVR",
        "TATAMOTORS",
        "SUNPHARMA",
        "MARUTI",
    ]

    cards = []
    for sym in fno_symbols:
        p = base_price.model_copy(
            update={
                "symbol": sym,
                "open_price": 996.0,
                "close_price": 1000.0,
                "high_price": 1010.0,
                "low_price": 980.0,
                "prev_close": 995.0,
                "traded_value": 500000000.0,
            }
        )
        d = base_deriv.model_copy(update={"symbol": sym})
        t = base_tech.model_copy(
            update={
                "symbol": sym,
                "avwap_swing_low": 950.0,
                "fractal_swing_low_20d": 960.0,
                "vpvr_hvn_levels": [1080.0],
                "swing_high_levels_250d": [1200.0],
            }
        )
        s = base_surv.model_copy(update={"symbol": sym})

        card = desk.evaluate(
            symbol=sym,
            eval_date=date(2026, 9, 25),
            price=p,
            deriv=d,
            tech=t,
            surv=s,
            regime=base_regime,
            is_bfsi=False,
            is_fno=True,
        )
        cards.append(card)

    assert len(cards) == 10
    for c in cards:
        assert c.desk_type == "TACTICAL"
        assert c.hard_gates_pass is True
        assert c.score >= 8.0
        assert c.verdict == "EXECUTE"
        assert c.entry_trigger is not None
        assert c.target_2 is not None
        assert c.risk_reward_ratio is not None and c.risk_reward_ratio >= 2.50


def test_hard_gate_price_below_minimum(
    base_price: DailyPriceRow,
    base_deriv: DerivativeMetricsRow,
    base_tech: TechnicalIndicatorsRow,
    base_surv: SurveillanceRegistryRow,
    base_regime: MarketRegimeRow,
) -> None:
    cfg = load_config()
    desk = TacticalDesk(cfg=cfg)
    p = base_price.model_copy(update={"close_price": 15.0})  # < 20.0
    card = desk.evaluate(
        "PENNY", date(2026, 9, 25), p, base_deriv, base_tech, base_surv, base_regime
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "ABORT"


def test_hard_gate_earnings_too_close(
    base_price: DailyPriceRow,
    base_deriv: DerivativeMetricsRow,
    base_tech: TechnicalIndicatorsRow,
    base_regime: MarketRegimeRow,
) -> None:
    cfg = load_config()
    desk = TacticalDesk(cfg=cfg)
    surv = SurveillanceRegistryRow(
        symbol="TATASTEEL", record_date=date(2026, 9, 25), days_to_earnings=3
    )
    card = desk.evaluate(
        "TATASTEEL", date(2026, 9, 25), base_price, base_deriv, base_tech, surv, base_regime
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "ABORT"


def test_hard_gate_excessive_gap(
    base_price: DailyPriceRow,
    base_deriv: DerivativeMetricsRow,
    base_tech: TechnicalIndicatorsRow,
    base_surv: SurveillanceRegistryRow,
    base_regime: MarketRegimeRow,
) -> None:
    cfg = load_config()
    desk = TacticalDesk(cfg=cfg)
    p = base_price.model_copy(
        update={"open_price": 160.0, "prev_close": 149.0}
    )  # Gap = 11 > 1.5 * 4.0 = 6.0
    card = desk.evaluate(
        "TATASTEEL", date(2026, 9, 25), p, base_deriv, base_tech, base_surv, base_regime
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "ABORT"


def test_hard_gate_circuit_band_tight(
    base_price: DailyPriceRow,
    base_deriv: DerivativeMetricsRow,
    base_tech: TechnicalIndicatorsRow,
    base_surv: SurveillanceRegistryRow,
    base_regime: MarketRegimeRow,
) -> None:
    cfg = load_config()
    desk = TacticalDesk(cfg=cfg)
    p = base_price.model_copy(update={"circuit_band": 2.0})  # < 5.0
    card = desk.evaluate(
        "TATASTEEL", date(2026, 9, 25), p, base_deriv, base_tech, base_surv, base_regime
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "ABORT"


def test_hard_gate_bfsi_prohibited(
    base_price: DailyPriceRow,
    base_deriv: DerivativeMetricsRow,
    base_tech: TechnicalIndicatorsRow,
    base_surv: SurveillanceRegistryRow,
    base_regime: MarketRegimeRow,
) -> None:
    cfg = load_config()
    desk = TacticalDesk(cfg=cfg)
    card = desk.evaluate(
        "HDFCBANK",
        date(2026, 9, 25),
        base_price,
        base_deriv,
        base_tech,
        base_surv,
        base_regime,
        is_bfsi=True,
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "ABORT"


def test_hard_gate_non_fno_prohibited(
    base_price: DailyPriceRow,
    base_deriv: DerivativeMetricsRow,
    base_tech: TechnicalIndicatorsRow,
    base_surv: SurveillanceRegistryRow,
    base_regime: MarketRegimeRow,
) -> None:
    cfg = load_config()
    desk = TacticalDesk(cfg=cfg)
    card = desk.evaluate(
        "CASHONLY",
        date(2026, 9, 25),
        base_price,
        base_deriv,
        base_tech,
        base_surv,
        base_regime,
        is_fno=False,
    )
    assert card.hard_gates_pass is False
    assert card.verdict == "ABORT"


def test_hard_gate_liquidity_insufficient(
    base_price: DailyPriceRow,
    base_deriv: DerivativeMetricsRow,
    base_tech: TechnicalIndicatorsRow,
    base_surv: SurveillanceRegistryRow,
    base_regime: MarketRegimeRow,
) -> None:
    cfg = load_config()
    desk = TacticalDesk(cfg=cfg)
    p = base_price.model_copy(update={"traded_value": 50000000.0})
    t = base_tech.model_copy(update={"adtv_20d": 50000000.0})  # 5 Cr < 15 Cr
    card = desk.evaluate("ILLIQUID", date(2026, 9, 25), p, base_deriv, t, base_surv, base_regime)
    assert card.hard_gates_pass is False
    assert card.verdict == "ABORT"


def test_tactical_desk_evaluate_from_db(
    base_price: DailyPriceRow,
    base_deriv: DerivativeMetricsRow,
    base_tech: TechnicalIndicatorsRow,
    base_surv: SurveillanceRegistryRow,
    base_regime: MarketRegimeRow,
) -> None:
    from unittest.mock import MagicMock

    mock_db = MagicMock()
    mock_db.select.side_effect = lambda table, **kwargs: (
        [{"symbol": "TATASTEEL", "is_bfsi": False, "is_fno": True}]
        if table == "universe"
        else [base_price.model_dump(mode="json")]
        if table == "daily_prices"
        else [base_deriv.model_dump(mode="json")]
        if table == "derivative_metrics"
        else [base_tech.model_dump(mode="json")]
        if table == "technical_indicators"
        else [base_surv.model_dump(mode="json")]
        if table == "surveillance_registry"
        else [base_regime.model_dump(mode="json")]
        if table == "market_regime"
        else []
    )
    desk = TacticalDesk(db=mock_db)
    card = desk.evaluate_from_db("TATASTEEL", date(2026, 9, 25))
    assert card is not None
    assert card.symbol == "TATASTEEL"
    assert card.verdict == "EXECUTE"
