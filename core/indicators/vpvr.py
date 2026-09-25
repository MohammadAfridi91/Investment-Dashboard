from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class VPVRResult:
    vpvr_hvn: float
    vpvr_lvn: float
    is_vpvr_breakout: bool
    vpvr_hvn_levels: list[float]
    hvn_high: float


def compute_vpvr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float | int],
    prev_close: float | None = None,
    num_bins: int = 50,
    window: int = 65,
) -> VPVRResult:
    """Compute Volume Profile Visible Range (VPVR) over a trailing window.

    Window: 65 sessions, 50 uniform price bins.
    HVN: top 20th percentile volume bins (>= 80th percentile).
    LVN: Volume(B) < 0.30 * Volume(HVN) AND B.price > HVN.high.
    Breakout: (close > hvn_high) AND (prev_close <= hvn_high) AND (current_bin in LVN).
    """
    n = len(closes)
    if n == 0:
        return VPVRResult(
            vpvr_hvn=0.0,
            vpvr_lvn=0.0,
            is_vpvr_breakout=False,
            vpvr_hvn_levels=[],
            hvn_high=0.0,
        )

    # Slice trailing window
    w_highs = highs[-window:]
    w_lows = lows[-window:]
    w_closes = closes[-window:]
    w_volumes = volumes[-window:]

    if prev_close is None:
        prev_close = float(closes[-2]) if len(closes) >= 2 else float(closes[-1])

    today_close = float(w_closes[-1])
    min_p = float(min(w_lows))
    max_p = float(max(w_highs))

    if max_p <= min_p:
        # Flat price edge case
        level = round(today_close, 2)
        return VPVRResult(
            vpvr_hvn=level,
            vpvr_lvn=level,
            is_vpvr_breakout=False,
            vpvr_hvn_levels=[level],
            hvn_high=level,
        )

    bin_edges = np.linspace(min_p, max_p, num_bins + 1)
    bin_width = float(bin_edges[1] - bin_edges[0])
    bin_centers = [(float(bin_edges[i]) + float(bin_edges[i + 1])) / 2.0 for i in range(num_bins)]
    bin_volumes = np.zeros(num_bins, dtype=float)

    for h, lo, v in zip(w_highs, w_lows, w_volumes, strict=False):
        vol = float(v)
        if vol <= 0:
            continue
        b_start = int((float(lo) - min_p) / bin_width)
        b_end = int((float(h) - min_p) / bin_width)
        b_start = max(0, min(num_bins - 1, b_start))
        b_end = max(0, min(num_bins - 1, b_end))
        if b_start > b_end:
            b_start, b_end = b_end, b_start
        k = b_end - b_start + 1
        bin_volumes[b_start : b_end + 1] += vol / k

    # HVN: top 20th percentile volume bins (>= 80th percentile)
    p80 = float(np.percentile(bin_volumes, 80))
    hvn_indices = [i for i, val in enumerate(bin_volumes) if val >= p80 and val > 0]
    if not hvn_indices:
        hvn_indices = [int(np.argmax(bin_volumes))]

    poc_idx = int(np.argmax(bin_volumes))
    vpvr_hvn = round(bin_centers[poc_idx], 2)
    hvn_levels = sorted([round(bin_centers[i], 2) for i in hvn_indices])
    hvn_high = float(max(bin_edges[i + 1] for i in hvn_indices))

    # LVN: Volume(B) < 0.30 * Volume(HVN) AND B.price > HVN.high
    vol_hvn = float(np.mean([bin_volumes[i] for i in hvn_indices]))
    lvn_indices = [
        i for i in range(num_bins) if bin_volumes[i] < 0.30 * vol_hvn and bin_centers[i] > hvn_high
    ]

    if lvn_indices:
        # Lowest volume node above HVN high
        best_lvn_idx = min(lvn_indices, key=lambda idx: bin_volumes[idx])
        vpvr_lvn = round(bin_centers[best_lvn_idx], 2)
    else:
        # Fallback to nearest price above hvn_high
        vpvr_lvn = round(hvn_high * 1.01, 2)

    # Current bin for today's close
    current_bin = int((today_close - min_p) / bin_width)
    current_bin = max(0, min(num_bins - 1, current_bin))

    is_breakout = bool(
        today_close > hvn_high and prev_close <= hvn_high and current_bin in lvn_indices
    )

    return VPVRResult(
        vpvr_hvn=vpvr_hvn,
        vpvr_lvn=vpvr_lvn,
        is_vpvr_breakout=is_breakout,
        vpvr_hvn_levels=hvn_levels,
        hvn_high=round(hvn_high, 2),
    )
