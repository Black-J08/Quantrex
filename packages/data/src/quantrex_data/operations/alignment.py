"""Timestamp alignment operations for Quantrex."""

from datetime import datetime, time, timedelta
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd

from quantrex_core.logging import get_logger

logger = get_logger(__name__)


# Exchange calendars (simplified - in production would use a proper calendar library)
EXCHANGE_CALENDARS = {
    "NSE": {
        "market_open": time(9, 15),
        "market_close": time(15, 30),
        "timezone": "Asia/Kolkata",
    },
    "NYSE": {
        "market_open": time(9, 30),
        "market_close": time(16, 0),
        "timezone": "America/New_York",
    },
}


def align_to_exchange_calendar(
    data: List[Dict[str, Any]],
    exchange: str = "NSE",
    timeframe: str = "1M",
) -> List[Dict[str, Any]]:
    """Align timestamps to exchange trading hours.

    Args:
        data: List of data rows with datetime.
        exchange: Exchange code (NSE, NYSE).
        timeframe: Timeframe interval.

    Returns:
        Filtered data with only exchange-hours timestamps.
    """
    if exchange not in EXCHANGE_CALENDARS:
        logger.warning("Unknown exchange %s, skipping alignment", exchange)
        return data

    calendar = EXCHANGE_CALENDARS[exchange]
    market_open = calendar["market_open"]
    market_close = calendar["market_close"]

    aligned = []
    for row in data:
        dt_val = row.get("datetime")
        dt = None
        if isinstance(dt_val, str):
            for fmt in ("%Y%m%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    dt = datetime.strptime(dt_val, fmt)
                    break
                except ValueError:
                    continue
        elif isinstance(dt_val, datetime):
            dt = dt_val
        else:
            continue

        # Check if dt was successfully parsed
        if dt is None:
            continue

        # Check if within market hours
        if market_open <= dt.time() <= market_close:
            aligned.append(row)

    logger.info("Aligned %d rows to %s calendar (%d kept)", len(data), exchange, len(aligned))
    return aligned


def resample_to_timeframe(
    data: List[Dict[str, Any]],
    source_timeframe: str,
    target_timeframe: str,
    origin_time: time = time(9, 15),
) -> List[Dict[str, Any]]:
    """Resample data from source timeframe to target timeframe.

    Args:
        data: List of data rows (must be sorted by datetime).
        source_timeframe: Source timeframe (e.g., "1M").
        target_timeframe: Target timeframe (e.g., "5M", "1H", "1D").
        origin_time: Market open time for alignment.

    Returns:
        Resampled data rows.
    """
    if not data:
        return []

    if source_timeframe == target_timeframe:
        return data

    # Convert to DataFrame for resampling
    df = pd.DataFrame(data)

    # Parse datetime
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime")

    # Ensure numeric columns
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Parse timeframes to pandas frequency
    source_freq = _timeframe_to_pandas_freq(source_timeframe)
    target_freq = _timeframe_to_pandas_freq(target_timeframe)

    if not source_freq or not target_freq:
        logger.warning("Invalid timeframe: %s -> %s", source_timeframe, target_timeframe)
        return data

    # Resample
    try:
        resampled = df.resample(target_freq, origin=origin_time.strftime("%H:%M")).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna()

        # Convert back to list of dicts
        resampled = resampled.reset_index()
        resampled["datetime"] = resampled["datetime"].dt.strftime("%Y%m%d %H:%M")

        result = resampled.to_dict("records")
        logger.info("Resampled %d rows from %s to %s (%d output)", len(data), source_timeframe, target_timeframe, len(result))
        return result

    except Exception as e:
        logger.exception("Resampling failed: %s", e)
        return data


def _timeframe_to_pandas_freq(timeframe: str) -> Optional[str]:
    """Convert timeframe string to pandas frequency string."""
    import re
    match = re.match(r'^(\d+)([MHDW])$', timeframe.upper())
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if unit == 'M':
        return f"{value}min"
    elif unit == 'H':
        return f"{value}H"
    elif unit == 'D':
        return f"{value}D"
    elif unit == 'W':
        return f"{value}W"
    return None


def synchronize_symbols(
    symbol_data: Dict[str, List[Dict[str, Any]]],
    exchange: str = "NSE",
    timeframe: str = "1M",
) -> Dict[str, List[Dict[str, Any]]]:
    """Synchronize multiple symbols to common timestamp index.

    Args:
        symbol_data: Dict mapping symbol to list of data rows.
        exchange: Exchange code for calendar alignment.
        timeframe: Base timeframe.

    Returns:
        Dict with synchronized data (same timestamps across symbols).
    """
    if not symbol_data:
        return {}

    # First, align each symbol to exchange calendar
    aligned_data = {}
    for symbol, data in symbol_data.items():
        aligned_data[symbol] = align_to_exchange_calendar(data, exchange, timeframe)

    # Find common timestamp index - normalize timestamps to strings for comparison
    all_timestamps = set()
    for data in aligned_data.values():
        timestamps = set()
        for row in data:
            dt_val = row.get("datetime")
            if isinstance(dt_val, str):
                timestamps.add(dt_val)
            elif isinstance(dt_val, datetime):
                # Convert datetime to string in standard format
                timestamps.add(dt_val.strftime("%Y-%m-%d %H:%M:%S"))
        all_timestamps.update(timestamps)

    common_timestamps = sorted(all_timestamps)

    # Filter each symbol to common timestamps
    synchronized = {}
    for symbol, data in aligned_data.items():
        data_by_ts = {}
        for row in data:
            dt_val = row.get("datetime")
            if isinstance(dt_val, str):
                data_by_ts[dt_val] = row
            elif isinstance(dt_val, datetime):
                data_by_ts[dt_val.strftime("%Y-%m-%d %H:%M:%S")] = row
        
        synchronized[symbol] = [data_by_ts[ts] for ts in common_timestamps if ts in data_by_ts]

    logger.info("Synchronized %d symbols to %d common timestamps", len(symbol_data), len(common_timestamps))
    return synchronized


def create_common_time_index(
    symbol_data: Dict[str, List[Dict[str, Any]]],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    freq: str = "1min",
) -> List[datetime]:
    """Create a common time index for all symbols.

    Args:
        symbol_data: Dict mapping symbol to list of data rows.
        start: Start datetime (None = earliest in data).
        end: End datetime (None = latest in data).
        freq: Frequency string for pandas date_range.

    Returns:
        List of datetime objects representing the common time index.
    """
    all_timestamps = []

    for data in symbol_data.values():
        for row in data:
            dt_val = row.get("datetime")
            if isinstance(dt_val, str):
                for fmt in ("%Y%m%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        all_timestamps.append(datetime.strptime(dt_val, fmt))
                        break
                    except ValueError:
                        continue
            elif isinstance(dt_val, datetime):
                all_timestamps.append(dt_val)

    if not all_timestamps:
        return []

    min_ts = min(all_timestamps) if start is None else start
    max_ts = max(all_timestamps) if end is None else end

    # Generate common index
    common_index = pd.date_range(start=min_ts, end=max_ts, freq=freq)
    return common_index.tolist()