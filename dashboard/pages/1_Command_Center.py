"""Command Center: Macro Cockpit, Universe Browser, and Pipeline Health."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.database.client import DB

st.set_page_config(page_title="Macro Cockpit & Universe", page_icon="🌐", layout="wide")


@st.cache_resource
def get_db():
    return DB.from_env()


db = get_db()

st.title("🌐 Command Center: Macro Cockpit & Universe Telemetry")

tab_macro, tab_universe, tab_pipeline = st.tabs(
    ["Macro Cockpit", "Universe Browser", "Pipeline Telemetry"]
)

with tab_macro:
    st.subheader("Dalal Street Macro Regime Trends")
    try:
        regime_rows = db.select("market_regime", order="trade_date.desc", limit=30)
        if regime_rows:
            df_regime = pd.DataFrame(regime_rows)
            c1, c2, c3 = st.columns(3)
            latest = regime_rows[0]
            c1.metric("India VIX", f"{latest.get('india_vix') or 'N/A'}")
            c2.metric(
                "FII Cash Net",
                f"₹{latest.get('fii_cash_net_cr') or 0:+,.1f} Cr"
                if latest.get("fii_cash_net_cr")
                else "N/A",
            )
            c3.metric(
                "DII Cash Net",
                f"₹{latest.get('dii_cash_net_cr') or 0:+,.1f} Cr"
                if latest.get("dii_cash_net_cr")
                else "N/A",
            )

            st.dataframe(
                df_regime[
                    [
                        "trade_date",
                        "india_vix",
                        "nifty_500_close",
                        "fii_cash_net_cr",
                        "dii_cash_net_cr",
                        "gsec_10y_yield",
                        "regime_classification",
                    ]
                ],
                use_container_width=True,
            )
        else:
            st.info("No regime data available.")
    except Exception as e:
        st.error(f"Error fetching regime data: {e}")

with tab_universe:
    st.subheader("Tracked Universe Directory")
    try:
        uni_rows = db.select(
            "universe",
            columns="symbol,company_name,sector,industry,is_fno,is_nifty500,is_bfsi",
            order="symbol.asc",
            limit=1000,
        )
        if uni_rows:
            df_uni = pd.DataFrame(uni_rows)
            sector_filter = st.multiselect(
                "Filter by Sector",
                options=sorted(df_uni["sector"].dropna().unique().tolist()),
            )
            fno_only = st.checkbox("F&O Stocks Only", value=False)

            filtered = df_uni
            if sector_filter:
                filtered = filtered[filtered["sector"].isin(sector_filter)]
            if fno_only:
                filtered = filtered[filtered["is_fno"]]

            st.dataframe(filtered, use_container_width=True)
            st.caption(f"Showing {len(filtered)} of {len(df_uni)} stocks.")
    except Exception as e:
        st.error(f"Error fetching universe: {e}")

with tab_pipeline:
    st.subheader("Automated Pipeline Execution Health")
    try:
        health_rows = db.select("pipeline_health", order="started_at.desc", limit=20)
        if health_rows:
            df_h = pd.DataFrame(health_rows)
            st.dataframe(
                df_h[
                    [
                        "run_id",
                        "workflow",
                        "status",
                        "started_at",
                        "duration_seconds",
                        "rows_processed",
                        "error_message",
                    ]
                ],
                use_container_width=True,
            )
        else:
            st.info("No pipeline health logs recorded.")
    except Exception as e:
        st.error(f"Error fetching pipeline health: {e}")
