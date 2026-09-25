"""Digital Card 1 and Card 2 Streamlit UI widgets and HTML components."""

from __future__ import annotations

from typing import Any

import streamlit as st

from core.models import TradeCheckCardRow


def render_tactical_card(card: TradeCheckCardRow | dict[str, Any]) -> None:
    """Renders a visual Tactical Swing Check Card (Card 1) in Streamlit."""
    data = card.model_dump() if isinstance(card, TradeCheckCardRow) else card
    symbol = data.get("symbol", "UNKNOWN")
    eval_date = data.get("eval_date", "")
    verdict = data.get("verdict", "ABORT")
    score = float(data.get("score", 0.0))
    max_score = float(data.get("max_score", 10.0))
    details = data.get("card_details", {})

    is_execute = verdict == "EXECUTE"
    badge_color = "#10b981" if is_execute else "#ef4444"
    verdict_icon = "🚀" if is_execute else "⛔"

    st.markdown(
        f"""
        <div style="background-color: #1e293b; border-radius: 12px; border-left: 6px solid {badge_color}; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h2 style="margin: 0; color: #f8fafc; font-size: 24px;">{symbol} <span style="font-size: 16px; color: #94a3b8; font-weight: normal;">| Tactical Swing Card</span></h2>
                    <p style="margin: 4px 0 0 0; color: #64748b; font-size: 13px;">Date: {eval_date} | Valid Until: {data.get("valid_until", "Next Session")}</p>
                </div>
                <div style="text-align: right;">
                    <div style="background-color: {badge_color}22; border: 1px solid {badge_color}; color: {badge_color}; padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 14px; display: inline-block;">
                        {verdict_icon} {verdict}
                    </div>
                    <div style="color: #f8fafc; font-size: 20px; font-weight: bold; margin-top: 6px;">
                        {score:.1f} <span style="font-size: 13px; color: #64748b;">/ {max_score:.1f}</span>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("1. Pre-Flight Hard Gates")
        gates = details.get("gates", {})
        gate_items = [
            ("Surveillance (ASM/GSM Clean)", gates.get("surveillance", False)),
            ("F&O Eligible & MWPL < 82%", gates.get("fno_mwpl", False)),
            ("Circuit Band ≥ 5%", gates.get("circuit_band", False)),
            ("Liquidity (ADTV ≥ ₹15 Cr)", gates.get("liquidity", False)),
            ("Price ≥ ₹20", gates.get("price_min", False)),
            ("Earnings Buffer > 5 Days", gates.get("earnings_buffer", False)),
            ("Pre-Market Gap < 1.5 ATR", gates.get("gap_atr", False)),
        ]
        for name, passed in gate_items:
            icon = "✅" if passed else "❌"
            color = "#10b981" if passed else "#ef4444"
            st.markdown(
                f"<span style='color:{color}; font-weight: 500;'>{icon} {name}</span>",
                unsafe_allow_html=True,
            )

        st.subheader("2. Active Confirmations")
        confirms = details.get("active_confirmations", [])
        if confirms:
            for c in confirms:
                st.markdown(f"⚡ **{c}**")
        else:
            st.caption("No active confirmations triggered.")

    with col2:
        st.subheader("3. Trade Architecture")
        if is_execute and data.get("entry_trigger"):
            st.metric("Entry Trigger", f"₹{data.get('entry_trigger', 0):.2f}")
            c_a, c_b = st.columns(2)
            with c_a:
                st.metric("Stop Loss", f"₹{data.get('stop_loss', 0):.2f}")
                st.metric("Risk-Reward", f"{data.get('risk_reward_ratio', 0):.2f}R")
            with c_b:
                st.metric("Target 1 (HVN)", f"₹{data.get('target_1', 0):.2f}")
                st.metric(
                    "Position Size",
                    f"{data.get('position_size_shares', 0):,} shs",
                )
            if data.get("target_2"):
                st.caption(f"Runner Target 2: ₹{data.get('target_2', 0):.2f}")
        else:
            st.warning("⛔ Execution blocked. Trade architecture suppressed.")

    with st.expander("Detailed Score Components (Derivatives & Technicals)"):
        d_col, t_col = st.columns(2)
        with d_col:
            st.markdown("**Derivatives Points (Max 5):**")
            d_scores = details.get("derivatives_score", {})
            st.json(d_scores)
        with t_col:
            st.markdown("**Technicals Points (Max 5):**")
            t_scores = details.get("technicals_score", {})
            st.json(t_scores)


def render_strategic_card(card: TradeCheckCardRow | dict[str, Any]) -> None:
    """Renders a visual Strategic Core Check Card (Card 2) in Streamlit."""
    data = card.model_dump() if isinstance(card, TradeCheckCardRow) else card
    symbol = data.get("symbol", "UNKNOWN")
    eval_date = data.get("eval_date", "")
    verdict = data.get("verdict", "REJECT")
    score = float(data.get("score", 0.0))
    max_score = float(data.get("max_score", 50.0))
    details = data.get("card_details", {})

    if verdict == "TIER_1":
        badge_color = "#38bdf8"
        icon = "💎"
    elif verdict == "TIER_2":
        badge_color = "#f59e0b"
        icon = "⭐"
    else:
        badge_color = "#ef4444"
        icon = "🚫"

    st.markdown(
        f"""
        <div style="background-color: #1e293b; border-radius: 12px; border-left: 6px solid {badge_color}; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h2 style="margin: 0; color: #f8fafc; font-size: 24px;">{symbol} <span style="font-size: 16px; color: #94a3b8; font-weight: normal;">| Strategic Core Card</span></h2>
                    <p style="margin: 4px 0 0 0; color: #64748b; font-size: 13px;">Date: {eval_date} | Restatement Caution: {"YES" if data.get("restatement_caution") else "NO"}</p>
                </div>
                <div style="text-align: right;">
                    <div style="background-color: {badge_color}22; border: 1px solid {badge_color}; color: {badge_color}; padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 14px; display: inline-block;">
                        {icon} {verdict}
                    </div>
                    <div style="color: #f8fafc; font-size: 20px; font-weight: bold; margin-top: 6px;">
                        {score:.1f} <span style="font-size: 13px; color: #64748b;">/ {max_score:.1f}</span>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    m1, m2, m3 = st.columns(3)
    moat = details.get("moat_score", {})
    sector = details.get("sector_score", {})
    val = details.get("valuation_score", {})

    with m1:
        st.metric("Moat & Capital Allocation", f"{moat.get('total', 0)} / 25 pts")
    with m2:
        st.metric("Sectoral Operational Drill", f"{sector.get('total', 0)} / 15 pts")
    with m3:
        st.metric("Valuation & Margin of Safety", f"{val.get('total', 0)} / 10 pts")

    with st.expander("17 Forensic Hard Gates Matrix", expanded=True):
        f_gates = details.get("forensic_gates", {})
        if f_gates:
            cols = st.columns(3)
            for idx, (gate_name, passed) in enumerate(f_gates.items()):
                c = cols[idx % 3]
                icon = "✅" if passed else "❌"
                color = "#10b981" if passed else "#ef4444"
                c.markdown(
                    f"<span style='color:{color}; font-size: 13px;'>{icon} {gate_name}</span>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("Forensic gates data not populated.")

    st.info(
        "🔒 **Execution Fields are strictly NULL**: Strategic Card 2 does not generate automated execution tickets. Fundamental core positions are managed discretionarily."
    )
