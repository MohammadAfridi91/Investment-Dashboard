from __future__ import annotations

from typing import Any


def altman_z_double_prime(x1: float, x2: float, x3: float, x4: float) -> float:
    """Compute Altman Z'' Score for emerging markets.

    Formula per Master Plan §10.5 and Appendix A.25:
        Z'' = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4

    Where:
        X1 = Working Capital / Total Assets
        X2 = Retained Earnings (or Net Worth) / Total Assets
        X3 = EBIT / Total Assets
        X4 = Book Value of Equity / Total Liabilities

    v6.5 Correction C-3: Safe gate threshold is > 2.6 (NOT > 3.0).
    """
    z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
    return round(z, 4)


def altman_z_from_financials(f: dict[str, Any]) -> float:
    """Extract required variables from financials dict and compute Altman Z''."""
    ta = float(f.get("total_assets") or 0)
    if ta <= 0:
        return 0.0

    ca = float(f.get("current_assets") or 0)
    cl = float(f.get("current_liabilities") or 0)
    wc = ca - cl
    x1 = wc / ta

    nw = float(f.get("net_worth") or 0)
    x2 = nw / ta

    ebit = float(f.get("ebit") or 0)
    x3 = ebit / ta

    tl = float(f.get("total_liabilities") or 0)
    x4 = (nw / tl) if tl > 0 else 1.0

    return altman_z_double_prime(x1, x2, x3, x4)
