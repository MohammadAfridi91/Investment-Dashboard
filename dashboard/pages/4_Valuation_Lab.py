"""Valuation Lab: Reverse DCF & Growth Headroom Simulator."""

from __future__ import annotations

import streamlit as st

from core.config import load_config
from core.database.client import DB
from dashboard.components.dcf_simulator import render_dcf_simulator

st.set_page_config(page_title="Valuation Lab", page_icon="🧮", layout="wide")


@st.cache_resource
def get_db_and_config():
    return DB.from_env(), load_config()


db, cfg = get_db_and_config()

st.title("🧮 Valuation Lab: Reverse DCF Sensitivity Model")
st.caption(
    "Dissect the market-implied growth expectations embedded in current valuations and compare against sectoral TAM headroom."
)

col_search, _ = st.columns([1, 1])

# Preset from database if available
preset_fcf = 2500.0
preset_ev = 50000.0
preset_sector_tam = 0.14

with col_search:
    uni_rows = db.select(
        "universe",
        columns="symbol,sector",
        filters={"is_bfsi": False},
        order="symbol.asc",
        limit=200,
    )
    sym_list = [u["symbol"] for u in uni_rows if u.get("symbol")]
    selected_sym = st.selectbox(
        "Load Company Financials (Optional)",
        options=["(Custom / Manual)", *sym_list],
    )

    if selected_sym != "(Custom / Manual)":
        fin_rows = db.select(
            "forensic_financials",
            columns="fcf,enterprise_value,sector",
            filters={"symbol": selected_sym},
            order="fiscal_year.desc",
            limit=1,
        )
        if fin_rows:
            f = fin_rows[0]
            if f.get("fcf") and f.get("fcf") > 0:
                preset_fcf = float(f["fcf"])
            if f.get("enterprise_value") and f.get("enterprise_value") > 0:
                preset_ev = float(f["enterprise_value"])
            sec = f.get("sector", "")
            preset_sector_tam = cfg.sector_tam_growth.get(sec, 0.14)
            st.success(
                f"Loaded {selected_sym} financials: Base FCF ₹{preset_fcf:,.1f} Cr | EV ₹{preset_ev:,.1f} Cr | TAM {preset_sector_tam * 100:.1f}%"
            )

render_dcf_simulator(
    default_fcf=preset_fcf,
    default_ev=preset_ev,
    default_wacc=0.11,
    default_terminal_g=0.05,
    sector_tam_growth=preset_sector_tam,
)
