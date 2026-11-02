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


# SymbolMapping removed: unused pass-through wrapper that added no value
# over a plain dict or tuple. Use (symbol, instrument_token, exchange,
# tradingsymbol) directly where needed.
