"""Zerodha-internal data models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum


class ZerodhaInterval(str, Enum):
    """Zerodha historical data intervals."""

    MINUTE = "minute"
    THREE_MINUTE = "3minute"
    FIVE_MINUTE = "5minute"
    TEN_MINUTE = "10minute"
    FIFTEEN_MINUTE = "15minute"
    THIRTY_MINUTE = "30minute"
    SIXTY_MINUTE = "60minute"
    DAY = "day"


@dataclass(slots=True, frozen=True)
class InstrumentToken:
    """Zerodha instrument token."""

    value: int

    def __str__(self) -> str:
        return str(self.value)


@dataclass(slots=True, frozen=True)
class RawCandle:
    """Raw candle data from Zerodha API.

    Format: [timestamp, open, high, low, close, volume]
    Optional: [timestamp, open, high, low, close, volume, oi]
    """

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    oi: Decimal | None = None

    @classmethod
    def from_api_response(cls, data: list) -> RawCandle:
        """Create RawCandle from Zerodha API response array."""
        if len(data) < 6:
            raise ValueError(f"Invalid candle data: expected at least 6 elements, got {len(data)}")

        # Parse timestamp - Zerodha returns ISO format with timezone
        ts_str = data[0]
        if isinstance(ts_str, str):
            timestamp = datetime.fromisoformat(ts_str)
        else:
            timestamp = datetime.fromtimestamp(ts_str, tz=UTC)

        return cls(
            timestamp=timestamp,
            open=Decimal(str(data[1])),
            high=Decimal(str(data[2])),
            low=Decimal(str(data[3])),
            close=Decimal(str(data[4])),
            volume=Decimal(str(data[5])),
            oi=Decimal(str(data[6])) if len(data) > 6 and data[6] is not None else None,
        )


@dataclass(slots=True, frozen=True)
class SymbolMapping:
    """Mapping from trading symbol to Zerodha instrument token."""

    symbol: str  # e.g., "NSE:INFY"
    instrument_token: InstrumentToken
    exchange: str
    tradingsymbol: str
