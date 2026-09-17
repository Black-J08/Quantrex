"""Data validation primitives for Quantrex."""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from quantrex_core.logging import get_logger

logger = get_logger(__name__)


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
) -> Tuple[bool, List[str]]:
    """Validate data completeness (no gaps, sufficient bars).

    Args:
        rows: List of data row dictionaries.
        expected_start: Expected start datetime.
        expected_end: Expected end datetime.
        expected_freq: Expected frequency (e.g., "1M", "1H", "1D").
        min_bars: Minimum number of bars required.

    Returns:
        Tuple of (is_valid, warning_messages).
    """
    warnings = []

    if len(rows) < min_bars:
        warnings.append(f"Insufficient data: {len(rows)} bars (minimum {min_bars})")

    if not rows:
        return False, warnings

    # Check for datetime ordering
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
    if expected_start and datetimes[0] > expected_start:
        warnings.append(f"Data starts after expected start: {datetimes[0]} > {expected_start}")
    if expected_end and datetimes[-1] < expected_end:
        warnings.append(f"Data ends before expected end: {datetimes[-1]} < {expected_end}")

    # Check for gaps (if frequency specified)
    if expected_freq and len(datetimes) > 1:
        freq_minutes = _parse_freq_to_minutes(expected_freq)
        if freq_minutes:
            expected_diff = freq_minutes * 60  # seconds
            for i in range(1, len(datetimes)):
                actual_diff = (datetimes[i] - datetimes[i - 1]).total_seconds()
                if actual_diff > expected_diff * 1.5:  # Allow 50% tolerance
                    warnings.append(f"Possible gap at index {i}: {actual_diff/60:.1f} min vs expected {freq_minutes} min")

    return True, warnings


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