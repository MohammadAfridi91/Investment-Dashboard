from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from core.database.client import DB
from core.indicators.avwap import compute_avwap_earnings, compute_avwap_swing_low
from core.indicators.vpvr import compute_vpvr
from core.models import TechnicalIndicatorsRow
from core.utils.logging import get_logger

log = get_logger("indicators.technicals")


def compute_ema(series: Sequence[float], period: int) -> list[float]:
    """Compute Exponential Moving Average (EMA) matching TradingView ta.ema.

    Recursive formula:
        ema[0] = series[0]
        ema[t] = alpha * series[t] + (1 - alpha) * ema[t - 1]
    where alpha = 2 / (period + 1).
    """
    n = len(series)
    if n == 0:
        return []
    if period <= 1 or n == 1:
        return [float(x) for x in series]

    alpha = 2.0 / (period + 1.0)
    ema: list[float] = [float(series[0])]
    for i in range(1, n):
        ema.append(alpha * float(series[i]) + (1.0 - alpha) * ema[-1])

    return ema


def compute_sma(series: Sequence[float], period: int) -> list[float]:
    """Compute Simple Moving Average (SMA)."""
    n = len(series)
    if n == 0:
        return []
    sma: list[float] = [0.0] * n
    current_sum = 0.0
    for i in range(n):
        current_sum += float(series[i])
        if i >= period:
            current_sum -= float(series[i - period])
            sma[i] = current_sum / period
        else:
            sma[i] = current_sum / (i + 1)
    return sma


def compute_wilder_atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> list[float]:
    """Compute Wilder's smoothed Average True Range (ATR(14)) matching TradingView ta.atr.

    Recursive formula (ta.rma on TR):
        TR_t = max(H - L, |H - C_prev|, |L - C_prev|)
        ATR_0 = TR_0
        ATR_t = alpha * TR_t + (1 - alpha) * ATR_{t-1}
    where alpha = 1 / period.
    """
    n = len(closes)
    if n == 0:
        return []

    tr: list[float] = [float(highs[0]) - float(lows[0])]
    for i in range(1, n):
        h = float(highs[i])
        lo = float(lows[i])
        cp = float(closes[i - 1])
        tr.append(max(h - lo, abs(h - cp), abs(lo - cp)))

    alpha = 1.0 / period
    atr: list[float] = [tr[0]]
    for i in range(1, n):
        atr.append(alpha * tr[i] + (1.0 - alpha) * atr[-1])

    return atr


def compute_mansfield_rs(
    stock_closes: Sequence[float],
    benchmark_closes: Sequence[float],
    lookback: int = 20,
) -> list[float]:
    """Compute Mansfield Relative Strength against a benchmark index.

    Formula:
        RS_ratio = stock_close / benchmark_close
        Mansfield_RS = (RS_ratio / SMA_20(RS_ratio) - 1) * 100
    """
    n = min(len(stock_closes), len(benchmark_closes))
    if n == 0:
        return []

    s_slice = stock_closes[-n:]
    b_slice = benchmark_closes[-n:]

    rs_ratios: list[float] = []
    for sc, bc in zip(s_slice, b_slice, strict=True):
        bc_val = float(bc)
        rs_ratios.append((float(sc) / bc_val) if bc_val > 0 else 1.0)

    sma_rs = compute_sma(rs_ratios, lookback)
    mansfield: list[float] = []
    for rs, s_rs in zip(rs_ratios, sma_rs, strict=True):
        m = (rs / s_rs - 1.0) * 100.0 if s_rs > 0 else 0.0
        mansfield.append(round(m, 4))

    return mansfield


def find_5bar_pivots(
    highs: Sequence[float],
    lows: Sequence[float],
    lookback: int = 250,
) -> tuple[list[float], list[float]]:
    """Identify confirmed 5-bar pivot highs and pivot lows over lookback sessions.

    Returns:
        tuple(sorted_unique_high_levels, sorted_unique_low_levels)
    """
    n = len(highs)
    if n < 5:
        return [], []

    w_highs = highs[-lookback:]
    w_lows = lows[-lookback:]
    w_len = len(w_highs)

    p_highs: set[float] = set()
    p_lows: set[float] = set()

    for i in range(2, w_len - 2):
        h = float(w_highs[i])
        lo = float(w_lows[i])
        if (
            h > float(w_highs[i - 1])
            and h > float(w_highs[i - 2])
            and h > float(w_highs[i + 1])
            and h > float(w_highs[i + 2])
        ):
            p_highs.add(round(h, 2))

        if (
            lo < float(w_lows[i - 1])
            and lo < float(w_lows[i - 2])
            and lo < float(w_lows[i + 1])
            and lo < float(w_lows[i + 2])
        ):
            p_lows.add(round(lo, 2))

    return sorted(p_highs), sorted(p_lows)


def find_fractal_swing_low_20d(lows: Sequence[float]) -> float:
    """Find the most recent 5-bar pivot low within the trailing 20 sessions.

    Fallback: minimum low in the trailing 20 sessions.
    """
    n = len(lows)
    if n == 0:
        return 0.0
    w_lows = [float(x) for x in lows[-20:]]
    w_len = len(w_lows)
    if w_len < 5:
        return min(w_lows)

    # Search backwards for confirmed 5-bar pivot low
    for i in range(w_len - 3, 1, -1):
        if (
            w_lows[i] < w_lows[i - 1]
            and w_lows[i] < w_lows[i - 2]
            and w_lows[i] < w_lows[i + 1]
            and w_lows[i] < w_lows[i + 2]
        ):
            return round(w_lows[i], 2)

    return round(min(w_lows), 2)


def compute_adtv_20d(traded_values: Sequence[float]) -> float:
    """Compute Average Daily Traded Value (ADTV) over trailing 20 sessions in INR."""
    if not traded_values:
        return 0.0
    vals = [float(v) for v in traded_values[-20:]]
    return round(float(np.mean(vals)), 2)


def compute_delivery_spike_ratio(
    delivery_quantities: Sequence[float | int],
) -> float | None:
    """Compute delivery spike ratio = today's delivery quantity / 20d mean delivery quantity."""
    n = len(delivery_quantities)
    if n < 2:
        return 1.0
    today_dq = float(delivery_quantities[-1])
    prior_dq = [float(x) for x in delivery_quantities[-21:-1]]
    if not prior_dq:
        return 1.0
    mean_dq = float(np.mean(prior_dq))
    if mean_dq <= 0:
        return 1.0 if today_dq > 0 else 0.0
    return round(today_dq / mean_dq, 4)


def compute_technical_indicators(
    symbol: str,
    target_date: date,
    price_bars: list[dict[str, Any]],
    benchmark_bars: list[dict[str, Any]],
    sector_bars: list[dict[str, Any]],
    earnings_dates: Sequence[date | str],
) -> TechnicalIndicatorsRow:
    """Compute all technical indicators for a given symbol on target_date."""
    # Ensure sorted by trade_date ascending
    sorted_bars = sorted(price_bars, key=lambda b: str(b["trade_date"]))
    closes = [float(b["close_price"]) for b in sorted_bars]
    highs = [float(b["high_price"]) for b in sorted_bars]
    lows = [float(b["low_price"]) for b in sorted_bars]
    volumes = [int(float(b.get("volume", 0) or 0)) for b in sorted_bars]
    traded_values = [float(b.get("traded_value", 0.0) or 0.0) for b in sorted_bars]
    delivery_qtys = [float(b.get("delivery_qty", 0) or 0) for b in sorted_bars]
    dates = [b["trade_date"] for b in sorted_bars]

    # EMAs & SMA
    ema20_arr = compute_ema(closes, 20)
    ema50_arr = compute_ema(closes, 50)
    sma200_arr = compute_sma(closes, 200)

    ema_20 = round(ema20_arr[-1], 2) if ema20_arr else None
    ema_50 = round(ema50_arr[-1], 2) if ema50_arr else None
    sma_200 = round(sma200_arr[-1], 2) if sma200_arr else None

    # ATR(14) and ATR compression (ATR_14 < SMA_20(ATR_14) * 0.80)
    atr14_arr = compute_wilder_atr(highs, lows, closes, period=14)
    atr_14 = round(atr14_arr[-1], 4) if atr14_arr else None
    atr_sma20_arr = compute_sma(atr14_arr, 20)
    atr_sma_20 = round(atr_sma20_arr[-1], 4) if atr_sma20_arr else None
    atr_compression = False
    if atr_14 is not None and atr_sma_20 is not None and atr_sma_20 > 0:
        atr_compression = bool(atr_14 < atr_sma_20 * 0.80)

    # Mansfield RS vs NIFTY 500
    sorted_bench = sorted(benchmark_bars, key=lambda b: str(b["trade_date"]))
    bench_closes = [float(b["close_price"]) for b in sorted_bench]
    rs500_arr = compute_mansfield_rs(closes, bench_closes, lookback=20)
    mansfield_rs_500 = rs500_arr[-1] if rs500_arr else None
    prev_mansfield_rs_500 = rs500_arr[-2] if len(rs500_arr) >= 2 else None

    # Mansfield RS vs Sector Index
    sorted_sec = sorted(sector_bars, key=lambda b: str(b["trade_date"]))
    sec_closes = [float(b["close_price"]) for b in sorted_sec]
    rs_sec_arr = compute_mansfield_rs(closes, sec_closes, lookback=20)
    mansfield_rs_sector = rs_sec_arr[-1] if rs_sec_arr else None
    prev_mansfield_rs_sector = rs_sec_arr[-2] if len(rs_sec_arr) >= 2 else None

    # AVWAP
    avwap_swing_low = compute_avwap_swing_low(highs, lows, closes, volumes, max_lookback=60)
    avwap_earnings = compute_avwap_earnings(
        dates,
        highs,
        lows,
        closes,
        volumes,
        earnings_dates,
        trade_date=target_date,
        fallback_lookback=60,
    )

    # VPVR
    prev_c = closes[-2] if len(closes) >= 2 else closes[-1]
    vpvr = compute_vpvr(highs, lows, closes, volumes, prev_close=prev_c, num_bins=50, window=65)

    # 250d Pivot high/low levels and 20d fractal swing low
    swing_highs_250d, swing_lows_250d = find_5bar_pivots(highs, lows, lookback=250)
    fractal_swing_low_20d = find_fractal_swing_low_20d(lows)

    # ADTV 20d & Delivery spike ratio
    adtv_20d = compute_adtv_20d(traded_values)
    delivery_spike = compute_delivery_spike_ratio(delivery_qtys)

    return TechnicalIndicatorsRow(
        symbol=symbol,
        trade_date=target_date,
        ema_20=ema_20,
        ema_50=ema_50,
        sma_200=sma_200,
        atr_14=atr_14,
        atr_sma_20=atr_sma_20,
        atr_compression=atr_compression,
        mansfield_rs_500=mansfield_rs_500,
        prev_mansfield_rs_500=prev_mansfield_rs_500,
        mansfield_rs_sector=mansfield_rs_sector,
        prev_mansfield_rs_sector=prev_mansfield_rs_sector,
        avwap_swing_low=avwap_swing_low,
        avwap_earnings=avwap_earnings,
        vpvr_hvn=vpvr.vpvr_hvn,
        vpvr_lvn=vpvr.vpvr_lvn,
        is_vpvr_breakout=vpvr.is_vpvr_breakout,
        fractal_swing_low_20d=fractal_swing_low_20d,
        vpvr_hvn_levels=vpvr.vpvr_hvn_levels,
        swing_high_levels_250d=swing_highs_250d,
        swing_low_levels_250d=swing_lows_250d,
        delivery_spike_ratio=delivery_spike,
        adtv_20d=adtv_20d,
    )


class TechnicalIndicatorsComputer:
    """Batch computer for technical indicators across universe stocks."""

    def __init__(self, db: DB, config: Any) -> None:
        self.db = db
        self.config = config

    def run_for_date(self, target_date: date, symbols: list[str] | None = None) -> int:
        if not symbols:
            uni_rows = self.db.select("universe", columns="symbol")
            symbols = [u["symbol"] for u in uni_rows]

        if not symbols:
            log.warning("no_symbols_for_technicals")
            return 0

        # Load benchmark prices (NIFTY 500) trailing 300 sessions
        bench_rows = self.db.select(
            "benchmark_prices",
            columns="symbol,trade_date,close_price",
            filters={"symbol": "NIFTY 500"},
            order="trade_date.asc",
            limit=300,
        )

        # Build sector mapping symbol -> sector_index
        mapping_path = Path("config/industry_mappings.json")
        sym_to_sector: dict[str, str] = {}
        if mapping_path.exists():
            try:
                with mapping_path.open(encoding="utf-8") as f:
                    ind_map = json.load(f)
                    for sec, syms in ind_map.items():
                        for s in syms:
                            sym_to_sector[s] = sec
            except Exception as e:
                log.warning("industry_map_load_failed", error=str(e))

        # Query sector indices prices
        sector_rows = self.db.select(
            "sector_indices",
            columns="index_symbol,trade_date,close_price",
            order="trade_date.asc",
            limit=5000,
        )
        sector_by_index: dict[str, list[dict[str, Any]]] = {}
        for sr in sector_rows:
            sector_by_index.setdefault(sr["index_symbol"], []).append(sr)

        # Batch load earnings events
        gov_events = self.db.select(
            "governance_events",
            columns="symbol,event_date,event_type",
            filters={"event_type": "EARNINGS"},
            order="event_date.asc",
            limit=5000,
        )
        earnings_by_sym: dict[str, list[date]] = {}
        for g in gov_events:
            d_val = g.get("event_date")
            if d_val:
                try:
                    d_obj = date.fromisoformat(str(d_val)[:10])
                    earnings_by_sym.setdefault(g["symbol"], []).append(d_obj)
                except Exception:
                    pass

        # Query historical price bars for symbols
        hist_prices = self.db.select_in(
            "daily_prices",
            "symbol",
            symbols,
            columns="symbol,trade_date,open_price,high_price,low_price,close_price,volume,traded_value,delivery_qty",
        )
        prices_by_sym: dict[str, list[dict[str, Any]]] = {}
        for hp in hist_prices:
            prices_by_sym.setdefault(hp["symbol"], []).append(hp)

        results: list[dict[str, Any]] = []
        for sym in symbols:
            p_bars = prices_by_sym.get(sym, [])
            # Filter up to target_date
            p_bars_filtered = [b for b in p_bars if str(b["trade_date"]) <= str(target_date)]
            if not p_bars_filtered:
                continue

            sec_index = sym_to_sector.get(sym, "NIFTY 500")
            s_bars = sector_by_index.get(sec_index, bench_rows)
            s_bars_filtered = [b for b in s_bars if str(b["trade_date"]) <= str(target_date)]
            b_bars_filtered = [b for b in bench_rows if str(b["trade_date"]) <= str(target_date)]
            ed_list = earnings_by_sym.get(sym, [])

            try:
                t_row = compute_technical_indicators(
                    symbol=sym,
                    target_date=target_date,
                    price_bars=p_bars_filtered,
                    benchmark_bars=b_bars_filtered,
                    sector_bars=s_bars_filtered,
                    earnings_dates=ed_list,
                )
                results.append(t_row.model_dump())
            except Exception as e:
                log.warning("tech_indicator_failed_sym", symbol=sym, error=str(e))
                continue

        if results:
            self.db.upsert("technical_indicators", results, on_conflict="symbol,trade_date")
            log.info("technicals_stored", count=len(results), target_date=str(target_date))

        return len(results)
