from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any


def compute_avwap(
    typical_prices: Sequence[float],
    volumes: Sequence[float | int],
) -> float:
    """Compute Anchored VWAP: Σ(typical_price * volume) / Σ(volume)."""
    if not typical_prices or not volumes or len(typical_prices) != len(volumes):
        return 0.0

    total_vol = sum(volumes)
    if total_vol <= 0:
        return sum(typical_prices) / len(typical_prices)

    pv_sum = sum(tp * vol for tp, vol in zip(typical_prices, volumes, strict=True))
    return round(pv_sum / total_vol, 2)


def find_swing_low_pivot_index(
    lows: Sequence[float],
    max_lookback: int = 60,
) -> int:
    """Find the index of the most recent 5-bar pivot low within max_lookback sessions.

    A 5-bar pivot low at index i satisfies:
        low[i] < low[i-2], low[i-1], low[i+1], low[i+2]
    Fallback: index of minimum low in the lookback window.
    """
    n = len(lows)
    if n == 0:
        return 0
    if n < 5:
        return int(min(range(n), key=lambda idx: lows[idx]))

    start_idx = max(0, n - max_lookback)
    # Search backwards from the most recent confirmed candidate (n - 3)
    for i in range(n - 3, start_idx + 1, -1):
        if (
            lows[i] < lows[i - 1]
            and lows[i] < lows[i - 2]
            and lows[i] < lows[i + 1]
            and lows[i] < lows[i + 2]
        ):
            return i

    # Fallback to absolute minimum low in lookback window
    window_indices = list(range(start_idx, n))
    return int(min(window_indices, key=lambda idx: lows[idx]))


def compute_avwap_swing_low(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float | int],
    max_lookback: int = 60,
) -> float:
    """Compute AVWAP anchored at the most recent 5-bar pivot low within 60 sessions."""
    n = len(closes)
    if n == 0:
        return 0.0

    anchor_idx = find_swing_low_pivot_index(lows, max_lookback=max_lookback)
    tp = [
        (h + lo + c) / 3.0
        for h, lo, c in zip(highs[anchor_idx:], lows[anchor_idx:], closes[anchor_idx:], strict=True)
    ]
    vol = volumes[anchor_idx:]
    return compute_avwap(tp, vol)


def _to_date_str(d: Any) -> str:
    if isinstance(d, date):
        return d.isoformat()
    return str(d).strip()[:10]


def compute_avwap_earnings(
    dates: Sequence[date | str],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float | int],
    earnings_dates: Sequence[date | str],
    trade_date: date | str | None = None,
    fallback_lookback: int = 60,
) -> float:
    """Compute AVWAP anchored at the most recent historical EARNINGS event <= trade_date.

    If no earnings event found in the window, falls back to swing low AVWAP or lookback start.
    """
    n = len(closes)
    if n == 0:
        return 0.0

    date_str_list = [_to_date_str(d) for d in dates]
    t_date_str = (
        _to_date_str(trade_date) if trade_date else (date_str_list[-1] if date_str_list else "")
    )

    valid_earnings = sorted(
        [_to_date_str(ed) for ed in earnings_dates if _to_date_str(ed) <= t_date_str],
        reverse=True,
    )

    anchor_idx: int | None = None
    for ed in valid_earnings:
        if ed in date_str_list:
            anchor_idx = date_str_list.index(ed)
            break

    if anchor_idx is None:
        # Fallback to swing low anchor
        anchor_idx = find_swing_low_pivot_index(lows, max_lookback=fallback_lookback)

    tp = [
        (h + lo + c) / 3.0
        for h, lo, c in zip(highs[anchor_idx:], lows[anchor_idx:], closes[anchor_idx:], strict=True)
    ]
    vol = volumes[anchor_idx:]
    return compute_avwap(tp, vol)
