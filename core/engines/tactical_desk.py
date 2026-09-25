"""Tactical Desk Execution Engine (Card 1).

Evaluates high-conviction swing/momentum trading setups in F&O non-BFSI universe:
- Phase 1: Hard Gates (Surveillance, F&O ban/MWPL, Circuit band, Liquidity, Price, Earnings, Gap)
- Phase 2: Derivatives Confirmation (OI buildup, CoC, PCR, Delivery, Institutional flow)
- Phase 3: Technical Confluence (AVWAP, VPVR breakout, Trend alignment, Mansfield RS, ATR compression)
- Phase 4: Confirmation & Regime Gates (Regime threshold, Active confirmations >= 2, R:R >= 2.50)
- Execution: Position sizing, Entry, Stop, Targets T1/T2, valid_until = T+1
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from core.config import Config, load_config
from core.database.client import DB
from core.engines.risk_manager import TradeArchitecture, compute_trade_architecture
from core.models import (
    DailyPriceRow,
    DerivativeMetricsRow,
    MarketRegimeRow,
    SurveillanceRegistryRow,
    TechnicalIndicatorsRow,
    TradeCheckCardRow,
)


class TacticalDesk:
    """Card 1 Tactical Evaluation Engine."""

    def __init__(self, db: DB | None = None, cfg: Config | None = None) -> None:
        self.db = db
        self.cfg = cfg or load_config()

    def evaluate(
        self,
        symbol: str,
        eval_date: date,
        price: DailyPriceRow,
        deriv: DerivativeMetricsRow | None = None,
        tech: TechnicalIndicatorsRow | None = None,
        surv: SurveillanceRegistryRow | None = None,
        regime: MarketRegimeRow | None = None,
        is_bfsi: bool = False,
        is_fno: bool = True,
    ) -> TradeCheckCardRow:
        """Evaluates Card 1 tactical criteria for a single symbol on a given trade date."""
        card_id = str(uuid.uuid4())
        rejection_reasons: list[str] = []

        # BFSI & F&O Filter check
        if is_bfsi:
            rejection_reasons.append("BFSI sector prohibited for Card 1 tactical desk")
        if not is_fno:
            rejection_reasons.append("Symbol is not in active F&O universe")

        # Phase 1: Hard Gates
        gate_surveillance = (
            surv is None
            or (
                surv.asm_stage < self.cfg.fatal.asm_min_stage_kill
                and surv.gsm_stage < self.cfg.fatal.gsm_min_stage_kill
            )
        ) and (deriv is None or not deriv.is_fno_ban)
        if not gate_surveillance:
            rejection_reasons.append("Failed surveillance gate (ASM/GSM/F&O ban)")

        gate_mwpl = (
            deriv is None or deriv.mwpl_pct is None or deriv.mwpl_pct < self.cfg.card1.mwpl_max_pct
        )
        if not gate_mwpl:
            rejection_reasons.append(
                f"MWPL exceeded limit ({deriv.mwpl_pct if deriv else 0}% >= {self.cfg.card1.mwpl_max_pct}%)"
            )

        gate_circuit = price.circuit_band >= 5.0 and price.close_price < price.high_price * 1.0001
        if not gate_circuit:
            rejection_reasons.append("Circuit band constraint violated (<5% or locked at limit)")

        effective_adtv = (
            tech.adtv_20d if (tech and tech.adtv_20d is not None) else price.traded_value
        )
        gate_liquidity = effective_adtv >= self.cfg.card1.adtv_min_inr
        if not gate_liquidity:
            rejection_reasons.append(
                f"ADTV below minimum ({effective_adtv:,.0f} < {self.cfg.card1.adtv_min_inr:,.0f})"
            )

        gate_price = price.close_price >= self.cfg.card1.price_min
        if not gate_price:
            rejection_reasons.append(
                f"Price below minimum ({price.close_price} < {self.cfg.card1.price_min})"
            )

        gate_earnings = surv is None or surv.days_to_earnings > 5
        if not gate_earnings:
            rejection_reasons.append("Earnings or major event within 5 trading days")

        gate_gap = True
        if tech is not None and tech.atr_14 is not None and tech.atr_14 > 0:
            gap_size = abs(price.open_price - price.prev_close)
            if gap_size > self.cfg.card1.gap_atr_multiplier_max * tech.atr_14:
                gate_gap = False
                rejection_reasons.append(
                    f"Overnight gap ({gap_size:.2f}) exceeds {self.cfg.card1.gap_atr_multiplier_max}x ATR"
                )

        hard_gates_pass = (
            not is_bfsi
            and is_fno
            and gate_surveillance
            and gate_mwpl
            and gate_circuit
            and gate_liquidity
            and gate_price
            and gate_earnings
            and gate_gap
        )

        # Phase 2: Derivatives (5 Points Max)
        d_oi_buildup = False
        if deriv is not None:
            if deriv.prev_fno_oi and deriv.prev_fno_oi > 0:
                oi_pct = ((deriv.fno_oi - deriv.prev_fno_oi) / deriv.prev_fno_oi) * 100.0
                d_oi_buildup = oi_pct >= self.cfg.card1.oi_buildup_min_pct
            elif deriv.fno_oi_change > 0:
                d_oi_buildup = True

        d_coc = False
        if deriv is not None and deriv.cost_of_carry is not None and deriv.cost_of_carry > 0:
            coc_rising = (
                deriv.prev_cost_of_carry is None or deriv.cost_of_carry > deriv.prev_cost_of_carry
            )
            if self.cfg.card1.coc_requires_price_oi:
                price_up = price.close_price > price.prev_close
                oi_up = deriv.prev_fno_oi is None or deriv.fno_oi > deriv.prev_fno_oi
                d_coc = coc_rising and price_up and oi_up
            else:
                d_coc = coc_rising

        d_pcr = False
        if deriv is not None and deriv.pcr is not None:
            pcr_band_ok = self.cfg.card1.pcr_band[0] <= deriv.pcr <= self.cfg.card1.pcr_band[1]
            if self.cfg.card1.pcr_rising_required:
                pcr_rising = deriv.prev_pcr is None or deriv.pcr >= deriv.prev_pcr
                d_pcr = pcr_band_ok and pcr_rising
            else:
                d_pcr = pcr_band_ok

        d_delivery = (
            price.delivery_percentile_20d is not None
            and price.delivery_percentile_20d >= self.cfg.card1.delivery_value_percentile_min
        )

        d_inst_buy = deriv is not None and deriv.has_institutional_net_buy

        derivatives_score = sum([d_oi_buildup, d_coc, d_pcr, d_delivery, d_inst_buy])

        # Phase 3: Technicals (5 Points Max)
        t_avwap = False
        if tech is not None and tech.avwap_swing_low is not None:
            t_avwap = price.close_price > tech.avwap_swing_low
            if tech.avwap_earnings is not None:
                t_avwap = t_avwap and (price.close_price > tech.avwap_earnings)

        t_vpvr = tech is not None and tech.is_vpvr_breakout

        t_trend = False
        if (
            tech is not None
            and tech.ema_20 is not None
            and tech.ema_50 is not None
            and tech.sma_200 is not None
        ):
            t_trend = (tech.ema_20 > tech.ema_50 > tech.sma_200) and (
                price.close_price > tech.ema_20
            )

        t_mansfield = False
        if tech is not None and tech.mansfield_rs_500 is not None:
            rs_pos = tech.mansfield_rs_500 > 0
            rs_rising = (
                tech.prev_mansfield_rs_500 is None
                or tech.mansfield_rs_500 > tech.prev_mansfield_rs_500
            )
            t_mansfield = rs_pos and rs_rising

        t_atr_comp = tech is not None and tech.atr_compression

        technicals_score = sum([t_avwap, t_vpvr, t_trend, t_mansfield, t_atr_comp])

        total_score = float(derivatives_score + technicals_score)
        max_score = 10.0

        # Phase 4: Confirmations & Execution Rules
        # Active Confirmations Check (must satisfy >= 2 of 4)
        c1_rollover = (
            deriv is not None
            and deriv.rollover_pct is not None
            and deriv.avg_rollover_pct_20d is not None
            and deriv.rollover_pct > deriv.avg_rollover_pct_20d
        )
        c2_basis = (
            deriv is not None
            and deriv.basis_pct is not None
            and deriv.basis_pct > 0
            and (deriv.prev_basis_pct is None or deriv.basis_pct > deriv.prev_basis_pct)
        )
        c3_iv_skew = deriv is not None and deriv.iv_skew is not None and abs(deriv.iv_skew) < 3.0
        c4_max_pain = (
            deriv is not None
            and deriv.max_pain is not None
            and deriv.max_pain > (deriv.spot_price or price.close_price)
        )

        active_confirmations = {
            "rollover_pct_above_20d_avg": c1_rollover,
            "basis_pct_positive_and_rising": c2_basis,
            "iv_skew_under_3pct": c3_iv_skew,
            "max_pain_above_spot": c4_max_pain,
        }
        active_confirmations_count = sum(active_confirmations.values())
        active_confirmations_pass = (
            active_confirmations_count >= self.cfg.card1.active_confirmations_required
        )

        if not active_confirmations_pass:
            rejection_reasons.append(
                f"Active confirmations ({active_confirmations_count}) < required ({self.cfg.card1.active_confirmations_required})"
            )

        # Regime Gate Check
        regime_type = (
            regime.regime_classification if (regime and regime.regime_classification) else "NEUTRAL"
        )
        if regime_type == "RISK_OFF":
            required_score = float(self.cfg.card1.score_min_risk_off)
        elif regime_type == "RISK_ON":
            required_score = float(self.cfg.card1.score_min_risk_on)
        else:
            required_score = float(self.cfg.card1.score_min_neutral)

        regime_pass = total_score >= required_score
        if not regime_pass:
            rejection_reasons.append(
                f"Score {total_score:.1f} < regime required threshold {required_score:.1f} ({regime_type})"
            )

        # Trade Architecture
        arch: TradeArchitecture = compute_trade_architecture(
            high_price_today=price.high_price,
            avwap_swing_low=tech.avwap_swing_low if tech else None,
            fractal_swing_low_20d=tech.fractal_swing_low_20d if tech else None,
            vpvr_hvn_levels=tech.vpvr_hvn_levels if tech else None,
            swing_high_levels_250d=tech.swing_high_levels_250d if tech else None,
            portfolio_capital=float(self.cfg.portfolio_capital),
            current_low=price.low_price,
            min_rr=self.cfg.card1.rr_min,
        )

        if not arch.is_valid:
            rejection_reasons.append(f"Trade architecture invalid: {arch.rejection_reason}")

        # Delivery percentile hard rule check
        delivery_pass = (
            price.delivery_percentile_20d is not None
            and price.delivery_percentile_20d >= self.cfg.card1.delivery_value_percentile_min
        )
        if not delivery_pass:
            rejection_reasons.append("Delivery value percentile < 80th percentile")

        # Final Verdict
        can_execute = (
            hard_gates_pass
            and regime_pass
            and active_confirmations_pass
            and arch.is_valid
            and delivery_pass
        )

        verdict = "EXECUTE" if can_execute else "ABORT"
        valid_until = eval_date + timedelta(days=1)

        card_details: dict[str, Any] = {
            "hard_gates": {
                "surveillance_clean": gate_surveillance,
                "fno_mwpl_clear": gate_mwpl,
                "circuit_band_ok": gate_circuit,
                "liquidity_ok": gate_liquidity,
                "price_ok": gate_price,
                "event_clear": gate_earnings,
                "gap_ok": gate_gap,
            },
            "phase2_derivatives": {
                "oi_buildup": d_oi_buildup,
                "coc_positive_rising": d_coc,
                "pcr_optimal": d_pcr,
                "delivery_percentile_high": d_delivery,
                "institutional_net_buy": d_inst_buy,
                "subtotal": derivatives_score,
            },
            "phase3_technicals": {
                "avwap_confluence": t_avwap,
                "vpvr_breakout": t_vpvr,
                "trend_alignment": t_trend,
                "mansfield_rs_positive": t_mansfield,
                "atr_compression": t_atr_comp,
                "subtotal": technicals_score,
            },
            "active_confirmations": active_confirmations,
            "regime": {
                "classification": regime_type,
                "required_score": required_score,
                "passed": regime_pass,
            },
            "rejection_reasons": rejection_reasons,
            "architecture_metadata": arch.metadata,
        }

        return TradeCheckCardRow(
            id=card_id,
            symbol=symbol,
            desk_type="TACTICAL",
            eval_date=eval_date,
            hard_gates_pass=hard_gates_pass,
            score=total_score,
            max_score=max_score,
            verdict=verdict,
            entry_trigger=arch.entry_trigger if can_execute else None,
            stop_loss=arch.stop_loss if can_execute else None,
            target_1=arch.target_1 if can_execute else None,
            target_2=arch.target_2 if can_execute else None,
            risk_reward_ratio=arch.risk_reward_ratio if can_execute else None,
            position_size_shares=arch.position_size_shares if can_execute else None,
            valid_until=valid_until,
            card_details=card_details,
            sebi_disclosure_snapshot=None,
            restatement_caution=False,
        )

    def evaluate_from_db(self, symbol: str, eval_date: date) -> TradeCheckCardRow | None:
        """Fetches data from database and evaluates Card 1 for a symbol."""
        if not self.db:
            raise RuntimeError("Database client not configured in TacticalDesk")

        # 1. Check universe
        u_rows = self.db.select("universe", filters={"symbol": symbol}, limit=1)
        if not u_rows:
            return None
        u = u_rows[0]
        is_bfsi = bool(u.get("is_bfsi", False))
        is_fno = bool(u.get("is_fno", False))

        # 2. Daily price
        p_rows = self.db.select(
            "daily_prices", filters={"symbol": symbol, "trade_date": eval_date.isoformat()}, limit=1
        )
        if not p_rows:
            return None
        price = DailyPriceRow.model_validate(p_rows[0])

        # 3. Derivatives
        deriv: DerivativeMetricsRow | None = None
        d_rows = self.db.select(
            "derivative_metrics",
            filters={"symbol": symbol, "trade_date": eval_date.isoformat()},
            limit=1,
        )
        if d_rows:
            deriv = DerivativeMetricsRow.model_validate(d_rows[0])

        # 4. Technicals
        tech: TechnicalIndicatorsRow | None = None
        t_rows = self.db.select(
            "technical_indicators",
            filters={"symbol": symbol, "trade_date": eval_date.isoformat()},
            limit=1,
        )
        if t_rows:
            tech = TechnicalIndicatorsRow.model_validate(t_rows[0])

        # 5. Surveillance
        surv: SurveillanceRegistryRow | None = None
        s_rows = self.db.select(
            "surveillance_registry",
            filters={"symbol": symbol, "record_date": eval_date.isoformat()},
            limit=1,
        )
        if s_rows:
            surv = SurveillanceRegistryRow.model_validate(s_rows[0])

        # 6. Regime
        regime: MarketRegimeRow | None = None
        r_rows = self.db.select(
            "market_regime", filters={"trade_date": eval_date.isoformat()}, limit=1
        )
        if r_rows:
            regime = MarketRegimeRow.model_validate(r_rows[0])

        return self.evaluate(
            symbol=symbol,
            eval_date=eval_date,
            price=price,
            deriv=deriv,
            tech=tech,
            surv=surv,
            regime=regime,
            is_bfsi=is_bfsi,
            is_fno=is_fno,
        )
