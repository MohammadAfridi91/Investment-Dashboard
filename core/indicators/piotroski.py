from __future__ import annotations

from typing import Any


def compute_piotroski_f_score(f: dict[str, Any], f_prev: dict[str, Any]) -> int:
    """Compute 9-point Piotroski F-Score.

    Implements the 9 criteria across 3 categories per Master Plan §10.7 and Appendix A.27:
    - Profitability (4 pts):
        1. ROA > 0
        2. CFO > 0
        3. ΔROA > 0
        4. Accrual: CFO / Total Assets > ROA
    - Leverage/Liquidity (3 pts):
        5. ΔLTD / Assets < 0 (v6.5 Correction C-4: asset-normalized leverage reduction)
        6. ΔCurrent Ratio > 0
        7. No new equity issued (shares_t <= shares_{t-1})
    - Operating Efficiency (2 pts):
        8. ΔGross Margin > 0
        9. ΔAsset Turnover > 0

    Score: integer between 0 and 9.
    Threshold: F >= 7 indicates strong fundamental quality.
    """
    score = 0

    # Current year figures
    ta_t = float(f.get("total_assets") or 0)
    np_t = float(f.get("net_profit") or 0)
    cfo_t = float(f.get("cfo") or 0)
    sales_t = float(f.get("sales") or 0)
    cogs_t = float(f.get("cogs") or 0)
    debt_t = float(f.get("total_debt") or 0)
    ca_t = float(f.get("current_assets") or 0)
    cl_t = float(f.get("current_liabilities") or 0)
    shares_t = float(f.get("shares_outstanding") or 0)

    # Previous year figures
    ta_p = float(f_prev.get("total_assets") or 0)
    np_p = float(f_prev.get("net_profit") or 0)
    sales_p = float(f_prev.get("sales") or 0)
    cogs_p = float(f_prev.get("cogs") or 0)
    debt_p = float(f_prev.get("total_debt") or 0)
    ca_p = float(f_prev.get("current_assets") or 0)
    cl_p = float(f_prev.get("current_liabilities") or 0)
    shares_p = float(f_prev.get("shares_outstanding") or 0)

    # 1. Profitability
    roa_t = (np_t / ta_t) if ta_t > 0 else 0.0
    roa_p = (np_p / ta_p) if ta_p > 0 else 0.0

    if roa_t > 0:
        score += 1
    if cfo_t > 0:
        score += 1
    if roa_t > roa_p:
        score += 1
    # Accrual check: CFO / TA > ROA (i.e. CFO > Net Income)
    cfo_scaled = (cfo_t / ta_t) if ta_t > 0 else 0.0
    if cfo_scaled > roa_t:
        score += 1

    # 2. Leverage, Liquidity and Source of Funds
    # v6.5 Correction C-4: ΔLTD / Assets < 0 (asset-normalized: (debt_t - debt_p) / ta_t < 0)
    delta_debt_norm = ((debt_t - debt_p) / ta_t) if ta_t > 0 else 0.0
    if delta_debt_norm < 0:
        score += 1

    cr_t = (ca_t / cl_t) if cl_t > 0 else 0.0
    cr_p = (ca_p / cl_p) if cl_p > 0 else 0.0
    if cr_t > cr_p:
        score += 1

    if shares_t > 0 and shares_p > 0 and shares_t <= shares_p:
        score += 1
    elif shares_t == 0 and shares_p == 0:
        # If shares data not explicitly tracked, assume no new equity issued
        score += 1

    # 3. Operating Efficiency
    gm_t = ((sales_t - cogs_t) / sales_t) if sales_t > 0 else 0.0
    gm_p = ((sales_p - cogs_p) / sales_p) if sales_p > 0 else 0.0
    if gm_t > gm_p:
        score += 1

    ato_t = (sales_t / ta_t) if ta_t > 0 else 0.0
    ato_p = (sales_p / ta_p) if ta_p > 0 else 0.0
    if ato_t > ato_p:
        score += 1

    return score
