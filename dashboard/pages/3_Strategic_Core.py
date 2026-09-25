"""Strategic Core Board: Pre-Flight Card 2 Forensic Scorecard."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from core.config import load_config
from core.database.client import DB
from core.engines.strategic_desk import StrategicDesk
from dashboard.components.card_renderers import render_strategic_card

st.set_page_config(page_title="Strategic Core Board", page_icon="🏛️", layout="wide")


@st.cache_resource
def get_db_and_config():
    return DB.from_env(), load_config()


db, cfg = get_db_and_config()

st.title("🏛️ Strategic Core Board (Card 2 Forensic Scorecard)")
st.caption(
    "Long-term compounder quality evaluation across 17 forensic gates, Moat durability, Sectoral velocity, and Reverse DCF valuation margins."
)

col_ctrl, col_main = st.columns([1, 3])

with col_ctrl:
    st.subheader("Controls")
    eval_date = st.date_input("Evaluation Date", value=date.today())

    # Get available Nifty 500 non-BFSI symbols
    strat_rows = db.select(
        "universe",
        columns="symbol",
        filters={"is_nifty500": True, "is_bfsi": False},
        order="symbol.asc",
        limit=400,
    )
    symbol_options = [r["symbol"] for r in strat_rows if r.get("symbol")]

    selected_symbol = st.selectbox(
        "Select Stock Symbol",
        options=symbol_options or ["TCS", "INFY", "LT", "HINDUNILVR"],
    )

    evaluate_btn = st.button("Run Forensic Quality Audit", type="primary")

with col_main:
    card_data: dict[str, Any] | None = None

    if selected_symbol:
        existing = db.select(
            "trade_check_cards",
            filters={
                "symbol": selected_symbol,
                "desk_type": "STRATEGIC",
                "eval_date": str(eval_date),
            },
            limit=1,
        )
        if existing:
            card_data = existing[0]

    if evaluate_btn or card_data:
        if evaluate_btn:
            with st.spinner(f"Evaluating Strategic Desk for {selected_symbol}..."):
                desk = StrategicDesk(db, cfg)
                card_row = desk.evaluate_from_db(selected_symbol, eval_date)
                if card_row:
                    card_data = card_row.model_dump()
                else:
                    st.error(
                        f"Could not compute Strategic Card for {selected_symbol} on {eval_date} (missing audited financials)."
                    )

        if card_data:
            render_strategic_card(card_data)

            # Historical Financials Table
            st.subheader(f"Audited Multi-Year Financials — {selected_symbol}")
            fin_rows = db.select(
                "forensic_financials",
                columns="fiscal_year,sales,ebitda,net_profit,cfo,fcf,gross_block,cwip,roce,altman_z_double_prime,beneish_m_score,piotroski_f_score,sloan_accrual",
                filters={"symbol": selected_symbol},
                order="fiscal_year.desc",
                limit=10,
            )
            if fin_rows:
                df_fin = pd.DataFrame(fin_rows)
                st.dataframe(df_fin, use_container_width=True)
            else:
                st.info(f"No multi-year financials found for {selected_symbol}.")
    else:
        st.info(
            f"Select a symbol and click **Run Forensic Quality Audit** to generate Card 2 for {selected_symbol}."
        )
