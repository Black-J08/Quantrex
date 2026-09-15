"""Timeframe parsing utilities for the backtest engine.

Single source of truth for converting timeframe interval strings
(e.g., "1M", "5M", "1H", "4H", "1D", "1W") to durations. Used by both
the engine (execution timing) and the strategy context (history
completion filtering) so the two can never diverge.
"""

import re
from datetime import timedelta

_TIMEFRAME_PATTERN = re.compile(r"^(\d+)([MHDW])$")


def parse_timeframe_to_timedelta(timeframe: str) -> timedelta | None:
    """Parse a timeframe string into its duration.

    Args:
        timeframe: Timeframe string like "1M", "5M", "1H", "4H", "1D", "1W".

    Returns:
        The timeframe duration, or ``None`` if the format is invalid.
    """
    match = _TIMEFRAME_PATTERN.match(timeframe.upper())
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if unit == "M":
        return timedelta(minutes=value)
    elif unit == "H":
        return timedelta(hours=value)
    elif unit == "D":
        return timedelta(days=value)
    else:  # 'W'
        return timedelta(weeks=value)


def calculate_close_time(open_time, timeframe: str):
    """Calculate the close time for a candle given its open time and timeframe.

    Args:
        open_time: The candle's open time (period start).
        timeframe: Timeframe string (e.g., "1M", "5M", "1H", "1D").

    Returns:
        The candle's close time (period end). Falls back to a 1-minute
        duration if the timeframe format is invalid.
    """
    from datetime import datetime

    duration = parse_timeframe_to_timedelta(timeframe)
    if duration is None:
        duration = timedelta(minutes=1)
    assert isinstance(open_time, datetime)
    return open_time + duration
