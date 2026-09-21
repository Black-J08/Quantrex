"""Interval string parsing and validation for Quantrex timeframes.

Provides functions to parse, validate, and convert timeframe interval strings
(e.g., "1H", "4H", "1D", "15M") to minutes and structured representations.
"""

import re
from typing import NamedTuple


class ParsedInterval(NamedTuple):
    """Parsed representation of a timeframe interval."""
    value: int
    unit: str  # 'M', 'H', 'D', 'W'
    total_minutes: int


# Pre-compiled regex for performance
_INTERVAL_PATTERN = re.compile(r'^(\d+)([MHDW])$', re.IGNORECASE)

# Unit to minutes conversion
_UNIT_TO_MINUTES = {
    'M': 1,
    'H': 60,
    'D': 60 * 24,
    'W': 60 * 24 * 7,
}

_VALID_UNITS = frozenset(_UNIT_TO_MINUTES.keys())


def parse_interval(interval: str) -> ParsedInterval:
    """Parse a timeframe interval string into its components.

    Args:
        interval: Timeframe string like "1H", "4H", "1D", "15M", "1W".

    Returns:
        ParsedInterval with value, unit, and total_minutes.

    Raises:
        ValueError: If interval format is invalid.
    """
    if not interval or not isinstance(interval, str):
        raise ValueError(f"Interval must be a non-empty string, got: {interval!r}")

    match = _INTERVAL_PATTERN.match(interval.strip().upper())
    if not match:
        raise ValueError(
            f"Invalid interval format: {interval!r}. "
            f"Expected format like '1H', '4H', '1D', '15M', '1W'. "
            f"Pattern: <number><unit> where unit is M, H, D, or W."
        )

    value = int(match.group(1))
    unit = match.group(2)

    if value <= 0:
        raise ValueError(f"Interval value must be positive, got: {value}")

    if unit not in _VALID_UNITS:
        raise ValueError(f"Invalid interval unit: {unit!r}. Valid units: {sorted(_VALID_UNITS)}")

    total_minutes = value * _UNIT_TO_MINUTES[unit]
    return ParsedInterval(value=value, unit=unit, total_minutes=total_minutes)


def interval_to_minutes(interval: str) -> int:
    """Convert a timeframe interval string to total minutes.

    Args:
        interval: Timeframe string like "1H", "4H", "1D", "15M".

    Returns:
        Total minutes for the interval.

    Raises:
        ValueError: If interval format is invalid.
    """
    return parse_interval(interval).total_minutes


def validate_interval(interval: str) -> bool:
    """Validate a timeframe interval string without raising.

    Args:
        interval: Timeframe string to validate.

    Returns:
        True if valid, False otherwise.
    """
    try:
        parse_interval(interval)
        return True
    except ValueError:
        return False


def get_supported_units() -> tuple[str, ...]:
    """Get the supported interval units.

    Returns:
        Tuple of supported unit characters ('M', 'H', 'D', 'W').
    """
    return tuple(sorted(_VALID_UNITS))