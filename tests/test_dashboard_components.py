"""Tests for dashboard components (charts, renderers, and DCF simulator)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import plotly.graph_objects as go

from dashboard.components.card_renderers import (
    render_strategic_card,
    render_tactical_card,
)
from dashboard.components.charts import (
    create_candlestick_chart,
    create_regime_gauge,
    create_vpvr_chart,
)


def test_create_candlestick_chart_normal() -> None:
    df = pd.DataFrame(
        {
            "trade_date": ["2026-09-22", "2026-09-23", "2026-09-24"],
            "open_price": [100.0, 102.0, 101.0],
            "high_price": [105.0, 104.0, 106.0],
            "low_price": [99.0, 100.0, 100.0],
            "close_price": [102.0, 101.0, 105.0],
            "volume": [10000, 15000, 20000],
        }
    )

    fig = create_candlestick_chart(df, avwap_swing_low=98.0, avwap_earnings=97.0, symbol="TEST")
    assert isinstance(fig, go.Figure)
    assert len(fig.data) >= 2  # Candlestick + Volume


def test_create_candlestick_chart_empty() -> None:
    df = pd.DataFrame()
    fig = create_candlestick_chart(df, symbol="EMPTY")
    assert isinstance(fig, go.Figure)
    assert "No price data" in fig.layout.title.text


def test_create_vpvr_chart_normal() -> None:
    price_levels = [100.0, 101.0, 102.0, 103.0]
    volumes = [500.0, 1200.0, 3000.0, 800.0]
    fig = create_vpvr_chart(price_levels, volumes, hvn_levels=[102.0], current_price=101.5)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1


def test_create_vpvr_chart_empty() -> None:
    fig = create_vpvr_chart([], [])
    assert isinstance(fig, go.Figure)
    assert "No VPVR" in fig.layout.title.text


def test_create_regime_gauge() -> None:
    fig = create_regime_gauge(13.5, "RISK_ON")
    assert isinstance(fig, go.Figure)
    assert fig.data[0].value == 13.5


def test_render_tactical_card_mocked_st() -> None:
    card_dict = {
        "symbol": "TCS",
        "eval_date": "2026-09-25",
        "verdict": "EXECUTE",
        "score": 9.0,
        "max_score": 10.0,
        "hard_gates_pass": True,
        "entry_trigger": 3850.0,
        "stop_loss": 3780.0,
        "target_1": 3950.0,
        "target_2": 4100.0,
        "risk_reward_ratio": 2.85,
        "position_size_shares": 120,
        "card_details": {
            "gates": {"surveillance": True, "liquidity": True},
            "active_confirmations": ["RS_RISING"],
            "derivatives_score": {"total": 4},
            "technicals_score": {"total": 5},
        },
    }

    with (
        patch("streamlit.markdown"),
        patch("streamlit.metric"),
        patch("streamlit.subheader"),
        patch("streamlit.columns", return_value=[MagicMock(), MagicMock()]),
        patch("streamlit.expander"),
    ):
        render_tactical_card(card_dict)


def test_render_strategic_card_mocked_st() -> None:
    card_dict = {
        "symbol": "INFY",
        "eval_date": "2026-09-25",
        "verdict": "TIER_1",
        "score": 45.0,
        "max_score": 50.0,
        "hard_gates_pass": True,
        "restatement_caution": False,
        "card_details": {
            "moat_score": {"total": 25},
            "sector_score": {"total": 10},
            "valuation_score": {"total": 10},
            "forensic_gates": {"beneish_m_score": True},
        },
    }

    with (
        patch("streamlit.markdown"),
        patch("streamlit.metric"),
        patch("streamlit.subheader"),
        patch(
            "streamlit.columns",
            return_value=[MagicMock(), MagicMock(), MagicMock()],
        ),
        patch("streamlit.expander"),
        patch("streamlit.info"),
    ):
        render_strategic_card(card_dict)
