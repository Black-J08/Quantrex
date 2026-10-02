"""Market data models for the trading framework."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from quantrex.core.models.base import Event
from quantrex.core.models.timeframe import Timeframe


@dataclass(slots=True, kw_only=True, frozen=True)
class OHLCVCandle(Event):
    """OHLCV bar/candle data.

    Attributes:
        symbol: Instrument symbol.
        timeframe: Bar timeframe (e.g., 1m, 1h, 1d).
        open: Opening price.
        high: Highest price.
        low: Lowest price.
        close: Closing price.
        volume: Trading volume.
    """

    symbol: str
    timeframe: Timeframe
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        """Validate bar fields."""
        if not self.symbol:
            raise ValueError("symbol cannot be empty")
        if self.open < 0:
            raise ValueError("open price cannot be negative")
        if self.high < 0:
            raise ValueError("high price cannot be negative")
        if self.low < 0:
            raise ValueError("low price cannot be negative")
        if self.close < 0:
            raise ValueError("close price cannot be negative")
        if self.volume < 0:
            raise ValueError("volume cannot be negative")
        if self.high < self.low:
            raise ValueError("high must be >= low")
        if self.high < self.open or self.high < self.close:
            raise ValueError("high must be >= open and close")
        if self.low > self.open or self.low > self.close:
            raise ValueError("low must be <= open and close")


@dataclass(slots=True, kw_only=True, frozen=True)
class Tick(Event):
    """Individual trade tick data.

    Attributes:
        symbol: Instrument symbol.
        price: Trade price.
    """

    symbol: str
    price: Decimal

    def __post_init__(self) -> None:
        """Validate tick fields."""
        if not self.symbol:
            raise ValueError("symbol cannot be empty")
        if self.price < 0:
            raise ValueError("price cannot be negative")