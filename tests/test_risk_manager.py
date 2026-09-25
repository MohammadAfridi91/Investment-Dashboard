"""Tests for Risk Manager module (trade architecture, targets, sizing)."""

import pytest

from core.engines.risk_manager import compute_trade_architecture


def test_trade_architecture_normal_case() -> None:
    # High: 1000.0, Entry = 1000 * 1.0005 = 1000.50
    # Stop: min(950, 960) = 950.0
    # Risk unit: 1000.50 - 950.0 = 50.50
    # HVNs: [1080.0, 1150.0] -> T1 = 1080.0
    # Resistances: [1200.0] -> T2 = 1200.0
    # R:R = (1200 - 1000.50) / 50.50 = 3.95 (>= 2.50)
    # Capital: 50,00,000. Risk 1% = 50,000. Risk shares = 50,000 / 50.50 = 990
    # Max allocation 10% = 500,000. Cap shares = 500,000 / 1000.50 = 499
    # Position size = min(990, 499) = 499
    arch = compute_trade_architecture(
        high_price_today=1000.0,
        avwap_swing_low=950.0,
        fractal_swing_low_20d=960.0,
        vpvr_hvn_levels=[1080.0, 1150.0],
        swing_high_levels_250d=[1200.0],
        portfolio_capital=5000000.0,
    )
    assert arch.is_valid is True
    assert arch.entry_trigger == 1000.50
    assert arch.stop_loss == 950.0
    assert arch.risk_unit == 50.50
    assert arch.target_1 == 1080.0
    assert arch.target_2 == 1200.0
    assert arch.risk_reward_ratio == pytest.approx(3.95, rel=1e-2)
    assert arch.position_size_shares == 499


def test_trade_architecture_fallback_targets() -> None:
    # No HVNs or resistances provided -> fallback to 1.5 * risk and 3.0 * risk
    arch = compute_trade_architecture(
        high_price_today=500.0,
        avwap_swing_low=480.0,
        fractal_swing_low_20d=485.0,
        vpvr_hvn_levels=None,
        swing_high_levels_250d=None,
        portfolio_capital=5000000.0,
    )
    assert arch.is_valid is True
    # Entry = 500.0 * 1.0005 = 500.25
    # Stop = min(480, 485) = 480.0
    # Risk unit = 20.25
    # T1 = 500.25 + 1.5 * 20.25 = 530.62 or 530.63
    # T2 = 500.25 + 3.0 * 20.25 = 561.0
    assert arch.target_1 > arch.entry_trigger
    assert arch.target_2 > arch.target_1
    assert arch.risk_reward_ratio >= 2.50


def test_trade_architecture_invalid_stop_above_entry() -> None:
    arch = compute_trade_architecture(
        high_price_today=100.0,
        avwap_swing_low=105.0,
        fractal_swing_low_20d=110.0,
        vpvr_hvn_levels=[120.0],
        swing_high_levels_250d=[150.0],
        portfolio_capital=5000000.0,
    )
    assert arch.is_valid is False
    assert "strictly below" in (arch.rejection_reason or "")


def test_trade_architecture_low_rr_rejection() -> None:
    # Target 2 is too close to entry -> R:R < 2.50
    arch = compute_trade_architecture(
        high_price_today=1000.0,
        avwap_swing_low=900.0,  # risk_unit = ~100
        fractal_swing_low_20d=900.0,
        vpvr_hvn_levels=[1020.0],
        swing_high_levels_250d=[1050.0],  # T2 = 1050 -> reward = 50, R:R = 0.50
        portfolio_capital=5000000.0,
        min_rr=2.50,
    )
    assert arch.is_valid is False
    assert "below minimum requirement" in (arch.rejection_reason or "")


def test_trade_architecture_fallback_current_low() -> None:
    # No avwap or fractal low, but current_low provided
    arch = compute_trade_architecture(
        high_price_today=1000.0,
        avwap_swing_low=None,
        fractal_swing_low_20d=None,
        vpvr_hvn_levels=None,
        swing_high_levels_250d=None,
        portfolio_capital=5000000.0,
        current_low=950.0,
    )
    assert arch.is_valid is True
    assert arch.stop_loss == round(950.0 * 0.98, 2)


def test_trade_architecture_zero_or_negative_high() -> None:
    arch = compute_trade_architecture(
        high_price_today=0.0,
        avwap_swing_low=90.0,
        fractal_swing_low_20d=90.0,
        vpvr_hvn_levels=None,
        swing_high_levels_250d=None,
        portfolio_capital=5000000.0,
    )
    assert arch.is_valid is False
    assert "strictly positive" in (arch.rejection_reason or "")
