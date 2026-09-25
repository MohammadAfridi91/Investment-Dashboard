"""Visual ASCII and Markdown formatters for Card 1, Card 2, and Market Regime."""

from __future__ import annotations

from typing import Any

from core.models import MarketRegimeRow, TradeCheckCardRow


def _status_icon(val: bool | None) -> str:
    if val is True:
        return "✅"
    if val is False:
        return "❌"
    return "⚪"


def format_card1_markdown(card: TradeCheckCardRow) -> str:
    """Renders a Card 1 Tactical Swing pre-flight check card in GitHub/Telegram Markdown."""
    details: dict[str, Any] = card.card_details or {}
    gates: dict[str, Any] = details.get("gates", {})
    derivs: dict[str, Any] = details.get("derivatives_score", {})
    techs: dict[str, Any] = details.get("technicals_score", {})
    active_conf: list[str] = details.get("active_confirmations", [])

    status_badge = "🟢 **EXECUTE**" if card.verdict == "EXECUTE" else "🔴 **ABORT**"
    gates_badge = "PASS" if card.hard_gates_pass else "FAIL"

    lines = [
        f"### 🎯 TACTICAL SWING CARD (CARD 1) — {card.symbol}",
        f"**Date:** `{card.eval_date}` | **Verdict:** {status_badge} | **Score:** `{card.score:.1f}/{card.max_score:.1f}`",
        f"**Hard Gates:** `{gates_badge}` | **Valid Until:** `{card.valid_until}`",
        "",
        "#### 1. Hard Pre-Flight Gates",
        f"- Surveillance (ASM/GSM): {_status_icon(gates.get('surveillance'))} `{'PASS' if gates.get('surveillance') else 'FAIL'}`",
        f"- F&O Eligibility & MWPL (<82%): {_status_icon(gates.get('fno_mwpl'))} `{'PASS' if gates.get('fno_mwpl') else 'FAIL'}`",
        f"- Circuit Band (≥5%): {_status_icon(gates.get('circuit_band'))} `{'PASS' if gates.get('circuit_band') else 'FAIL'}`",
        f"- Liquidity (ADTV ≥ ₹15 Cr): {_status_icon(gates.get('liquidity'))} `{'PASS' if gates.get('liquidity') else 'FAIL'}`",
        f"- Price Threshold (≥ ₹20): {_status_icon(gates.get('price_min'))} `{'PASS' if gates.get('price_min') else 'FAIL'}`",
        f"- Earnings Buffer (>5 Days): {_status_icon(gates.get('earnings_buffer'))} `{'PASS' if gates.get('earnings_buffer') else 'FAIL'}`",
        f"- Pre-Market Gap (<1.5 ATR): {_status_icon(gates.get('gap_atr'))} `{'PASS' if gates.get('gap_atr') else 'FAIL'}`",
        "",
        "#### 2. Signal Breakdown",
        f"**Derivatives Component ({derivs.get('total', 0)}/5 pts):**",
        f"- OI Buildup (≥5%): {_status_icon(derivs.get('oi_buildup', False))} ({derivs.get('oi_buildup_pts', 0)} pt)",
        f"- Cost of Carry (Positive & Rising): {_status_icon(derivs.get('coc_rising', False))} ({derivs.get('coc_rising_pts', 0)} pt)",
        f"- PCR (0.60-1.25 & Rising): {_status_icon(derivs.get('pcr_bullish', False))} ({derivs.get('pcr_bullish_pts', 0)} pt)",
        f"- Delivery Percentile (≥80th): {_status_icon(derivs.get('delivery_volume_pctile', False))} ({derivs.get('delivery_volume_pts', 0)} pt)",
        f"- Institutional Net Buy: {_status_icon(derivs.get('institutional_flow', False))} ({derivs.get('institutional_flow_pts', 0)} pt)",
        "",
        f"**Technicals Component ({techs.get('total', 0)}/5 pts):**",
        f"- AVWAP Swing Low Support: {_status_icon(techs.get('avwap_support', False))} ({techs.get('avwap_support_pts', 0)} pt)",
        f"- VPVR High Volume Node Breakout: {_status_icon(techs.get('vpvr_breakout', False))} ({techs.get('vpvr_breakout_pts', 0)} pt)",
        f"- Trend Alignment (EMA20 > EMA50 > SMA200): {_status_icon(techs.get('trend_alignment', False))} ({techs.get('trend_alignment_pts', 0)} pt)",
        f"- Mansfield RS vs NIFTY 500 (Positive & Rising): {_status_icon(techs.get('mansfield_rs_rising', False))} ({techs.get('mansfield_rs_pts', 0)} pt)",
        f"- ATR Volatility Compression: {_status_icon(techs.get('atr_compression', False))} ({techs.get('atr_compression_pts', 0)} pt)",
        "",
        f"#### 3. Active Confirmations ({len(active_conf)}/4 active)",
    ]

    if active_conf:
        for conf in active_conf:
            lines.append(f"- ⚡ `{conf}`")
    else:
        lines.append("- *(No active confirmations satisfied)*")

    lines.append("")
    lines.append("#### 4. Trade Execution Architecture")
    if card.verdict == "EXECUTE" and card.entry_trigger:
        lines.extend(
            [
                f"- **Entry Trigger:** `₹{card.entry_trigger:.2f}`",
                f"- **Stop Loss:** `₹{card.stop_loss:.2f}`"
                if card.stop_loss
                else "- **Stop Loss:** N/A",
                f"- **Target 1 (Primary):** `₹{card.target_1:.2f}`"
                if card.target_1
                else "- **Target 1:** N/A",
                f"- **Target 2 (Runner):** `₹{card.target_2:.2f}`"
                if card.target_2
                else "- **Target 2:** N/A",
                f"- **Risk-to-Reward Ratio:** `{card.risk_reward_ratio:.2f}R`"
                if card.risk_reward_ratio
                else "- **Risk-to-Reward:** N/A",
                f"- **Recommended Position Size:** `{card.position_size_shares or 0:,} shares`",
            ]
        )
    else:
        lines.append("⛔ *Execution blocked or aborted. Order architecture suppressed.*")

    lines.extend(
        [
            "",
            "---",
            "⚖️ *SEBI RA Regulation: Decision-support tool only. Quantitative rules engine output without guaranteed returns.*",
        ]
    )
    return "\n".join(lines)


def format_card1_ascii(card: TradeCheckCardRow) -> str:
    """Renders a Card 1 Tactical Swing check card in ASCII box art."""
    details: dict[str, Any] = card.card_details or {}
    verdict_str = f"[{card.verdict}]"
    score_str = f"{card.score:.1f}/{card.max_score:.1f}"

    lines = [
        "┌─────────────────────────────────────────────────────────────┐",
        "│ DALAL STREET ENGINE v6.5 — TACTICAL SWING CARD (CARD 1)     │",
        "├─────────────────────────────────────────────────────────────┤",
        f"│ Symbol: {card.symbol:<12} Date: {card.eval_date!s:<12} Score: {score_str:<12} │",
        f"│ Verdict: {verdict_str:<11} Hard Gates: {'PASS' if card.hard_gates_pass else 'FAIL':<8} Valid: {card.valid_until!s:<12} │",
        "├─────────────────────────────────────────────────────────────┤",
        "│ TRADE EXECUTION ARCHITECTURE:                               │",
    ]

    if card.verdict == "EXECUTE" and card.entry_trigger:
        lines.extend(
            [
                f"│   • Entry Trigger  : ₹{card.entry_trigger:<39.2f}│",
                f"│   • Stop Loss      : ₹{(card.stop_loss or 0.0):<39.2f}│",
                f"│   • Target 1 (HVN) : ₹{(card.target_1 or 0.0):<39.2f}│",
                f"│   • Target 2 (Res) : ₹{(card.target_2 or 0.0):<39.2f}│",
                f"│   • Risk/Reward    : {str(card.risk_reward_ratio) + 'R':<41}│",
                f"│   • Position Sizing: {str(card.position_size_shares or 0) + ' shares':<41}│",
            ]
        )
    else:
        reason = details.get("fail_reason", "EXECUTION_ABORTED")
        lines.append(f"│   • STATUS: BLOCKED ({reason[:35]:<35})│")

    lines.extend(
        [
            "├─────────────────────────────────────────────────────────────┤",
            "│ DISCLAIMER: SEBI RA personal tool. Zero guaranteed returns. │",
            "└─────────────────────────────────────────────────────────────┘",
        ]
    )
    return "\n".join(lines)


def format_card2_markdown(card: TradeCheckCardRow) -> str:
    """Renders a Card 2 Strategic Core pre-flight card in Markdown."""
    details: dict[str, Any] = card.card_details or {}
    gates: dict[str, Any] = details.get("forensic_gates", {})
    moat: dict[str, Any] = details.get("moat_score", {})
    sector: dict[str, Any] = details.get("sector_score", {})
    val: dict[str, Any] = details.get("valuation_score", {})

    status_badge = (
        "💎 **TIER 1 (ELITE)**"
        if card.verdict == "TIER_1"
        else ("⭐ **TIER 2 (CORE)**" if card.verdict == "TIER_2" else "🚫 **REJECT**")
    )
    gates_badge = "ALL PASS" if card.hard_gates_pass else "VIOLATION DETECTED"

    lines = [
        f"### 🏛️ STRATEGIC CORE QUALITY CARD (CARD 2) — {card.symbol}",
        f"**Date:** `{card.eval_date}` | **Verdict:** {status_badge} | **Score:** `{card.score:.1f}/{card.max_score:.1f}`",
        f"**Forensic Integrity:** `{gates_badge}` | **Restatement Caution:** `{'YES' if card.restatement_caution else 'NO'}`",
        "",
        "#### 1. Forensic Integrity Hard Gates (17 Gates)",
        f"- Beneish M-Score (< -2.22): {_status_icon(gates.get('beneish_m_score'))}",
        f"- 5-Yr Cumulative CFO/EBITDA (≥75%): {_status_icon(gates.get('cfo_realization'))}",
        f"- Auditor Independence (Tier-1, No Resignation 3Y): {_status_icon(gates.get('auditor_independent'))}",
        f"- CARO Audit Cleanliness (No Adverse Notes 3Y): {_status_icon(gates.get('caro_clean'))}",
        f"- CWIP / Gross Block (<30%): {_status_icon(gates.get('cwip_ok'))}",
        f"- Contingent Liabilities / Net Worth (<15%): {_status_icon(gates.get('obs_ok'))}",
        f"- Related Party Transactions Cleanliness: {_status_icon(gates.get('rpt_clean'))}",
        f"- Promoter Pledge (<5% & Not Rising): {_status_icon(gates.get('pledge_clean'))}",
        f"- Altman Z'' Distress Score (>2.60): {_status_icon(gates.get('altman_z'))}",
        f"- Piotroski F-Score (≥7/9): {_status_icon(gates.get('piotroski_f'))}",
        f"- Sloan Accrual Anomaly (<0.08): {_status_icon(gates.get('sloan_accrual'))}",
        f"- Interest Coverage Ratio (≥4.0x): {_status_icon(gates.get('interest_coverage'))}",
        f"- Debt Service Coverage Ratio (≥1.5x): {_status_icon(gates.get('dscr'))}",
        "",
        "#### 2. Multi-Dimensional Quality Scoring",
        f"**Moat Durability & Capital Allocation ({moat.get('total', 0)}/25 pts):**",
        f"- ROIC vs WACC Spread (≥5%): {_status_icon(moat.get('roic_spread', False))} ({moat.get('roic_spread_pts', 0)} pts)",
        f"- Incremental ROIC (ROIIC ≥20%): {_status_icon(moat.get('roiic', False))} ({moat.get('roiic_pts', 0)} pts)",
        f"- Free Cash Flow Consistency (≥4/5 Yrs Positive): {_status_icon(moat.get('fcf_consistency', False))} ({moat.get('fcf_consistency_pts', 0)} pts)",
        f"- Gross Margin Stability: {_status_icon(moat.get('margin_power', False))} ({moat.get('margin_power_pts', 0)} pts)",
        f"- Deleveraging / Conservative Debt (ND/EBITDA <1.0): {_status_icon(moat.get('deleverage', False))} ({moat.get('deleverage_pts', 0)} pts)",
        "",
        f"**Sectoral Operational Velocity ({sector.get('total', 0)}/15 pts):**",
        f"- Working Capital Cycle Discipline: {_status_icon(sector.get('wc_discipline', False))} ({sector.get('wc_discipline_pts', 0)} pts)",
        f"- Fixed Asset Turnover Velocity: {_status_icon(sector.get('asset_velocity', False))} ({sector.get('asset_velocity_pts', 0)} pts)",
        f"- Capacity Utilization Proxy: {_status_icon(sector.get('capacity', False))} ({sector.get('capacity_pts', 0)} pts)",
        "",
        f"**Valuation & Margin of Safety ({val.get('total', 0)}/10 pts):**",
        f"- Reverse DCF Reality Check (Implied Growth ≤ TAM): {_status_icon(val.get('dcf_reality', False))} ({val.get('dcf_reality_pts', 0)} pts)",
        f"- Free Cash Flow Yield vs G-Sec Yield: {_status_icon(val.get('fcf_yield', False))} ({val.get('fcf_yield_pts', 0)} pts)",
        "",
        "#### 3. Execution Mandate",
        "🔒 *Execution fields are strictly NULL for Strategic Card 2 by design (Section 19 Acceptance Test 10 compliance).* Long-term allocation decisions require discretionary fundamental review.",
        "",
        "---",
        "⚖️ *SEBI RA Regulation: Research analysis scorecard. No investment advice or guaranteed outcome.*",
    ]
    return "\n".join(lines)


def format_card2_ascii(card: TradeCheckCardRow) -> str:
    """Renders a Card 2 Strategic Core check card in ASCII box art."""
    score_str = f"{card.score:.1f}/{card.max_score:.1f}"

    lines = [
        "┌─────────────────────────────────────────────────────────────┐",
        "│ DALAL STREET ENGINE v6.5 — STRATEGIC CORE CARD (CARD 2)     │",
        "├─────────────────────────────────────────────────────────────┤",
        f"│ Symbol: {card.symbol:<12} Date: {card.eval_date!s:<12} Score: {score_str:<12} │",
        f"│ Verdict: {card.verdict:<11} Forensic: {'PASS' if card.hard_gates_pass else 'FAIL':<10} Caution: {'YES' if card.restatement_caution else 'NO':<10} │",
        "├─────────────────────────────────────────────────────────────┤",
        "│ QUALITY TIERS BREAKDOWN:                                    │",
        f"│   • Moat Durability     : {card.card_details.get('moat_score', {}).get('total', 0):<2} / 25 pts                          │",
        f"│   • Sector Drill-Down   : {card.card_details.get('sector_score', {}).get('total', 0):<2} / 15 pts                          │",
        f"│   • Valuation & Margin  : {card.card_details.get('valuation_score', {}).get('total', 0):<2} / 10 pts                          │",
        "├─────────────────────────────────────────────────────────────┤",
        "│ MANDATE: Strict Fundamental Core (Execution Fields = None)  │",
        "│ DISCLAIMER: SEBI RA personal tool. Zero guaranteed returns. │",
        "└─────────────────────────────────────────────────────────────┘",
    ]
    return "\n".join(lines)


def format_regime_markdown(regime: MarketRegimeRow) -> str:
    """Renders a Market Regime macro cockpit summary in Markdown."""
    vix = f"{regime.india_vix:.2f}" if regime.india_vix is not None else "N/A"
    nifty = f"{regime.nifty_500_close:,.1f}" if regime.nifty_500_close is not None else "N/A"
    fii = f"₹{regime.fii_cash_net_cr:+,.1f} Cr" if regime.fii_cash_net_cr is not None else "N/A"
    dii = f"₹{regime.dii_cash_net_cr:+,.1f} Cr" if regime.dii_cash_net_cr is not None else "N/A"
    gsec = f"{regime.gsec_10y_yield * 100:.2f}%" if regime.gsec_10y_yield is not None else "N/A"
    classification = regime.regime_classification or "PENDING_HISTORY"

    badge = (
        "🟢 **RISK_ON**"
        if classification == "RISK_ON"
        else ("🔴 **RISK_OFF**" if classification == "RISK_OFF" else "🟡 **NEUTRAL**")
    )

    lines = [
        f"### 🌐 DALAL STREET MACRO COCKPIT — {regime.trade_date}",
        f"**Overall Market Regime:** {badge}",
        "",
        "| Macro Metric | Current Value | Threshold Benchmark |",
        "| :--- | :--- | :--- |",
        f"| **India VIX** | `{vix}` | <14.0 (Risk On) / >22.0 (Risk Off) |",
        f"| **NIFTY 500 Close** | `{nifty}` | Above 50/200 SMAs |",
        f"| **FII Net Cash** | `{fii}` | Institutional liquidity driver |",
        f"| **DII Net Cash** | `{dii}` | Domestic support absorption |",
        f"| **10Y G-Sec Yield** | `{gsec}` | Risk-free hurdle benchmark |",
        "",
        "---",
        "⚡ *Engine gates Card 1 trades if Regime == RISK_OFF (threshold score 99 required).* ",
    ]
    return "\n".join(lines)
