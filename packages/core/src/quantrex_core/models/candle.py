"""Candle data model for Quantrex framework.

Immutable OHLCV candle with timestamp and symbol, shared across all execution environments.
"""

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class Candle:
    """Immutable OHLCV candle with timestamp and symbol.

    Attributes:
        symbol: Trading symbol (e.g., "COPPER")
        timestamp: Candle timestamp (naive datetime, assumed UTC)
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
    open: float
    high: float
    low: float
    close: float
    volume: float
    indicators: Mapping[str, float | int | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Wrap ``indicators`` in a MappingProxyType for runtime immutability.

        The dataclass is ``frozen=True`` so the field *binding* cannot be
        reassigned, but a plain ``dict`` value would still allow item
        mutation. ``MappingProxyType`` gives us a read-only view that
        preserves dict-style reads while blocking writes with ``TypeError``.
        """
        if not isinstance(self.indicators, MappingProxyType):
            object.__setattr__(self, "indicators", MappingProxyType(dict(self.indicators)))

    @classmethod
    def from_row(
        cls,
        row: dict,
        symbol: str,
        datetime_format: str = "%Y%m%d %H:%M",
        *,
        indicators: Mapping[str, float | int | None] | None = None,
    ) -> "Candle":
        """Create a Candle from a raw data row dictionary.

        Args:
            row: Dictionary with keys 'datetime', 'open', 'high', 'low', 'close', 'volume'
            symbol: Trading symbol
            datetime_format: Format string for parsing the datetime field
            indicators: Optional read-only mapping of precomputed indicator
                name -> value for this bar. Defaults to an empty mapping.
                Anything passed here will be wrapped in
                ``types.MappingProxyType`` by ``__post_init__`` so callers
                cannot mutate the per-bar indicator bag after construction.

        Returns:
            Candle instance with parsed values.

        Raises:
            ValueError: If required keys are missing or values cannot be parsed.
        """
        try:
            timestamp = datetime.strptime(row["datetime"], datetime_format)
            return cls(
                symbol=symbol,
                timestamp=timestamp,
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