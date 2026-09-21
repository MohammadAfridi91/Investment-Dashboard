from __future__ import annotations

from core.indicators.piotroski import compute_piotroski_f_score


def test_piotroski_perfect_score() -> None:
    f_curr = {
        "total_assets": 1200.0,
        "net_profit": 150.0,  # ROA = 150/1200 = 0.125 > 0 (pt 1)
        "cfo": 180.0,  # CFO > 0 (pt 2), CFO/TA = 0.15 > ROA (pt 4)
        "total_debt": 100.0,  # Debt reduced (100 - 150)/1200 < 0 (pt 5, C-4)
        "current_assets": 500.0,
        "current_liabilities": 200.0,  # CR = 2.5 > 2.0 (pt 6)
        "shares_outstanding": 100.0,  # Shares unchanged (pt 7)
        "sales": 1500.0,
        "cogs": 900.0,  # GM = 600/1500 = 40% > 35% (pt 8), ATO = 1500/1200 = 1.25 > 1.0 (pt 9)
    }
    f_prev = {
        "total_assets": 1000.0,
        "net_profit": 100.0,  # ROA = 100/1000 = 0.10 -> ROA increased (pt 3)
        "cfo": 120.0,
        "total_debt": 150.0,
        "current_assets": 400.0,
        "current_liabilities": 200.0,  # CR = 2.0
        "shares_outstanding": 100.0,
        "sales": 1000.0,
        "cogs": 650.0,  # GM = 350/1000 = 35%, ATO = 1000/1000 = 1.0
    }
    score = compute_piotroski_f_score(f_curr, f_prev)
    assert score == 9


def test_piotroski_c4_asset_normalized_debt() -> None:
    """Verify v6.5 Correction C-4: ΔLTD / Assets < 0."""
    f_curr = {
        "total_assets": 1000.0,
        "net_profit": 10.0,
        "cfo": 15.0,
        "total_debt": 120.0,  # Debt INCREASED from 100 -> delta debt is +20, should NOT get point
        "current_assets": 200.0,
        "current_liabilities": 100.0,
        "shares_outstanding": 10.0,
        "sales": 500.0,
        "cogs": 300.0,
    }
    f_prev = {
        "total_assets": 1000.0,
        "net_profit": 10.0,
        "cfo": 15.0,
        "total_debt": 100.0,
        "current_assets": 200.0,
        "current_liabilities": 100.0,
        "shares_outstanding": 10.0,
        "sales": 500.0,
        "cogs": 300.0,
    }
    score = compute_piotroski_f_score(f_curr, f_prev)
    # Debt increased, so pt 5 is 0
    assert score < 9
