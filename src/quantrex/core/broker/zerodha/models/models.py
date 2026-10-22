"""Zerodha-internal data models."""

from __future__ import annotations

from dataclasses import dataclass
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
class SymbolMapping:
    """Mapping from trading symbol to Zerodha instrument token."""

    symbol: str  # e.g., "NSE:INFY"
    instrument_token: InstrumentToken
    exchange: str
    tradingsymbol: str
