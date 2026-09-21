"""Timeframe arithmetic utilities for Quantrex framework.

Provides functions for timeframe comparison, alignment to origin time,
and interval boundary calculations.
"""

from datetime import datetime, time
from typing import Optional

from quantrex_core.timeframe.parser import ParsedInterval, parse_interval


def align_to_origin(
    timestamp: datetime,
    origin_time: time,
    interval_minutes: int
) -> datetime:
    """Align a timestamp to the origin time for a given interval.

    Calculates the start of the interval that contains the given timestamp,
    using the market origin time as the reference point.

    Args:
        timestamp: The candle timestamp to align.
        origin_time: Market origin time (e.g., 09:15 for NSE).
        interval_minutes: Interval duration in minutes.

    Returns:
        Datetime representing the start of the interval.
    """
    # Convert timestamp to minutes since epoch (day 0)
    timestamp_minutes = (
        timestamp.hour * 60 +
        timestamp.minute +
        timestamp.day * 24 * 60
    )

    # Convert origin time to minutes
    origin_minutes = origin_time.hour * 60 + origin_time.minute

    # Calculate interval start relative to origin
    # Example: origin=09:15 (555), interval=60min, timestamp=10:15 (615)
    # (615 - 555) // 60 = 1, interval_start = 555 + 1*60 = 615 (10:15)
    interval_start_minutes = origin_minutes + (
        (timestamp_minutes - origin_minutes) // interval_minutes
    ) * interval_minutes

    # Convert back to datetime (preserve date from timestamp)
    days = interval_start_minutes // (24 * 60)
    minutes_of_day = interval_start_minutes % (24 * 60)
    hours = minutes_of_day // 60
    minutes = minutes_of_day % 60

    return timestamp.replace(
        hour=hours,
        minute=minutes,
        second=0,
        microsecond=0
    )


def get_interval_bounds(
    timestamp: datetime,
    origin_time: time,
    interval_minutes: int
) -> tuple[datetime, datetime]:
    """Get the start and end bounds of the interval containing a timestamp.

    Args:
        timestamp: The timestamp to find bounds for.
        origin_time: Market origin time.
        interval_minutes: Interval duration in minutes.

    Returns:
        Tuple of (interval_start, interval_end).
    """
    start = align_to_origin(timestamp, origin_time, interval_minutes)
    from datetime import timedelta
    end = start + timedelta(minutes=interval_minutes)
    return (start, end)


def is_interval_complete(
    timestamp: datetime,
    origin_time: time,
    interval_minutes: int,
    current_time: Optional[datetime] = None
) -> bool:
    """Check if an interval is complete (closed) at the given current time.

    An interval is complete if current_time >= interval_end.

    Args:
        timestamp: A timestamp within the interval (typically candle timestamp).
        origin_time: Market origin time.
        interval_minutes: Interval duration in minutes.
        current_time: Current execution time (defaults to now).

    Returns:
        True if the interval is complete/closed.
    """
    if current_time is None:
        current_time = datetime.now()

    _, interval_end = get_interval_bounds(timestamp, origin_time, interval_minutes)
    return current_time >= interval_end


def compare_timeframes(tf1: str, tf2: str) -> int:
    """Compare two timeframe intervals by duration.

    Args:
        tf1: First timeframe (e.g., "1H").
        tf2: Second timeframe (e.g., "15M").

    Returns:
        -1 if tf1 < tf2, 0 if equal, 1 if tf1 > tf2.
    """
    minutes1 = parse_interval(tf1).total_minutes
    minutes2 = parse_interval(tf2).total_minutes

    if minutes1 < minutes2:
        return -1
    elif minutes1 > minutes2:
        return 1
    return 0


def is_multiple_of(tf_smaller: str, tf_larger: str) -> bool:
    """Check if larger timeframe is an exact multiple of smaller timeframe.

    Args:
        tf_smaller: Smaller timeframe (e.g., "15M").
        tf_larger: Larger timeframe (e.g., "1H").

    Returns:
        True if tf_larger is an exact multiple of tf_smaller.
    """
    smaller_minutes = parse_interval(tf_smaller).total_minutes
    larger_minutes = parse_interval(tf_larger).total_minutes

    return larger_minutes % smaller_minutes == 0


def get_next_interval_start(
    timestamp: datetime,
    origin_time: time,
    interval_minutes: int
) -> datetime:
    """Get the start of the next interval after the one containing timestamp.

    Args:
        timestamp: Reference timestamp.
        origin_time: Market origin time.
        interval_minutes: Interval duration in minutes.

    Returns:
        Start of the next interval.
    """
    current_start = align_to_origin(timestamp, origin_time, interval_minutes)
    from datetime import timedelta
    return current_start + timedelta(minutes=interval_minutes)