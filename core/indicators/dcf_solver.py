from __future__ import annotations

from typing import Any

from scipy.optimize import brentq

from core.utils.logging import get_logger

log = get_logger("indicators.dcf")


def compute_wacc(
    fin: Any,
    gsec_yield: float,
    erp: float = 0.055,
    beta: float | None = None,
) -> float:
    """Compute Weighted Average Cost of Capital (WACC).

    Formula per Master Plan §10.8 and Appendix A.1:
        Ke = Rf + beta * ERP
        Rf = 10Y G-Sec yield (from market_regime.gsec_10y_yield)
        beta winsorized to [0.70, 1.60] (default 1.0)
        ERP = 5.5% (0.055)

        Kd_pre = Interest_Expense / Total_Debt (or Rf + 1.0% if zero debt)
        Kd = Kd_pre * (1 - Tax_Rate)

        WACC = (E/V)*Ke + (D/V)*Kd
        E = Market Cap, D = Total Debt, V = E + D
    """
    b = 1.0 if beta is None else beta
    b_winsorized = max(0.70, min(1.60, b))
    rf = gsec_yield
    ke = rf + b_winsorized * erp

    # Extract debt and tax from fin (dict or model)
    if isinstance(fin, dict):
        total_debt = float(fin.get("total_debt") or 0)
        interest_exp = float(fin.get("interest_expense") or 0)
        tax_rate = float(fin.get("tax_rate") or 0.25)
        mcap = float(fin.get("market_cap") or 0)
    else:
        total_debt = float(getattr(fin, "total_debt", 0) or 0)
        interest_exp = float(getattr(fin, "interest_expense", 0) or 0)
        tax_rate = float(getattr(fin, "tax_rate", 0.25) or 0.25)
        mcap = float(getattr(fin, "market_cap", 0) or 0)

    kd_pre = interest_exp / total_debt if total_debt > 0 and interest_exp > 0 else rf + 0.01
    kd = kd_pre * (1.0 - tax_rate)

    v = mcap + total_debt
    if v <= 0:
        return round(ke, 4)

    wacc = (mcap / v) * ke + (total_debt / v) * kd
    return round(wacc, 4)


def solve_implied_dcf_growth(
    fcff_0: float,
    ev: float,
    wacc: float,
    g_term: float = 0.05,
    years: int = 10,
    tol: float = 1e-5,
) -> float | None:
    """Solve for implied revenue/FCFF growth rate equating DCF value to Enterprise Value.

    Uses Brent's method (scipy.optimize.brentq) over bounds [-0.20, 0.50].
    Formula per Master Plan §10.8 and Appendix A.15:
        EV = Σ[t=1..10] FCFF_0 * (1 + g)^t / (1 + WACC)^t
           + FCFF_0 * (1 + g)^10 * (1 + g_term) / ((WACC - g_term) * (1 + WACC)^10)
    """
    if fcff_0 <= 0 or ev <= 0 or wacc <= g_term:
        return None

    def objective(g: float) -> float:
        pv = sum(fcff_0 * ((1.0 + g) ** t) / ((1.0 + wacc) ** t) for t in range(1, years + 1))
        tv = (fcff_0 * ((1.0 + g) ** years) * (1.0 + g_term)) / (
            (wacc - g_term) * ((1.0 + wacc) ** years)
        )
        return (pv + tv) - ev

    try:
        sol = brentq(objective, -0.20, 0.50, xtol=tol)
        return round(float(sol), 4)
    except (ValueError, RuntimeError):
        return None


def solve_multi_scenario_growth(
    fcff_0: float,
    ev: float,
    wacc: float,
    g_term: float = 0.05,
) -> dict[str, float | None]:
    """Solve for bear, base, and bull reverse DCF growth rates."""
    base_g = solve_implied_dcf_growth(fcff_0, ev, wacc, g_term=g_term)

    # Bear: higher hurdle (+1% WACC), lower terminal growth (-0.5%)
    bear_wacc = wacc + 0.01
    bear_gterm = max(0.02, g_term - 0.005)
    bear_g = solve_implied_dcf_growth(fcff_0, ev, bear_wacc, g_term=bear_gterm)

    # Bull: lower hurdle (-1% WACC), higher terminal growth (+0.5%)
    bull_wacc = max(g_term + 0.01, wacc - 0.01)
    bull_gterm = g_term + 0.005
    bull_g = solve_implied_dcf_growth(fcff_0, ev, bull_wacc, g_term=bull_gterm)

    return {"base": base_g, "bear": bear_g, "bull": bull_g}
