from __future__ import annotations

from typing import Any


def compute_beneish_m_score(f: dict[str, Any], f_prev: dict[str, Any]) -> float:
    """Compute Beneish M-Score for earnings manipulation detection.

    Implements the 8-variable model per Master Plan §10.4 and Appendix A.24:
        M = -4.84 + 0.920*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
            + 0.115*DEPI - 0.172*SGAI + 4.037*TATA - 0.327*LVGI

    v6.5 Correction C-2: LVGI coefficient is -0.327 (NOT +0.0327).
    Threshold: M > -2.22 suggests earnings manipulation risk.
    """
    def safe(num: float, den: float) -> float:
        return (num / den) if den != 0.0 else 1.0

    rec_t = float(f.get("receivables") or 0)
    sales_t = float(f.get("sales") or 0)
    rec_p = float(f_prev.get("receivables") or 0)
    sales_p = float(f_prev.get("sales") or 0)
    dsri = safe(safe(rec_t, sales_t), safe(rec_p, sales_p))

    cogs_t = float(f.get("cogs") or 0)
    cogs_p = float(f_prev.get("cogs") or 0)
    gm_t = safe(sales_t - cogs_t, sales_t)
    gm_p = safe(sales_p - cogs_p, sales_p)
    gmi = safe(gm_p, gm_t)

    ta_t = float(f.get("total_assets") or 0)
    ca_t = float(f.get("current_assets") or 0)
    nb_t = float(f.get("net_block") or 0)
    ta_p = float(f_prev.get("total_assets") or 0)
    ca_p = float(f_prev.get("current_assets") or 0)
    nb_p = float(f_prev.get("net_block") or 0)
    nc_t = safe(ta_t - (ca_t + nb_t), ta_t)
    nc_p = safe(ta_p - (ca_p + nb_p), ta_p)
    aqi = safe(nc_t, nc_p)

    sgi = safe(sales_t, sales_p)

    dep_t = float(f.get("depreciation") or 0)
    gb_t = float(f.get("gross_block") or 0)
    dep_p = float(f_prev.get("depreciation") or 0)
    gb_p = float(f_prev.get("gross_block") or 0)
    dr_t = safe(dep_t, gb_t + dep_t)
    dr_p = safe(dep_p, gb_p + dep_p)
    depi = safe(dr_p, dr_t)

    sga_t = float(f.get("sga_expense") or 0)
    sga_p = float(f_prev.get("sga_expense") or 0)
    sgai = safe(safe(sga_t, sales_t), safe(sga_p, sales_p))

    ni_t = float(f.get("net_profit") or 0)
    cfo_t = float(f.get("cfo") or 0)
    tata = safe(ni_t - cfo_t, ta_t)

    tl_t = float(f.get("total_liabilities") or 0)
    tl_p = float(f_prev.get("total_liabilities") or 0)
    lev_t = safe(tl_t, ta_t)
    lev_p = safe(tl_p, ta_p)
    lvgi = safe(lev_t, lev_p)

    # v6.5 correction C-2: LVGI coefficient is -0.327
    m = (
        -4.84
        + 0.920 * dsri
        + 0.528 * gmi
        + 0.404 * aqi
        + 0.892 * sgi
        + 0.115 * depi
        - 0.172 * sgai
        + 4.037 * tata
        - 0.327 * lvgi
    )
    return round(m, 4)
