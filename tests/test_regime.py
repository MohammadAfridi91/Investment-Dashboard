from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from core.indicators.regime import (
    classify_regime,
    compute_market_breadth,
    update_daily_market_regime,
)


def test_compute_market_breadth() -> None:
    # 5 stocks: 4 advances, 1 decline
    daily_prices = [
        {"close_price": 105.0, "prev_close": 100.0},  # advance
        {"close_price": 200.0, "prev_close": 195.0},  # advance
        {"close_price": 50.0, "prev_close": 52.0},  # decline
        {"close_price": 310.0, "prev_close": 300.0},  # advance
        {"close_price": 75.0, "prev_close": 70.0},  # advance
    ]
    breadth = compute_market_breadth(daily_prices)
    assert breadth == 0.8  # 4 / 5 = 0.80


def test_compute_market_breadth_empty_or_invalid() -> None:
    assert compute_market_breadth([]) is None
    assert compute_market_breadth([{"close_price": 0.0, "prev_close": 0.0}]) is None


def test_classify_regime_thresholds() -> None:
    config = {
        "market_regime": {
            "vix_risk_off": 20.0,
            "breadth_risk_off": 0.40,
            "vix_risk_on": 15.0,
            "breadth_risk_on": 0.60,
        }
    }

    # RISK_OFF conditions (VIX elevated OR breadth broken)
    assert classify_regime(india_vix=22.5, market_breadth=0.65, config=config) == "RISK_OFF"
    assert classify_regime(india_vix=14.0, market_breadth=0.35, config=config) == "RISK_OFF"
    assert classify_regime(india_vix=25.0, market_breadth=0.30, config=config) == "RISK_OFF"

    # RISK_ON conditions (VIX calm AND breadth strong)
    assert classify_regime(india_vix=13.5, market_breadth=0.72, config=config) == "RISK_ON"

    # NEUTRAL conditions
    assert classify_regime(india_vix=17.0, market_breadth=0.55, config=config) == "NEUTRAL"
    assert classify_regime(india_vix=14.0, market_breadth=0.50, config=config) == "NEUTRAL"
    assert classify_regime(india_vix=None, market_breadth=0.50, config=config) == "NEUTRAL"


def test_update_daily_market_regime_integration() -> None:
    mock_db = MagicMock()
    mock_db.select.side_effect = [
        # daily_prices
        [
            {"close_price": 105.0, "prev_close": 100.0},
            {"close_price": 95.0, "prev_close": 100.0},
        ],
        # existing market_regime
        [
            {"india_vix": 13.5, "nifty_trend": "BULLISH"},
        ],
    ]

    target_date = date(2024, 1, 25)
    config = {
        "market_regime": {
            "vix_risk_off": 20.0,
            "breadth_risk_off": 0.40,
            "vix_risk_on": 15.0,
            "breadth_risk_on": 0.60,
        }
    }

    res = update_daily_market_regime(mock_db, config, target_date)
    assert res["trade_date"] == "2024-01-25"
    assert res["market_breadth"] == 0.50
    assert res["regime_classification"] == "NEUTRAL"
    mock_db.upsert.assert_called_once()
