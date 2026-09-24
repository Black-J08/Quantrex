"""Candle data model for Quantrex framework.

Immutable OHLCV candle with timestamp and symbol, shared across all execution environments.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Mapping


def _parse_interval(interval: str):
    """Parse a timeframe interval string into its components (local copy to avoid circular import)."""
    import re
    _INTERVAL_PATTERN = re.compile(r'^(\d+)([MHDW])$', re.IGNORECASE)
    _UNIT_TO_MINUTES = {
        'M': 1,
        'H': 60,
        'D': 60 * 24,
        'W': 60 * 24 * 7,
    }
    
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

    if unit not in _UNIT_TO_MINUTES:
        raise ValueError(f"Invalid interval unit: {unit!r}. Valid units: {sorted(_UNIT_TO_MINUTES.keys())}")

    total_minutes = value * _UNIT_TO_MINUTES[unit]
    
    class ParsedInterval:
        def __init__(self, value, unit, total_minutes):
            self.value = value
            self.unit = unit
            self.total_minutes = total_minutes
    
    return ParsedInterval(value=value, unit=unit, total_minutes=total_minutes)


@dataclass(frozen=True, slots=True)
class Candle:
    """Immutable OHLCV candle with timestamp and symbol.

    Attributes:
        symbol: Trading symbol (e.g., "COPPER")
        timestamp: Candle open time (naive datetime, assumed UTC)
        close_time: Candle close time (open time + timeframe duration)
        timeframe: Timeframe interval (e.g., "1M", "1H", "1D")
        open: Opening price
        high: Highest price
        low: Lowest price
        close: Closing price
        volume: Trading volume
        indicators: Read-only mapping of precomputed indicator name -> value
            for this bar. Defaults to empty. The mapping is wrapped in
            ``types.MappingProxyType`` at construction time, so attempting
            to mutate it (e.g. ``candle.indicators["x"] = 1``) raises
            ``TypeError`` while dict-style reads remain ergonomic.
            Values must be ``float``, ``int``, or ``None``.
    """

    symbol: str
    timestamp: datetime
    close_time: datetime
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    indicators: Mapping[str, float | int | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate close_time and wrap indicators in MappingProxyType.

        Validates that close_time equals timestamp + timeframe duration.
        Wraps indicators in MappingProxyType for runtime immutability.
        """
        # Validate close_time matches timestamp + timeframe
        parsed = _parse_interval(self.timeframe)
        expected_close = self.timestamp + timedelta(minutes=parsed.total_minutes)
        if self.close_time != expected_close:
            raise ValueError(
                f"close_time {self.close_time} does not match timestamp {self.timestamp} "
                f"+ timeframe {self.timeframe} (expected {expected_close})"
            )

        if not isinstance(self.indicators, MappingProxyType):
            object.__setattr__(self, "indicators", MappingProxyType(dict(self.indicators)))

    @classmethod
    def from_row(
        cls,
        row: dict,
        symbol: str,
        timeframe: str,
        datetime_format: str = "%Y%m%d %H:%M",
        *,
        indicators: Mapping[str, float | int | None] | None = None,
    ) -> "Candle":
        """Create a Candle from a raw data row dictionary.

        Args:
            row: Dictionary with keys 'datetime', 'open', 'high', 'low', 'close', 'volume'
            symbol: Trading symbol
            timeframe: Timeframe interval (e.g., "1M", "1H", "1D")
            datetime_format: Format string for parsing the datetime field
            indicators: Optional read-only mapping of precomputed indicator
                name -> value for this bar. Defaults to an empty mapping.
                Anything passed here will be wrapped in
                ``types.MappingProxyType`` by ``__post_init__`` so callers
                cannot mutate the per-bar indicator bag after construction.

        Returns:
            Candle instance with parsed values.

        Raises:
            ValueError: If required keys are missing, values cannot be parsed,
                or timeframe format is invalid.
        """
        try:
            dt_val = row["datetime"]
            # Handle pandas Timestamp objects (from Parquet cache)
            if hasattr(dt_val, 'strftime'):
                timestamp = dt_val.to_pydatetime()
            else:
                timestamp = datetime.strptime(dt_val, datetime_format)

            # Compute close_time from timestamp + timeframe
            parsed = _parse_interval(timeframe)
            close_time = timestamp + timedelta(minutes=parsed.total_minutes)

            return cls(
                symbol=symbol,
                timestamp=timestamp,
                close_time=close_time,
                timeframe=timeframe,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                indicators={} if indicators is None else dict(indicators),
            )
        except KeyError as e:
            raise ValueError(f"Missing required key in row: {e}") from e
        except (ValueError, TypeError) as e:
            raise ValueError(f"Failed to parse row values: {e}") from e