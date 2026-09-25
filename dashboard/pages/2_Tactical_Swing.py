"""Tactical Swing Board: Pre-Flight Card 1 Live Inspector."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from core.config import load_config
from core.database.client import DB
from core.engines.tactical_desk import TacticalDesk
from dashboard.components.card_renderers import render_tactical_card
from dashboard.components.charts import create_candlestick_chart

st.set_page_config(page_title="Tactical Swing Board", page_icon="🎯", layout="wide")


@st.cache_resource
def get_db_and_config():
    return DB.from_env(), load_config()


db, cfg = get_db_and_config()

st.title("🎯 Tactical Swing Board (Card 1 Live Inspector)")
st.caption(
    "Pre-flight trade checks for liquid F&O equities. Enforces 7 hard gates, derivatives scoring, technical alignment, and trade architecture."
)

col_ctrl, col_main = st.columns([1, 3])

with col_ctrl:
    st.subheader("Controls")
    eval_date = st.date_input("Evaluation Date", value=date.today())

    # Get available F&O non-BFSI symbols
    fno_rows = db.select(
        "universe",
        columns="symbol",
        filters={"is_fno": True, "is_bfsi": False},
        order="symbol.asc",
        limit=200,
    )
    symbol_options = [r["symbol"] for r in fno_rows if r.get("symbol")]

    selected_symbol = st.selectbox(
        "Select Stock Symbol",
        options=symbol_options or ["TCS", "INFY", "RELIANCE"],
    )

    evaluate_btn = st.button("Run Real-Time Pre-Flight Check", type="primary")

with col_main:
    # Check if a card already exists in database
    card_data: dict[str, Any] | None = None
    if selected_symbol:
        existing = db.select(
            "trade_check_cards",
            filters={
                "symbol": selected_symbol,
                "desk_type": "TACTICAL",
                "eval_date": str(eval_date),
            },
            limit=1,
        )
        if existing:
            card_data = existing[0]

    if evaluate_btn or card_data:
        if evaluate_btn:
            with st.spinner(f"Evaluating Tactical Desk for {selected_symbol}..."):
                desk = TacticalDesk(db, cfg)
                card_row = desk.evaluate_from_db(selected_symbol, eval_date)
                if card_row:
                    card_data = card_row.model_dump()
                else:
                    st.error(
                        f"Could not compute Tactical Card for {selected_symbol} on {eval_date} (missing price/derivatives data)."
                    )

        if card_data:
            render_tactical_card(card_data)

            # Price Action Candlestick Chart
            prices = db.select(
                "daily_prices",
                columns="trade_date,open_price,high_price,low_price,close_price,volume",
                filters={"symbol": selected_symbol},
                order="trade_date.asc",
                limit=65,
            )
            if prices:
                df_p = pd.DataFrame(prices)
                df_p["trade_date"] = pd.to_datetime(df_p["trade_date"])
                fig = create_candlestick_chart(
                    df_p,
                    avwap_swing_low=card_data.get("stop_loss"),
                    symbol=selected_symbol,
                )
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(
            f"Select a symbol and click **Run Real-Time Pre-Flight Check** to generate Card 1 for {selected_symbol}."
        )
