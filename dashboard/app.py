"""Dalal Street Automation Engine v6.5 — Interactive Command Center."""

from __future__ import annotations

from typing import Any

import streamlit as st

from core.config import load_config
from core.database.client import DB
from dashboard.components.charts import create_regime_gauge

st.set_page_config(
    page_title="Dalal Street Engine v6.5",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_db_and_config() -> tuple[DB, Any]:
    cfg = load_config()
    db = DB.from_env()
    return db, cfg


def main() -> None:
    db, _cfg = get_db_and_config()

    # Sidebar
    st.sidebar.title("🏛️ Dalal Street v6.5")
    st.sidebar.caption("Quantitative & Forensic Decision Support")

    # DB Health Check
    try:
        db.select("universe", columns="symbol", limit=1)
        st.sidebar.success("🟢 Supabase Connected")
    except Exception as e:
        st.sidebar.error(f"🔴 DB Offline: {e}")

    st.title("🎯 Dalal Street Automation Engine — Command Center")
    st.markdown(
        "Institutional-grade quantitative swing trading and forensic fundamental decision-support engine."
    )

    # Top KPI Metrics Row
    try:
        uni_rows = db.select("universe", columns="symbol,is_fno,is_nifty500,is_bfsi")
        total_symbols = len(uni_rows)
        fno_count = sum(1 for u in uni_rows if u.get("is_fno"))
        n500_count = sum(1 for u in uni_rows if u.get("is_nifty500"))
        bfsi_count = sum(1 for u in uni_rows if u.get("is_bfsi"))
    except Exception:
        total_symbols, fno_count, n500_count, bfsi_count = 0, 0, 0, 0

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Universe Tracked", f"{total_symbols} stocks")
    kpi2.metric("Liquid F&O Names", f"{fno_count} contracts")
    kpi3.metric("Nifty 500 Core", f"{n500_count} companies")
    kpi4.metric("Non-BFSI Coverage", f"{total_symbols - bfsi_count} firms")

    st.markdown("---")

    # Macro Regime Snapshot
    col_regime, col_actions = st.columns([1, 1])

    with col_regime:
        st.subheader("🌐 Macro Market Regime")
        try:
            regime_rows = db.select("market_regime", order="trade_date.desc", limit=1)
            if regime_rows:
                r = regime_rows[0]
                vix = float(r.get("india_vix") or 15.0)
                classification = r.get("regime_classification") or "NEUTRAL"
                st.plotly_chart(
                    create_regime_gauge(vix, classification),
                    use_container_width=True,
                )
                st.caption(
                    f"Date: {r.get('trade_date')} | Nifty 500: ₹{r.get('nifty_500_close', 0):,.1f} | FII: ₹{r.get('fii_cash_net_cr', 0):+,.1f} Cr"
                )
            else:
                st.info("Market regime data pending initial calculation.")
        except Exception as e:
            st.warning(f"Could not load regime: {e}")

    with col_actions:
        st.subheader("🚀 Quick Decision Hub")
        st.markdown(
            """
        - **[Tactical Swing Board](./Tactical_Swing)**: Pre-flight checks for F&O momentum setups (Card 1: 0 to 10 pts).
        - **[Strategic Quality Board](./Strategic_Core)**: Multi-year forensic audit & moat scoring (Card 2: 0 to 50 pts).
        - **[Valuation Lab](./Valuation_Lab)**: Real-time Reverse DCF solver & growth sensitivity matrix.
        - **[Macro Cockpit](./Command_Center)**: Deep macro indicators, FII/DII flow, and system health.
        """
        )

        st.info(
            "⚖️ **SEBI RA Disclaimer**: This application is a decision-support quantitative model. Output cards do not constitute automated execution or guaranteed returns."
        )


if __name__ == "__main__":
    main()
