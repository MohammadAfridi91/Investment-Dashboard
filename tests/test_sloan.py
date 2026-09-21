from __future__ import annotations

from core.indicators.sloan import sloan_accrual


def test_sloan_accrual_clean() -> None:
    # Net Income = 100, CFO = 110, TA_beg = 1000, TA_end = 1200 (avg = 1100)
    # Sloan = (100 - 110) / 1100 = -10 / 1100 = -0.0091 < 0.10
    val = sloan_accrual(100.0, 110.0, 1000.0, 1200.0)
    assert val < 0.10
    assert val == -0.0091


def test_sloan_accrual_high() -> None:
    # Net Income = 300, CFO = 50, TA_beg = 1000, TA_end = 1000 (avg = 1000)
    # Sloan = (300 - 50) / 1000 = 0.25 > 0.10
    val = sloan_accrual(300.0, 50.0, 1000.0, 1000.0)
    assert val >= 0.10
    assert val == 0.25
