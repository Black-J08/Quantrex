"""Candle data model for backtest engine."""

from dataclasses import dataclass
from datetime import datetime


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
    """

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def from_row(cls, row: dict, symbol: str, datetime_format: str = "%Y%m%d %H:%M") -> "Candle":
        """Create a Candle from a raw data row dictionary.

        Args:
            row: Dictionary with keys 'datetime', 'open', 'high', 'low', 'close', 'volume'
            symbol: Trading symbol
            datetime_format: Format string for parsing the datetime field

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
            )
        except KeyError as e:
            raise ValueError(f"Missing required key in row: {e}") from e
        except (ValueError, TypeError) as e:
            raise ValueError(f"Failed to parse row values: {e}") from e