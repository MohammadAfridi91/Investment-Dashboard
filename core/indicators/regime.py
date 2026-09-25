from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from core.database.client import DB
from core.utils.logging import get_logger

log = get_logger("indicators.regime")


def compute_market_breadth(daily_prices: Sequence[dict[str, Any]]) -> float | None:
    """Compute market breadth ratio = advancing stocks / total active traded stocks.

    An advancing stock has close_price > prev_close.
    """
    if not daily_prices:
        return None

    advances = 0
    total = 0

    for dp in daily_prices:
        cp = dp.get("close_price")
        prev = dp.get("prev_close")
        if cp is None or prev is None:
            continue
        try:
            c_val = float(cp)
            p_val = float(prev)
            if c_val <= 0 or p_val <= 0:
                continue
            total += 1
            if c_val > p_val:
                advances += 1
        except (ValueError, TypeError):
            continue

    if total == 0:
        return None

    return round(advances / total, 4)


def classify_regime(
    india_vix: float | None,
    market_breadth: float | None,
    config: Any,
) -> str:
    """Classify market regime into RISK_OFF, RISK_ON, or NEUTRAL.

    Appendix C:
        VIX RISK_OFF: > 20.0
        Breadth RISK_OFF: < 0.40 (< 40%)
        VIX RISK_ON: < 15.0
        Breadth RISK_ON: > 0.60 (> 60%)
    """
    vix_off = 20.0
    breadth_off = 0.40
    vix_on = 15.0
    breadth_on = 0.60

    if config is not None:
        if isinstance(config, dict):
            reg_cfg = config.get("market_regime", {})
            vix_off = reg_cfg.get("vix_risk_off", vix_off)
            breadth_off = reg_cfg.get("breadth_risk_off", breadth_off)
            vix_on = reg_cfg.get("vix_risk_on", vix_on)
            breadth_on = reg_cfg.get("breadth_risk_on", breadth_on)
        elif hasattr(config, "market_regime"):
            reg_cfg_obj = getattr(config, "market_regime", None)
            if reg_cfg_obj is not None:
                vix_off = getattr(reg_cfg_obj, "vix_risk_off", vix_off)
                breadth_off = getattr(reg_cfg_obj, "breadth_risk_off", breadth_off)
                vix_on = getattr(reg_cfg_obj, "vix_risk_on", vix_on)
                breadth_on = getattr(reg_cfg_obj, "breadth_risk_on", breadth_on)

    # RISK_OFF if VIX elevated OR market breadth severely broken
    if (india_vix is not None and india_vix > vix_off) or (
        market_breadth is not None and market_breadth < breadth_off
    ):
        return "RISK_OFF"

    # RISK_ON if VIX subdued AND market breadth strong
    if (india_vix is not None and india_vix < vix_on) and (
        market_breadth is not None and market_breadth > breadth_on
    ):
        return "RISK_ON"

    return "NEUTRAL"


def update_daily_market_regime(
    db: DB,
    config: Any,
    target_date: date,
) -> dict[str, Any]:
    """Compute market breadth, classify regime, and update market_regime table for target_date."""
    # Fetch today's prices for breadth calculation
    prices = db.select(
        "daily_prices",
        columns="close_price,prev_close",
        filters={"trade_date": target_date.isoformat()},
        limit=5000,
    )
    breadth = compute_market_breadth(prices)

    # Query current market regime row to get existing india_vix
    existing_regime = db.select(
        "market_regime",
        columns="india_vix,nifty_trend",
        filters={"trade_date": target_date.isoformat()},
        limit=1,
    )

    vix: float | None = None
    if existing_regime and existing_regime[0].get("india_vix") is not None:
        try:
            vix = float(existing_regime[0]["india_vix"])
        except (ValueError, TypeError):
            vix = None

    regime_class = classify_regime(vix, breadth, config)

    update_payload: dict[str, Any] = {
        "trade_date": target_date.isoformat(),
        "market_breadth": breadth,
        "regime_classification": regime_class,
    }

    try:
        db.upsert("market_regime", [update_payload], on_conflict="trade_date")
        log.info(
            "regime_updated",
            date=str(target_date),
            vix=vix,
            breadth=breadth,
            classification=regime_class,
        )
    except Exception as e:
        log.error("regime_upsert_failed", error=str(e))

    return update_payload
