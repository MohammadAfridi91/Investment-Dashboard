from __future__ import annotations


def sloan_accrual(ni: float, cfo: float, ta_beg: float, ta_end: float) -> float:
    """Compute Sloan Accrual Ratio.

    Formula per Master Plan §10.6 and Appendix A.26:
        Sloan = (Net Income - CFO) / Average Total Assets
        Average Total Assets = (ta_beg + ta_end) / 2.0

    Threshold: Sloan < 0.10 indicates clean earnings quality.
    """
    avg = (ta_beg + ta_end) / 2.0
    if avg == 0.0:
        return 0.0
    return round((ni - cfo) / avg, 4)
