from datetime import date
from typing import Any


class ValidationError(Exception):
    pass


def validate_ohlc(row: dict[str, Any]) -> list[str]:
    errs = []
    o, h, l, c = (row['open_price'], row['high_price'],
                  row['low_price'], row['close_price'])
    if not (l <= o <= h): errs.append('open outside [low, high]')
    if not (l <= c <= h): errs.append('close outside [low, high]')
    if row['volume'] < 0: errs.append('negative volume')
    if row['delivery_qty'] > row['volume']: errs.append('delivery > volume')
    if row['prev_close'] <= 0: errs.append('non-positive prev_close')
    return errs


def validate_symbol_in_universe(symbol: str, universe_symbols: set[str]) -> bool:
    return symbol in universe_symbols


def validate_trading_day(d: date, holidays) -> bool:
    from core.utils.trading_calendar import is_trading_day
    return is_trading_day(d, holidays)
