"""Data validation primitives for Quantrex."""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Set

from quantrex_core.logging import get_logger

logger = get_logger(__name__)

# Exchange calendar cache
_exchange_calendar_cache: Dict[str, Any] = {}


def _get_exchange_calendar(calendar_name: str):
    """Get exchange calendar from cache or create new one."""
    if calendar_name not in _exchange_calendar_cache:
        try:
            import exchange_calendars as xcals
            _exchange_calendar_cache[calendar_name] = xcals.get_calendar(calendar_name)
        except Exception as e:
            logger.warning("Failed to load exchange calendar %s: %s", calendar_name, e)
            return None
    return _exchange_calendar_cache[calendar_name]


REQUIRED_COLUMNS = {"datetime", "open", "high", "low", "close", "volume"}


def validate_data_format(rows: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """Validate that data rows have required columns and valid types.

    Args:
        rows: List of data row dictionaries.

    Returns:
        Tuple of (is_valid, error_messages).
    """
    errors = []

    if not rows:
        errors.append("No data rows provided")
        return False, errors

    # Check first row for required columns
    first_row = rows[0]
    missing_cols = REQUIRED_COLUMNS - set(first_row.keys())
    if missing_cols:
        errors.append(f"Missing required columns: {missing_cols}")

    # Validate each row
    for i, row in enumerate(rows):
        row_errors = _validate_row(row, i)
        errors.extend(row_errors)
        if len(errors) > 100:  # Limit error reporting
            errors.append(f"... and {len(rows) - i - 1} more rows")
            break

    return len(errors) == 0, errors


def _validate_row(row: Dict[str, Any], index: int) -> List[str]:
    """Validate a single data row."""
    errors = []

    # Check datetime
    dt_val = row.get("datetime")
    if dt_val is None:
        errors.append(f"Row {index}: missing datetime")
    elif not isinstance(dt_val, (str, datetime)):
        errors.append(f"Row {index}: datetime must be string or datetime, got {type(dt_val)}")

    # Check OHLCV values
    for col in ["open", "high", "low", "close", "volume"]:
        val = row.get(col)
        if val is None:
            errors.append(f"Row {index}: missing {col}")
        else:
            try:
                float_val = float(val)
                if col != "volume" and float_val <= 0:
                    errors.append(f"Row {index}: {col} must be positive, got {float_val}")
                if col == "volume" and float_val < 0:
                    errors.append(f"Row {index}: volume cannot be negative, got {float_val}")
            except (ValueError, TypeError):
                errors.append(f"Row {index}: {col} must be numeric, got {val}")

    # Validate OHLC relationships
    try:
        o, h, l, c = float(row.get("open", 0)), float(row.get("high", 0)), float(row.get("low", 0)), float(row.get("close", 0))
        if h < max(o, c):
            errors.append(f"Row {index}: high ({h}) < max(open, close) ({max(o, c)})")
        if l > min(o, c):
            errors.append(f"Row {index}: low ({l}) > min(open, close) ({min(o, c)})")
    except (ValueError, TypeError):
        pass  # Already caught above

    return errors


def validate_completeness(
    rows: List[Dict[str, Any]],
    expected_start: Optional[datetime] = None,
    expected_end: Optional[datetime] = None,
    expected_freq: Optional[str] = None,
    min_bars: int = 100,
    exchange_calendar: Optional[str] = None,
) -> Tuple[bool, List[str]]:
    """Validate data completeness (no gaps, sufficient bars).

    Args:
        rows: List of data row dictionaries.
        expected_start: Expected start datetime.
        expected_end: Expected end datetime.
        expected_freq: Expected frequency (e.g., "1M", "1H", "1D").
        min_bars: Minimum number of bars required.
        exchange_calendar: Optional exchange calendar name (e.g., "NSE", "BSE").
            If provided, validates timestamps against exchange trading sessions
            using the XBOM (BSE) calendar for both NSE and BSE.

    Returns:
        Tuple of (is_valid, warning_messages).
    """
    warnings = []

    if len(rows) < min_bars:
        warnings.append(f"Insufficient data: {len(rows)} bars (minimum {min_bars})")

    if not rows:
        return False, warnings

    # Check for datetime ordering and parse all datetimes
    datetimes = []
    for row in rows:
        dt_val = row.get("datetime")
        if isinstance(dt_val, str):
            # Try common formats
            for fmt in ("%Y%m%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    datetimes.append(datetime.strptime(dt_val, fmt))
                    break
                except ValueError:
                    continue
        elif isinstance(dt_val, datetime):
            datetimes.append(dt_val)

    if len(datetimes) != len(rows):
        warnings.append("Could not parse all datetime values")
        return True, warnings

    # Check ordering
    for i in range(1, len(datetimes)):
        if datetimes[i] <= datetimes[i - 1]:
            warnings.append(f"Data not strictly ordered at index {i}: {datetimes[i-1]} >= {datetimes[i]}")
            break

    # Check date range
    if exchange_calendar:
        # Calendar-aware date range check: compare against first/last expected trading minutes
        calendar = _get_exchange_calendar("XBOM")
        if calendar is not None:
            import pandas as pd
            cal_tz = str(calendar.tz) if hasattr(calendar, 'tz') else 'Asia/Kolkata'
            
            # Get first and last expected trading minutes in the expected range
            start_for_cal = expected_start if expected_start else datetimes[0]
            end_for_cal = expected_end if expected_end else datetimes[-1]
            
            # Convert to timezone-aware timestamps in calendar's timezone
            if start_for_cal.tzinfo is None:
                start_for_cal = pd.Timestamp(start_for_cal).tz_localize(cal_tz)
            else:
                start_for_cal = pd.Timestamp(start_for_cal).tz_convert(cal_tz)
            
            if end_for_cal.tzinfo is None:
                end_for_cal = pd.Timestamp(end_for_cal).tz_localize(cal_tz)
            else:
                end_for_cal = pd.Timestamp(end_for_cal).tz_convert(cal_tz)
            
            # Get all expected trading minutes from calendar for the date range
            try:
                expected_minutes = calendar.minutes_in_range(start_for_cal, end_for_cal)
            except Exception as e:
                logger.warning("Failed to get calendar minutes for date range check: %s", e)
                expected_minutes = []
            
            if len(expected_minutes) > 0:
                # First and last expected trading minutes
                first_expected = expected_minutes[0]
                last_expected = expected_minutes[-1]
                
                # Convert to naive UTC for comparison
                first_expected_utc = first_expected.tz_convert('UTC').tz_localize(None).to_pydatetime()
                last_expected_utc = last_expected.tz_convert('UTC').tz_localize(None).to_pydatetime()
                
                # Convert actual datetimes to naive UTC
                first_data_utc = datetimes[0]
                if first_data_utc.tzinfo is None:
                    first_data_utc = pd.Timestamp(first_data_utc).tz_localize(cal_tz).tz_convert('UTC').tz_localize(None).to_pydatetime()
                else:
                    first_data_utc = first_data_utc.astimezone().replace(tzinfo=None)
                
                last_data_utc = datetimes[-1]
                if last_data_utc.tzinfo is None:
                    last_data_utc = pd.Timestamp(last_data_utc).tz_localize(cal_tz).tz_convert('UTC').tz_localize(None).to_pydatetime()
                else:
                    last_data_utc = last_data_utc.astimezone().replace(tzinfo=None)
                
                # Check if data starts after first expected trading minute
                if first_data_utc > first_expected_utc:
                    warnings.append(f"Data starts after expected start: {first_data_utc} > {first_expected_utc}")
                # Check if data ends before last expected trading minute
                if last_data_utc < last_expected_utc:
                    warnings.append(f"Data ends before expected end: {last_data_utc} < {last_expected_utc}")
    else:
        # Non-calendar-aware date range check (original behavior)
        if expected_start and datetimes[0] > expected_start:
            warnings.append(f"Data starts after expected start: {datetimes[0]} > {expected_start}")
        if expected_end and datetimes[-1] < expected_end:
            warnings.append(f"Data ends before expected end: {datetimes[-1]} < {expected_end}")

    # Check for gaps
    if exchange_calendar:
        # Calendar-aware gap detection using XBOM (BSE) calendar for both NSE and BSE
        _validate_gaps_with_calendar(datetimes, expected_start, expected_end, warnings)
    elif expected_freq and len(datetimes) > 1:
        # Fallback: frequency-based gap detection (for crypto, forex, etc.)
        freq_minutes = _parse_freq_to_minutes(expected_freq)
        if freq_minutes:
            expected_diff = freq_minutes * 60  # seconds
            for i in range(1, len(datetimes)):
                actual_diff = (datetimes[i] - datetimes[i - 1]).total_seconds()
                if actual_diff > expected_diff * 1.5:  # Allow 50% tolerance
                    warnings.append(f"Possible gap at index {i}: {actual_diff/60:.1f} min vs expected {freq_minutes} min")

    return True, warnings


def _validate_gaps_with_calendar(
    datetimes: List[datetime],
    expected_start: Optional[datetime],
    expected_end: Optional[datetime],
    warnings: List[str],
) -> None:
    """Validate gaps using exchange calendar (XBOM for both NSE and BSE)."""
    if not datetimes:
        return

    # Use XBOM calendar for both NSE and BSE
    calendar = _get_exchange_calendar("XBOM")
    if calendar is None:
        logger.warning("XBOM calendar unavailable, skipping calendar-aware gap validation")
        return

    # Determine validation range - use calendar's timezone for accurate session detection
    # The calendar expects datetimes in its timezone (Asia/Kolkata for XBOM)
    import pandas as pd
    cal_tz = str(calendar.tz) if hasattr(calendar, 'tz') else 'Asia/Kolkata'
    
    start = expected_start if expected_start else datetimes[0]
    end = expected_end if expected_end else datetimes[-1]
    
    # Convert to timezone-aware timestamps in calendar's timezone
    if start.tzinfo is None:
        start = pd.Timestamp(start).tz_localize(cal_tz)
    else:
        start = pd.Timestamp(start).tz_convert(cal_tz)
    
    if end.tzinfo is None:
        end = pd.Timestamp(end).tz_localize(cal_tz)
    else:
        end = pd.Timestamp(end).tz_convert(cal_tz)

    # Get all expected trading minutes from calendar for the date range
    try:
        expected_minutes = calendar.minutes_in_range(start, end)
    except Exception as e:
        logger.warning("Failed to get calendar minutes: %s", e)
        return

    if len(expected_minutes) == 0:
        return

    # Convert actual datetimes to naive UTC for comparison
    # Data from Indian exchanges (NSE/BSE) is in IST but parsed as naive
    # We need to treat naive datetimes as IST and convert to UTC for comparison
    actual_set: Set[datetime] = set()
    for dt in datetimes:
        if dt.tzinfo is None:
            # Data from NSE/BSE is in IST - localize to IST then convert to UTC
            actual_set.add(pd.Timestamp(dt).tz_localize(cal_tz).tz_convert('UTC').tz_localize(None).to_pydatetime())
        else:
            # Convert to UTC then make naive
            actual_set.add(dt.astimezone().replace(tzinfo=None))

    # Convert expected minutes to naive UTC for comparison
    expected_set: Set[datetime] = set()
    for m in expected_minutes:
        # m is a pandas Timestamp with UTC timezone
        if hasattr(m, 'tzinfo') and m.tzinfo is not None:
            # Convert to UTC then make naive
            expected_set.add(m.tz_convert('UTC').tz_localize(None).to_pydatetime())
        else:
            expected_set.add(m.to_pydatetime() if hasattr(m, 'to_pydatetime') else m)

    # Find missing minutes (expected but not in actual)
    missing = expected_set - actual_set
    if missing:
        # Group consecutive missing minutes into ranges
        sorted_missing = sorted(missing)
        gap_start = sorted_missing[0]
        prev = sorted_missing[0]
        
        for curr in sorted_missing[1:]:
            if (curr - prev).total_seconds() > 60:  # Not consecutive
                gap_end = prev
                if gap_start == gap_end:
                    warnings.append(f"Missing bar at {gap_start.strftime('%Y-%m-%d %H:%M')} (market hours)")
                else:
                    warnings.append(f"Missing bars from {gap_start.strftime('%Y-%m-%d %H:%M')} to {gap_end.strftime('%Y-%m-%d %H:%M')} (market hours)")
                gap_start = curr
            prev = curr
        
        # Last gap
        gap_end = prev
        if gap_start == gap_end:
            warnings.append(f"Missing bar at {gap_start.strftime('%Y-%m-%d %H:%M')} (market hours)")
        else:
            warnings.append(f"Missing bars from {gap_start.strftime('%Y-%m-%d %H:%M')} to {gap_end.strftime('%Y-%m-%d %H:%M')} (market hours)")


def _parse_freq_to_minutes(freq: str) -> Optional[int]:
    """Parse frequency string to minutes."""
    import re
    match = re.match(r'^(\d+)([MHDW])$', freq.upper())
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    if unit == 'M':
        return value
    elif unit == 'H':
        return value * 60
    elif unit == 'D':
        return value * 60 * 24
    elif unit == 'W':
        return value * 60 * 24 * 7
    return None


def check_timestamp_alignment(
    symbol_data: Dict[str, List[Dict[str, Any]]],
    tolerance_seconds: int = 60,
) -> Tuple[bool, List[str]]:
    """Check that all symbols have aligned timestamps.

    Args:
        symbol_data: Dictionary mapping symbol to list of data rows.
        tolerance_seconds: Maximum allowed timestamp difference.

    Returns:
        Tuple of (is_aligned, warning_messages).
    """
    warnings = []

    if not symbol_data:
        return True, warnings

    # Get reference timestamps from first symbol
    first_symbol = next(iter(symbol_data))
    ref_timestamps = []
    for row in symbol_data[first_symbol]:
        dt_val = row.get("datetime")
        if isinstance(dt_val, str):
            for fmt in ("%Y%m%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    ref_timestamps.append(datetime.strptime(dt_val, fmt))
                    break
                except ValueError:
                    continue
        elif isinstance(dt_val, datetime):
            ref_timestamps.append(dt_val)

    # Check each other symbol
    for symbol, rows in symbol_data.items():
        if symbol == first_symbol:
            continue

        sym_timestamps = []
        for row in rows:
            dt_val = row.get("datetime")
            if isinstance(dt_val, str):
                for fmt in ("%Y%m%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        sym_timestamps.append(datetime.strptime(dt_val, fmt))
                        break
                    except ValueError:
                        continue
            elif isinstance(dt_val, datetime):
                sym_timestamps.append(dt_val)

        if len(sym_timestamps) != len(ref_timestamps):
            warnings.append(f"Symbol {symbol}: different number of bars ({len(sym_timestamps)} vs {len(ref_timestamps)})")
            continue

        for i, (ref_ts, sym_ts) in enumerate(zip(ref_timestamps, sym_timestamps)):
            diff = abs((ref_ts - sym_ts).total_seconds())
            if diff > tolerance_seconds:
                warnings.append(f"Symbol {symbol}: timestamp misalignment at index {i}: {diff:.1f}s diff")
                break

    return len(warnings) == 0, warnings