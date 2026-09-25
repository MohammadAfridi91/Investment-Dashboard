"""Risk Manager Module for Dalal Street Engine.

Implements Appendix A.21 / A.22 / A.23:
- Entry Trigger: high_price_today * 1.0005 (0.05% buffer)
- Stop Loss: min(avwap_swing_low, fractal_swing_low_20d)
- Risk Unit: entry_trigger - stop_loss
- Target 1: nearest HVN > entry_trigger (or fallback entry + 1.5 * risk_unit)
- Target 2: min(resistances > Target 1) (or fallback entry + 3.0 * risk_unit)
- Risk:Reward Ratio: (Target 2 - entry_trigger) / risk_unit
- Position Sizing: min(risk_based_shares, capital_based_shares)
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TradeArchitecture(BaseModel):
    """Encapsulates execution parameters computed by Risk Manager."""

    model_config = ConfigDict(from_attributes=True)

    entry_trigger: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_unit: float
    risk_reward_ratio: float
    position_size_shares: int
    is_valid: bool
    rejection_reason: str | None = None
    metadata: dict[str, float | int | str] = Field(default_factory=dict)


def compute_trade_architecture(
    high_price_today: float,
    avwap_swing_low: float | None,
    fractal_swing_low_20d: float | None,
    vpvr_hvn_levels: list[float] | None,
    swing_high_levels_250d: list[float] | None,
    portfolio_capital: float,
    current_low: float | None = None,
    min_rr: float = 2.50,
    entry_buffer_pct: float = 0.0005,
    risk_capital_pct: float = 0.01,
    max_capital_pct: float = 0.10,
) -> TradeArchitecture:
    """Computes tactical trade architecture: entry, stop, targets, R:R, and size.

    Args:
        high_price_today: Session high price.
        avwap_swing_low: Anchored VWAP from swing low level.
        fractal_swing_low_20d: 20-day fractal swing low level.
        vpvr_hvn_levels: High Volume Nodes from VPVR.
        swing_high_levels_250d: 250-day swing high resistance levels.
        portfolio_capital: Total portfolio capital in INR (e.g. 5,000,000).
        current_low: Optional session low price for fallback stop.
        min_rr: Minimum acceptable Risk-to-Reward ratio (default 2.50).
        entry_buffer_pct: Percentage buffer above session high (default 0.05%).
        risk_capital_pct: Fraction of capital to risk per trade (default 1%).
        max_capital_pct: Maximum portfolio allocation per trade (default 10%).

    Returns:
        TradeArchitecture instance.
    """
    if high_price_today <= 0:
        return TradeArchitecture(
            entry_trigger=0.0,
            stop_loss=0.0,
            target_1=0.0,
            target_2=0.0,
            risk_unit=0.0,
            risk_reward_ratio=0.0,
            position_size_shares=0,
            is_valid=False,
            rejection_reason="High price must be strictly positive",
        )

    # 1. Entry Trigger: 0.05% above today's high
    entry = round(high_price_today * (1.0 + entry_buffer_pct), 2)

    # 2. Stop Loss: min(avwap_swing_low, fractal_swing_low_20d)
    stop_candidates: list[float] = []
    if avwap_swing_low is not None and avwap_swing_low > 0:
        stop_candidates.append(avwap_swing_low)
    if fractal_swing_low_20d is not None and fractal_swing_low_20d > 0:
        stop_candidates.append(fractal_swing_low_20d)

    if stop_candidates:
        stop = round(min(stop_candidates), 2)
    elif current_low is not None and current_low > 0:
        stop = round(current_low * 0.98, 2)
    else:
        return TradeArchitecture(
            entry_trigger=entry,
            stop_loss=0.0,
            target_1=0.0,
            target_2=0.0,
            risk_unit=0.0,
            risk_reward_ratio=0.0,
            position_size_shares=0,
            is_valid=False,
            rejection_reason="No swing low reference available for stop loss",
        )

    # 3. Risk Unit
    risk_unit = round(entry - stop, 2)
    if risk_unit <= 0:
        return TradeArchitecture(
            entry_trigger=entry,
            stop_loss=stop,
            target_1=0.0,
            target_2=0.0,
            risk_unit=risk_unit,
            risk_reward_ratio=0.0,
            position_size_shares=0,
            is_valid=False,
            rejection_reason=f"Stop loss ({stop:.2f}) must be strictly below entry trigger ({entry:.2f})",
        )

    # 4. Target 1: nearest HVN > entry
    valid_hvns = [round(h, 2) for h in (vpvr_hvn_levels or []) if h > entry + 0.01]
    target_1 = min(valid_hvns) if valid_hvns else round(entry + 1.5 * risk_unit, 2)

    if target_1 <= entry:
        target_1 = round(entry + 1.5 * risk_unit, 2)

    # 5. Target 2: min(resistances > Target 1)
    res_candidates: list[float] = []
    for r in swing_high_levels_250d or []:
        if r > target_1 + 0.01:
            res_candidates.append(round(r, 2))

    if res_candidates:
        target_2 = min(res_candidates)
    else:
        hvn_candidates = [round(h, 2) for h in (vpvr_hvn_levels or []) if h > target_1 + 0.01]
        target_2 = min(hvn_candidates) if hvn_candidates else round(entry + 3.0 * risk_unit, 2)

    if target_2 <= target_1:
        target_2 = round(target_1 + 1.5 * risk_unit, 2)

    # 6. Risk-to-Reward Ratio
    risk_reward_ratio = round((target_2 - entry) / risk_unit, 2)

    # 7. Position Sizing
    risk_budget = portfolio_capital * risk_capital_pct
    max_allocation = portfolio_capital * max_capital_pct
    risk_shares = int(risk_budget / risk_unit) if risk_unit > 0 else 0
    cap_shares = int(max_allocation / entry) if entry > 0 else 0
    position_size_shares = max(0, min(risk_shares, cap_shares))

    # 8. Validation checks
    is_valid = True
    rejection_reason: str | None = None

    if position_size_shares <= 0:
        is_valid = False
        rejection_reason = "Position size is 0 shares (capital or risk limit exceeded)"
    elif risk_reward_ratio < min_rr:
        is_valid = False
        rejection_reason = (
            f"R:R ratio ({risk_reward_ratio:.2f}) is below minimum requirement ({min_rr:.2f})"
        )

    return TradeArchitecture(
        entry_trigger=entry,
        stop_loss=stop,
        target_1=target_1,
        target_2=target_2,
        risk_unit=risk_unit,
        risk_reward_ratio=risk_reward_ratio,
        position_size_shares=position_size_shares,
        is_valid=is_valid,
        rejection_reason=rejection_reason,
        metadata={
            "risk_shares": risk_shares,
            "cap_shares": cap_shares,
            "risk_budget": risk_budget,
            "max_allocation": max_allocation,
        },
    )
