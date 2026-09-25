from __future__ import annotations

from core.indicators.dcf_solver import (
    compute_wacc,
    solve_implied_dcf_growth,
    solve_multi_scenario_growth,
)


def test_compute_wacc_basic() -> None:
    fin = {
        "market_cap": 8000.0,
        "total_debt": 2000.0,
        "interest_expense": 160.0,  # Kd_pre = 160/2000 = 8%
        "tax_rate": 0.25,  # Kd = 8% * (1 - 0.25) = 6%
    }
    # Rf = 7.12% (0.0712), beta = 1.0, ERP = 5.5% (0.055)
    # Ke = 7.12% + 5.5% = 12.62%
    # V = 10000, E/V = 0.8, D/V = 0.2
    # WACC = 0.8 * 12.62% + 0.2 * 6.0% = 10.096% + 1.2% = 11.296% ~ 0.1130
    wacc = compute_wacc(fin, gsec_yield=0.0712, erp=0.055, beta=1.0)
    assert round(wacc, 2) == 0.11


def test_compute_wacc_beta_winsorization() -> None:
    fin = {"market_cap": 1000.0, "total_debt": 0.0}
    # High beta (2.5) should be capped at 1.6
    wacc_high = compute_wacc(fin, gsec_yield=0.07, erp=0.05, beta=2.5)
    expected_ke_high = 0.07 + 1.60 * 0.05
    assert abs(wacc_high - expected_ke_high) < 1e-4

    # Low beta (0.3) should be raised to 0.70
    wacc_low = compute_wacc(fin, gsec_yield=0.07, erp=0.05, beta=0.3)
    expected_ke_low = 0.07 + 0.70 * 0.05
    assert abs(wacc_low - expected_ke_low) < 1e-4


def test_solve_implied_dcf_growth_residual() -> None:
    fcff_0 = 100.0
    wacc = 0.11
    g_term = 0.05
    years = 10

    # Assume a known growth rate g_target = 0.12 (12%)
    # Compute what EV would be:
    ev = sum(fcff_0 * ((1.0 + 0.12) ** t) / ((1.0 + wacc) ** t) for t in range(1, years + 1))
    ev += (fcff_0 * ((1.0 + 0.12) ** years) * (1.0 + g_term)) / (
        (wacc - g_term) * ((1.0 + wacc) ** years)
    )

    # Solve for g from ev
    solved_g = solve_implied_dcf_growth(fcff_0, ev, wacc, g_term=g_term, years=years, tol=1e-5)
    assert solved_g is not None
    assert abs(solved_g - 0.12) <= 1e-3


def test_solve_implied_dcf_growth_invalid_inputs() -> None:
    # Negative FCFF or EV should return None
    assert solve_implied_dcf_growth(-10.0, 1000.0, 0.12) is None
    assert solve_implied_dcf_growth(100.0, -500.0, 0.12) is None
    # WACC <= g_term should return None (undefined terminal value)
    assert solve_implied_dcf_growth(100.0, 1000.0, 0.04, g_term=0.05) is None


def test_solve_multi_scenario_growth() -> None:
    res = solve_multi_scenario_growth(fcff_0=100.0, ev=2500.0, wacc=0.12, g_term=0.05)
    assert "base" in res
    assert "bear" in res
    assert "bull" in res
    assert res["base"] is not None
