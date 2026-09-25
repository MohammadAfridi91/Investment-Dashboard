from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from core.indicators.technicals import (
    compute_adtv_20d,
    compute_delivery_spike_ratio,
    compute_ema,
    compute_mansfield_rs,
    compute_sma,
    compute_technical_indicators,
    compute_wilder_atr,
    find_5bar_pivots,
    find_fractal_swing_low_20d,
)


def test_indicator_parity_ema_vs_tradingview() -> None:
    """Verification Plan Test 3: EMA(20/50/200) vs TradingView within 0.05-0.10%."""
    np.random.seed(42)
    # Generate 250 realistic daily price steps
    returns = np.random.normal(0.0005, 0.015, 250)
    prices = [100.0]
    for r in returns:
        prices.append(prices[-1] * (1.0 + r))

    # Test EMA 20
    ema20 = compute_ema(prices, 20)
    s = pd.Series(prices)
    pd_ema20 = s.ewm(span=20, adjust=False).mean().tolist()
    for our_val, tv_val in zip(ema20, pd_ema20, strict=True):
        rel_diff = abs(our_val - tv_val) / tv_val
        assert rel_diff < 0.0010  # within 0.10%

    # Test EMA 50
    ema50 = compute_ema(prices, 50)
    pd_ema50 = s.ewm(span=50, adjust=False).mean().tolist()
    for our_val, tv_val in zip(ema50, pd_ema50, strict=True):
        rel_diff = abs(our_val - tv_val) / tv_val
        assert rel_diff < 0.0010  # within 0.10%

    # Test SMA 200
    sma200 = compute_sma(prices, 200)
    pd_sma200 = s.rolling(200).mean().tolist()
    for our_val, tv_val in zip(sma200[200:], pd_sma200[200:], strict=True):
        rel_diff = abs(our_val - tv_val) / tv_val
        assert rel_diff < 0.0001  # within 0.01%


def test_indicator_parity_atr14_vs_tradingview() -> None:
    """Verification Plan Test 3: ATR(14) vs TradingView within 0.05-0.10%."""
    np.random.seed(123)
    n = 100
    closes = [500.0]
    highs = [505.0]
    lows = [495.0]

    for _ in range(n - 1):
        prev = closes[-1]
        c = prev * (1.0 + np.random.normal(0, 0.01))
        h = max(c, prev) + abs(np.random.normal(0, 2.0))
        lo = min(c, prev) - abs(np.random.normal(0, 2.0))
        highs.append(h)
        lows.append(lo)
        closes.append(c)

    our_atr = compute_wilder_atr(highs, lows, closes, period=14)

    # TradingView ta.atr(14) is ta.rma(tr, 14) with alpha = 1 / 14
    tr = [highs[0] - lows[0]]
    for i in range(1, n):
        tr.append(
            max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        )

    tv_atr = pd.Series(tr).ewm(alpha=1.0 / 14.0, adjust=False).mean().tolist()

    for our_val, tv_val in zip(our_atr, tv_atr, strict=True):
        rel_diff = abs(our_val - tv_val) / tv_val
        assert rel_diff < 0.0010  # within 0.10%


def test_mansfield_rs_calculation() -> None:
    # Stock outperforming benchmark: stock doubles, benchmark stays flat
    stock_closes = [100.0 + i * 2.0 for i in range(40)]
    bench_closes = [100.0] * 40

    m_rs = compute_mansfield_rs(stock_closes, bench_closes, lookback=20)
    assert len(m_rs) == 40
    # Later bars should have strongly positive Mansfield RS
    assert m_rs[-1] > 0.0

    # Stock underperforming benchmark
    stock_under = [100.0 - i * 1.0 for i in range(40)]
    m_rs_under = compute_mansfield_rs(stock_under, bench_closes, lookback=20)
    assert m_rs_under[-1] < 0.0


def test_5bar_pivots_and_fractal_swing_low() -> None:
    # 20 bars: clear pivot low at bar 10
    lows = [100.0] * 20
    highs = [105.0] * 20
    lows[10] = 80.0
    # Surrounding lows higher
    lows[8] = 95.0
    lows[9] = 90.0
    lows[11] = 92.0
    lows[12] = 96.0

    fractal_low = find_fractal_swing_low_20d(lows)
    assert fractal_low == 80.0

    # Test pivot highs
    highs[5] = 130.0
    highs[3] = 110.0
    highs[4] = 115.0
    highs[6] = 118.0
    highs[7] = 112.0
    p_highs, p_lows = find_5bar_pivots(highs, lows, lookback=250)
    assert 130.0 in p_highs
    assert 80.0 in p_lows


def test_adtv_and_delivery_spike() -> None:
    traded_vals = [10_000_000.0] * 20
    assert compute_adtv_20d(traded_vals) == 10_000_000.0

    # Delivery quantities: 20 days of 1000, today = 3500 -> 3.5x spike
    delivery_qtys = [1000] * 20 + [3500]
    spike = compute_delivery_spike_ratio(delivery_qtys)
    assert spike == 3.5


def test_compute_technical_indicators_row_full() -> None:
    # Build 70 daily bars for INFY
    price_bars = []
    bench_bars = []
    sector_bars = []
    base_date = date(2024, 1, 1)

    for i in range(70):
        d = date.fromordinal(base_date.toordinal() + i)
        price_bars.append(
            {
                "trade_date": d,
                "open_price": 1400.0 + i,
                "high_price": 1420.0 + i,
                "low_price": 1390.0 + i,
                "close_price": 1410.0 + i,
                "volume": 2000000,
                "traded_value": 2800000000.0,
                "delivery_qty": 1200000,
            }
        )
        bench_bars.append(
            {
                "trade_date": d,
                "close_price": 20000.0 + i * 10,
            }
        )
        sector_bars.append(
            {
                "trade_date": d,
                "close_price": 35000.0 + i * 20,
            }
        )

    target_d: date = price_bars[-1]["trade_date"]
    row = compute_technical_indicators(
        symbol="INFY",
        target_date=target_d,
        price_bars=price_bars,
        benchmark_bars=bench_bars,
        sector_bars=sector_bars,
        earnings_dates=[date(2024, 1, 15)],
    )

    assert row.symbol == "INFY"
    assert row.trade_date == target_d
    assert row.ema_20 is not None and row.ema_20 > 0
    assert row.ema_50 is not None and row.ema_50 > 0
    assert row.atr_14 is not None and row.atr_14 > 0
    assert row.avwap_swing_low is not None and row.avwap_swing_low > 0
    assert row.avwap_earnings is not None and row.avwap_earnings > 0
    assert row.vpvr_hvn is not None and row.vpvr_hvn > 0
    assert row.fractal_swing_low_20d > 0
    assert row.adtv_20d is not None and row.adtv_20d > 0
    assert row.delivery_spike_ratio is not None


def test_technical_indicators_computer_batch_run() -> None:
    from unittest.mock import MagicMock

    from core.indicators.technicals import TechnicalIndicatorsComputer

    mock_db = MagicMock()
    # universe
    mock_db.select.side_effect = [
        [{"symbol": "TCS"}, {"symbol": "INFY"}],
        # benchmark_prices (NIFTY 500)
        [{"symbol": "NIFTY 500", "trade_date": "2024-01-25", "close_price": 21500.0}],
        # sector_indices
        [{"index_symbol": "NIFTY IT", "trade_date": "2024-01-25", "close_price": 37000.0}],
        # governance_events (EARNINGS)
        [{"symbol": "TCS", "event_date": "2024-01-15", "event_type": "EARNINGS"}],
    ]
    mock_db.select_in.return_value = [
        {
            "symbol": "TCS",
            "trade_date": "2024-01-25",
            "open_price": 3800.0,
            "high_price": 3850.0,
            "low_price": 3790.0,
            "close_price": 3820.0,
            "volume": 1500000,
            "traded_value": 5700000000.0,
            "delivery_qty": 900000,
        },
        {
            "symbol": "INFY",
            "trade_date": "2024-01-25",
            "open_price": 1600.0,
            "high_price": 1630.0,
            "low_price": 1590.0,
            "close_price": 1615.0,
            "volume": 2500000,
            "traded_value": 4000000000.0,
            "delivery_qty": 1400000,
        },
    ]

    computer = TechnicalIndicatorsComputer(mock_db, config={})
    count = computer.run_for_date(date(2024, 1, 25))
    assert count == 2
    mock_db.upsert.assert_called_once()
    args = mock_db.upsert.call_args[0]
    assert args[0] == "technical_indicators"
    assert len(args[1]) == 2
