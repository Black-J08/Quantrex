"""Candle filtering by timeframe for Quantrex framework.

Provides a single, shared implementation for filtering candles by timeframe interval.
Used by both backtest and live execution contexts.
"""

from datetime import time
from typing import Sequence

from quantrex_core.models import Candle
from quantrex_core.timeframe.parser import parse_interval
from quantrex_core.timeframe.arithmetic import align_to_origin


def filter_candles_by_timeframe(
    candles: Sequence[Candle],
    interval: str,
    origin_time: time
) -> tuple[Candle, ...]:
    """Filter candles by timeframe interval, returning the last candle of each completed interval.

    Groups candles into the specified interval using the origin time for correct alignment,
    and returns a tuple of the last candle from each completed interval (i.e., the "closed"
    candles for that timeframe).

    Args:
        candles: Sequence of candles in chronological order (oldest first).
        interval: Timeframe interval string (e.g., "1H", "4H", "1D", "15M").
        origin_time: Market origin time for interval alignment (e.g., 09:15 for NSE).

    Returns:
        Tuple of candles representing the last candle of each completed interval,
        in chronological order.

    Raises:
        ValueError: If interval format is invalid.
    """
    if not candles:
        return ()

    # Parse and validate interval
    parsed = parse_interval(interval)
    interval_minutes = parsed.total_minutes

    # Group candles by interval
    result = []
    current_interval_start = None
    current_interval_candles = []

    for candle in candles:
        # Calculate the interval start for this candle using origin time
        interval_start = align_to_origin(candle.timestamp, origin_time, interval_minutes)

        if current_interval_start is None:
            current_interval_start = interval_start
            current_interval_candles = [candle]
        elif interval_start == current_interval_start:
            current_interval_candles.append(candle)
        else:
            # Interval changed - add the last candle of the previous interval
            if current_interval_candles:
                result.append(current_interval_candles[-1])
            current_interval_start = interval_start
            current_interval_candles = [candle]

    # Add the last interval's last candle if it has candles
    if current_interval_candles:
        result.append(current_interval_candles[-1])

    return tuple(result)


def filter_candles_by_timeframe_minutes(
    candles: Sequence[Candle],
    interval_minutes: int,
    origin_time: time
) -> tuple[Candle, ...]:
    """Filter candles by timeframe using pre-computed interval minutes.

    Convenience function when interval_minutes is already known.

    Args:
        candles: Sequence of candles in chronological order.
        interval_minutes: Interval duration in minutes.
        origin_time: Market origin time for interval alignment.

    Returns:
        Tuple of candles representing the last candle of each completed interval.
    """
    if not candles:
        return ()

    result = []
    current_interval_start = None
    current_interval_candles = []

    for candle in candles:
        interval_start = align_to_origin(candle.timestamp, origin_time, interval_minutes)

        if current_interval_start is None:
            current_interval_start = interval_start
            current_interval_candles = [candle]
        elif interval_start == current_interval_start:
            current_interval_candles.append(candle)
        else:
            if current_interval_candles:
                result.append(current_interval_candles[-1])
            current_interval_start = interval_start
            current_interval_candles = [candle]

    if current_interval_candles:
        result.append(current_interval_candles[-1])

    return tuple(result)