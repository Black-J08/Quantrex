"""Timeframe parsing utilities for the backtest engine.

Single source of truth for converting timeframe interval strings
(e.g., "1M", "5M", "1H", "4H", "1D", "1W") to durations.
"""

import re
from functools import lru_cache
from datetime import timedelta

_TIMEFRAME_PATTERN = re.compile(r"^(\d+)([MHDW])$")


@lru_cache(maxsize=32)
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
