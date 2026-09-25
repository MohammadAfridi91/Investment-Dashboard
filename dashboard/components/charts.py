"""Interactive Plotly financial charts for Dalal Street Dashboard."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def create_candlestick_chart(
    df: pd.DataFrame,
    avwap_swing_low: float | None = None,
    avwap_earnings: float | None = None,
    symbol: str = "",
) -> go.Figure:
    """Creates a high-contrast dark theme candlestick chart with volume and AVWAP overlays."""
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=(f"{symbol} Price Action & AVWAP", "Volume"),
        row_width=[0.2, 0.7],
    )

    if df.empty:
        fig.update_layout(template="plotly_dark", title="No price data available")
        return fig

    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=df["trade_date"],
            open=df["open_price"],
            high=df["high_price"],
            low=df["low_price"],
            close=df["close_price"],
            name="OHLC",
            increasing_line_color="#10b981",
            decreasing_line_color="#ef4444",
        ),
        row=1,
        col=1,
    )

    # AVWAP Overlays
    if avwap_swing_low is not None:
        fig.add_hline(
            y=avwap_swing_low,
            line_dash="dash",
            line_color="#38bdf8",
            annotation_text=f"AVWAP Swing Low: ₹{avwap_swing_low:.1f}",
            annotation_position="top left",
            row=1,
            col=1,
        )

    if avwap_earnings is not None:
        fig.add_hline(
            y=avwap_earnings,
            line_dash="dot",
            line_color="#f59e0b",
            annotation_text=f"AVWAP Earnings: ₹{avwap_earnings:.1f}",
            annotation_position="bottom left",
            row=1,
            col=1,
        )

    # Volume bars
    colors = [
        "#10b981" if c >= o else "#ef4444"
        for c, o in zip(df["close_price"], df["open_price"], strict=False)
    ]
    fig.add_trace(
        go.Bar(
            x=df["trade_date"],
            y=df["volume"],
            marker_color=colors,
            name="Volume",
            opacity=0.7,
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        margin={"l": 40, "r": 40, "t": 40, "b": 40},
        height=550,
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0f172a",
        font={"color": "#94a3b8"},
    )
    return fig


def create_vpvr_chart(
    price_levels: list[float],
    volumes: list[float],
    hvn_levels: list[float] | None = None,
    current_price: float | None = None,
) -> go.Figure:
    """Creates a horizontal volume profile chart highlighting High Volume Nodes (HVN)."""
    fig = go.Figure()

    if not price_levels or not volumes:
        fig.update_layout(template="plotly_dark", title="No VPVR profile data")
        return fig

    fig.add_trace(
        go.Bar(
            y=price_levels,
            x=volumes,
            orientation="h",
            marker_color="#6366f1",
            opacity=0.75,
            name="Volume Profile",
        )
    )

    if current_price is not None:
        fig.add_hline(
            y=current_price,
            line_color="#10b981",
            line_width=2,
            annotation_text=f"LTP: ₹{current_price:.1f}",
            annotation_position="top right",
        )

    if hvn_levels:
        for hvn in hvn_levels:
            fig.add_hline(
                y=hvn,
                line_dash="dash",
                line_color="#eab308",
                annotation_text=f"HVN: ₹{hvn:.1f}",
                annotation_position="bottom right",
            )

    fig.update_layout(
        template="plotly_dark",
        title="Volume Profile Visible Range (VPVR)",
        xaxis_title="Traded Volume",
        yaxis_title="Price (₹)",
        margin={"l": 40, "r": 40, "t": 50, "b": 40},
        height=450,
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0f172a",
        font={"color": "#94a3b8"},
    )
    return fig


def create_regime_gauge(vix_value: float | None, regime: str | None) -> go.Figure:
    """Renders a gauge dial for Market Volatility / Regime."""
    val = vix_value if vix_value is not None else 15.0
    regime_str = regime or "NEUTRAL"

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=val,
            title={
                "text": f"India VIX — Regime: {regime_str}",
                "font": {"size": 18, "color": "#f8fafc"},
            },
            gauge={
                "axis": {"range": [5, 35], "tickwidth": 1, "tickcolor": "#94a3b8"},
                "bar": {"color": "#38bdf8"},
                "bgcolor": "#1e293b",
                "borderwidth": 2,
                "bordercolor": "#334155",
                "steps": [
                    {"range": [5, 14], "color": "#065f46"},  # Risk On
                    {"range": [14, 22], "color": "#854d0e"},  # Neutral
                    {"range": [22, 35], "color": "#991b1b"},  # Risk Off
                ],
                "threshold": {
                    "line": {"color": "white", "width": 4},
                    "thickness": 0.75,
                    "value": val,
                },
            },
        )
    )

    fig.update_layout(
        template="plotly_dark",
        height=260,
        margin={"l": 30, "r": 30, "t": 50, "b": 20},
        paper_bgcolor="#0f172a",
        font={"color": "#94a3b8"},
    )
    return fig
