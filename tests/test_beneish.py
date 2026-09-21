from __future__ import annotations

from core.indicators.beneish import compute_beneish_m_score


def test_beneish_clean_firm() -> None:
    f_curr = {
        "sales": 120.0,
        "cogs": 70.0,
        "receivables": 15.0,
        "total_assets": 200.0,
        "current_assets": 80.0,
        "net_block": 100.0,
        "depreciation": 10.0,
        "gross_block": 110.0,
        "sga_expense": 15.0,
        "net_profit": 20.0,
        "cfo": 22.0,
        "total_liabilities": 50.0,
    }
    f_prev = {
        "sales": 100.0,
        "cogs": 60.0,
        "receivables": 14.0,
        "total_assets": 180.0,
        "current_assets": 70.0,
        "net_block": 95.0,
        "depreciation": 9.0,
        "gross_block": 104.0,
        "sga_expense": 13.0,
        "net_profit": 18.0,
        "cfo": 20.0,
        "total_liabilities": 48.0,
    }
    m = compute_beneish_m_score(f_curr, f_prev)
    # Clean firm score is well below -2.22
    assert m < -2.22


def test_beneish_manipulator_firm() -> None:
    f_curr = {
        "sales": 150.0,
        "cogs": 110.0,
        "receivables": 60.0,  # Huge receivable spike
        "total_assets": 200.0,
        "current_assets": 100.0,
        "net_block": 50.0,
        "depreciation": 2.0,  # Depreciating less
        "gross_block": 80.0,
        "sga_expense": 20.0,
        "net_profit": 35.0,
        "cfo": 2.0,  # High profit, virtually zero cash flow
        "total_liabilities": 120.0,
    }
    f_prev = {
        "sales": 100.0,
        "cogs": 50.0,
        "receivables": 15.0,
        "total_assets": 150.0,
        "current_assets": 60.0,
        "net_block": 60.0,
        "depreciation": 8.0,
        "gross_block": 68.0,
        "sga_expense": 15.0,
        "net_profit": 20.0,
        "cfo": 22.0,
        "total_liabilities": 50.0,
    }
    m = compute_beneish_m_score(f_curr, f_prev)
    # High accruals and spikes flag manipulation
    assert m > -2.22


def test_beneish_c2_lvgi_coefficient() -> None:
    """Verify v6.5 Correction C-2: LVGI coefficient is -0.327."""
    base = {
        "sales": 100.0,
        "cogs": 60.0,
        "receivables": 15.0,
        "total_assets": 200.0,
        "current_assets": 80.0,
        "net_block": 100.0,
        "depreciation": 10.0,
        "gross_block": 110.0,
        "sga_expense": 15.0,
        "net_profit": 15.0,
        "cfo": 15.0,
        "total_liabilities": 50.0,
    }
    prev = dict(base)

    # When all indices are 1.0, TATA = 0, DSRI=1, GMI=1, AQI=1, SGI=1, DEPI=1, SGAI=1, LVGI=1:
    # M = -4.84 + 0.92(1) + 0.528(1) + 0.404(1) + 0.892(1) + 0.115(1) - 0.172(1) + 4.037(0) - 0.327(1)
    # M = -4.84 + 0.920 + 0.528 + 0.404 + 0.892 + 0.115 - 0.172 - 0.327 = -2.480
    m = compute_beneish_m_score(base, prev)
    expected = round(-4.84 + 0.920 + 0.528 + 0.404 + 0.892 + 0.115 - 0.172 - 0.327, 4)
    assert abs(m - expected) < 0.05
