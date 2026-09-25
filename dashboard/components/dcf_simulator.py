"""Interactive Reverse DCF real-time slider simulator component."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from core.indicators.dcf_solver import solve_implied_dcf_growth


def render_dcf_simulator(
    default_fcf: float = 2500.0,
    default_ev: float = 50000.0,
    default_wacc: float = 0.11,
    default_terminal_g: float = 0.05,
    sector_tam_growth: float = 0.14,
) -> None:
    """Renders a real-time Reverse DCF sensitivity and implied growth simulator."""
    st.markdown("### 🧮 Reverse DCF Sensitivity & Implied Growth Simulator")
    st.caption(
        "Solves for the implied 10-year Free Cash Flow growth rate embedded in the current valuation."
    )

    col1, col2 = st.columns([1, 1])

    with col1:
        fcf = st.number_input(
            "Base Free Cash Flow (₹ Cr)",
            min_value=1.0,
            max_value=100000.0,
            value=float(default_fcf),
            step=100.0,
        )
        ev = st.number_input(
            "Current Enterprise Value (₹ Cr)",
            min_value=10.0,
            max_value=2000000.0,
            value=float(default_ev),
            step=500.0,
        )
        wacc = (
            st.slider(
                "Discount Rate / WACC (%)",
                min_value=7.0,
                max_value=18.0,
                value=float(default_wacc * 100),
                step=0.25,
            )
            / 100.0
        )
        terminal_g = (
            st.slider(
                "Terminal Growth Rate g (%)",
                min_value=2.0,
                max_value=7.0,
                value=float(default_terminal_g * 100),
                step=0.25,
            )
            / 100.0
        )

    with col2:
        # Solve implied growth
        implied_g = solve_implied_dcf_growth(
            current_fcf=fcf,
            target_ev=ev,
            wacc=wacc,
            terminal_growth=terminal_g,
            years=10,
        )

        st.markdown("#### Valuation Reality Check")
        if np.isnan(implied_g):
            st.error("DCF Solver could not converge with current inputs.")
        else:
            diff = implied_g - sector_tam_growth
            tam_pct = sector_tam_growth * 100
            implied_pct = implied_g * 100

            st.metric(
                "Implied 10-Yr FCF Growth",
                f"{implied_pct:.2f}%",
                delta=f"{-diff * 100:.2f}% vs TAM"
                if diff > 0
                else f"{abs(diff) * 100:.2f}% Headroom",
                delta_color="inverse" if diff > 0 else "normal",
            )

            if implied_g <= sector_tam_growth:
                st.success(
                    f"✅ **Margin of Safety Passed**: Implied growth ({implied_pct:.1f}%) is within Sector TAM expansion rate ({tam_pct:.1f}%)."
                )
            else:
                st.warning(
                    f"⚠️ **Growth Overhang**: Market prices in {implied_pct:.1f}% annual growth, exceeding sectoral TAM of {tam_pct:.1f}%."
                )

    st.markdown("#### 2-Way Sensitivity Matrix (WACC vs Terminal Growth)")
    wacc_steps = [wacc - 0.02, wacc - 0.01, wacc, wacc + 0.01, wacc + 0.02]
    tg_steps = [terminal_g - 0.01, terminal_g, terminal_g + 0.01]

    matrix_data: dict[str, list[str]] = {}
    for tg in tg_steps:
        col_label = f"g = {tg * 100:.1f}%"
        matrix_data[col_label] = []
        for w in wacc_steps:
            g_sol = solve_implied_dcf_growth(
                current_fcf=fcf,
                target_ev=ev,
                wacc=w,
                terminal_growth=tg,
                years=10,
            )
            val_str = f"{g_sol * 100:.1f}%" if not np.isnan(g_sol) else "N/A"
            matrix_data[col_label].append(val_str)

    row_index = [f"WACC {w * 100:.1f}%" for w in wacc_steps]
    df_matrix = pd.DataFrame(matrix_data, index=row_index)
    st.dataframe(df_matrix, use_container_width=True)
