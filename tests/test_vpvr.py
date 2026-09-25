from __future__ import annotations

from core.indicators.vpvr import compute_vpvr


def test_compute_vpvr_basic_hvn_and_lvn() -> None:
    # Construct 65 bars with known price range 100 to 150
    # High volume (100,000 per bar) in range 100-120
    # Very low volume (1,000 per bar) above 120
    highs = []
    lows = []
    closes = []
    volumes = []

    for _ in range(60):
        highs.append(120.0)
        lows.append(100.0)
        closes.append(110.0)
        volumes.append(100000)

    for _ in range(5):
        highs.append(150.0)
        lows.append(125.0)
        closes.append(135.0)
        volumes.append(500)

    res = compute_vpvr(highs, lows, closes, volumes, num_bins=50, window=65)

    assert res.vpvr_hvn > 0
    assert len(res.vpvr_hvn_levels) > 0
    # HVN high should be around 120
    assert res.hvn_high <= 130.0
    # LVN should exist above HVN high
    assert res.vpvr_lvn > res.hvn_high


def test_compute_vpvr_breakout_flag() -> None:
    highs = []
    lows = []
    closes = []
    volumes = []

    # 63 bars inside 100-120 with high volume
    for _ in range(63):
        highs.append(120.0)
        lows.append(100.0)
        closes.append(110.0)
        volumes.append(50000)

    # Bar 64: close right at resistance 119.5 (prev_close <= hvn_high)
    highs.append(120.0)
    lows.append(115.0)
    closes.append(119.5)
    volumes.append(50000)

    # Bar 65: breaks out to 135 with thin volume (in LVN above hvn_high)
    highs.append(140.0)
    lows.append(125.0)
    closes.append(135.0)
    volumes.append(200)

    res = compute_vpvr(highs, lows, closes, volumes, prev_close=119.5, num_bins=50, window=65)

    assert res.is_vpvr_breakout is True


def test_compute_vpvr_no_breakout_when_close_below_hvn() -> None:
    highs = [120.0] * 65
    lows = [100.0] * 65
    closes = [110.0] * 65
    volumes = [5000] * 65

    res = compute_vpvr(highs, lows, closes, volumes, num_bins=50, window=65)
    assert res.is_vpvr_breakout is False


def test_compute_vpvr_flat_price_edge_case() -> None:
    highs = [100.0] * 10
    lows = [100.0] * 10
    closes = [100.0] * 10
    volumes = [1000] * 10

    res = compute_vpvr(highs, lows, closes, volumes, num_bins=50, window=65)
    assert res.vpvr_hvn == 100.0
    assert res.is_vpvr_breakout is False
