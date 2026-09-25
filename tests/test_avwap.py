from __future__ import annotations

from datetime import date

from core.indicators.avwap import (
    compute_avwap,
    compute_avwap_earnings,
    compute_avwap_swing_low,
    find_swing_low_pivot_index,
)


def test_compute_avwap_formula() -> None:
    # 3 bars:
    # Bar 1: TP=100, V=1000 -> PV=100,000
    # Bar 2: TP=105, V=2000 -> PV=210,000
    # Bar 3: TP=110, V=1500 -> PV=165,000
    # Total PV = 475,000, Total Vol = 4500 -> 475000 / 4500 = 105.555... -> 105.56
    typical_prices = [100.0, 105.0, 110.0]
    volumes = [1000, 2000, 1500]
    res = compute_avwap(typical_prices, volumes)
    assert res == 105.56


def test_compute_avwap_empty_and_zero_volume() -> None:
    assert compute_avwap([], []) == 0.0
    # Zero volume falls back to average of typical prices
    assert compute_avwap([100.0, 110.0], [0, 0]) == 105.0


def test_find_swing_low_pivot_index_detected() -> None:
    # 7 bars: lows: [100, 95, 90, 80, 92, 98, 105]
    # Bar at index 3 (low 80) is <= 90, 95, 92, 98 -> confirmed 5-bar pivot low!
    lows = [100.0, 95.0, 90.0, 80.0, 92.0, 98.0, 105.0]
    idx = find_swing_low_pivot_index(lows, max_lookback=60)
    assert idx == 3


def test_find_swing_low_pivot_index_fallback() -> None:
    # Monotonically increasing lows: no 5-bar pivot low possible
    lows = [80.0, 82.0, 85.0, 88.0, 90.0, 95.0]
    idx = find_swing_low_pivot_index(lows, max_lookback=60)
    # Falls back to index of minimum low in window (index 0)
    assert idx == 0


def test_compute_avwap_swing_low() -> None:
    # 6 bars:
    # Pivot low at index 2 (bar 3)
    highs = [102.0, 100.0, 92.0, 95.0, 100.0, 104.0]
    lows = [98.0, 94.0, 88.0, 90.0, 96.0, 100.0]
    closes = [100.0, 96.0, 90.0, 93.0, 98.0, 102.0]
    volumes = [1000, 1000, 2000, 3000, 2500, 1500]

    # Index 2 has low=88 <= 94, 98, 90, 96 -> pivot low anchor is index 2
    # Bars from index 2 to 5:
    # i=2: TP=(92+88+90)/3 = 90.0, V=2000 -> PV=180,000
    # i=3: TP=(95+90+93)/3 = 92.6667, V=3000 -> PV=278,000
    # i=4: TP=(100+96+98)/3 = 98.0, V=2500 -> PV=245,000
    # i=5: TP=(104+100+102)/3 = 102.0, V=1500 -> PV=153,000
    # Total PV = 856,000, Total Vol = 9000 -> 856000 / 9000 = 95.11
    val = compute_avwap_swing_low(highs, lows, closes, volumes, max_lookback=60)
    assert val == 95.11


def test_compute_avwap_earnings() -> None:
    dates = [
        date(2024, 1, 10),
        date(2024, 1, 11),
        date(2024, 1, 12),
        date(2024, 1, 15),
        date(2024, 1, 16),
    ]
    highs = [100.0, 102.0, 105.0, 110.0, 112.0]
    lows = [98.0, 99.0, 101.0, 106.0, 108.0]
    closes = [99.0, 101.0, 104.0, 109.0, 110.0]
    volumes = [1000, 1000, 2000, 4000, 3000]

    # Earnings on 2024-01-15 (index 3)
    earnings_dates = [date(2024, 1, 15)]
    val = compute_avwap_earnings(
        dates, highs, lows, closes, volumes, earnings_dates, trade_date=date(2024, 1, 16)
    )
    # Slices from index 3 (2024-01-15) to end (index 4)
    # i=3: TP=(110+106+109)/3 = 108.3333, V=4000 -> PV = 433,333.33
    # i=4: TP=(112+108+110)/3 = 110.0, V=3000 -> PV = 330,000.00
    # Total PV = 763,333.33, Total Vol = 7000 -> 763333.33 / 7000 = 109.05
    assert val == 109.05


def test_compute_avwap_earnings_fallback_when_none_match() -> None:
    dates = [date(2024, 1, 10), date(2024, 1, 11)]
    highs = [100.0, 102.0]
    lows = [95.0, 97.0]
    closes = [98.0, 100.0]
    volumes = [1000, 1000]
    # No matching historical earnings -> falls back to swing low anchor without error
    val = compute_avwap_earnings(
        dates, highs, lows, closes, volumes, [], trade_date=date(2024, 1, 11)
    )
    assert val > 0
