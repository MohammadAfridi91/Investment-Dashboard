from __future__ import annotations

from core.indicators.altman import altman_z_double_prime, altman_z_from_financials


def test_altman_z_double_prime_formula() -> None:
    # Z'' = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4
    # With X1=0.2, X2=0.3, X3=0.15, X4=0.8
    # 6.56*0.2 = 1.312
    # 3.26*0.3 = 0.978
    # 6.72*0.15 = 1.008
    # 1.05*0.8 = 0.840
    # Sum = 4.138
    res = altman_z_double_prime(0.2, 0.3, 0.15, 0.8)
    assert res == 4.138
    assert res > 2.6  # Safe zone per Correction C-3


def test_altman_z_from_financials() -> None:
    safe_firm = {
        "total_assets": 1000.0,
        "current_assets": 400.0,
        "current_liabilities": 200.0,  # WC = 200 -> X1 = 0.2
        "net_worth": 600.0,  # X2 = 0.6
        "ebit": 150.0,  # X3 = 0.15
        "total_liabilities": 400.0,  # X4 = 600/400 = 1.5
    }
    z = altman_z_from_financials(safe_firm)
    assert z > 2.6

    distressed_firm = {
        "total_assets": 1000.0,
        "current_assets": 100.0,
        "current_liabilities": 300.0,  # Negative WC = -200 -> X1 = -0.2
        "net_worth": 50.0,
        "ebit": -50.0,  # Operating loss
        "total_liabilities": 950.0,
    }
    z_distressed = altman_z_from_financials(distressed_firm)
    assert z_distressed < 2.6
