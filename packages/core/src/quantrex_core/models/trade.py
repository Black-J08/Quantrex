"""Trade record model for Quantrex framework.

Immutable record of a completed trade (position reduction).
"""

from dataclasses import dataclass
from datetime import datetime

from .enums import PositionSide


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """Immutable record of a completed trade.

    Created when a position's absolute quantity decreases (position moves closer to zero).

    Attributes:
        symbol: Trading symbol (e.g., "COPPER")
        side: LONG or SHORT (direction of the position being closed)
        quantity: Absolute quantity closed (always positive)
        entry_timestamp: When the position was originally opened
        entry_price: Price at which the position was originally opened
        exit_timestamp: When the position was closed (or reduced)
        exit_price: Price at which the position was closed (or reduced)
        pnl: Realized P&L for this trade portion
    """
    symbol: str
    side: PositionSide
    quantity: float
    entry_timestamp: datetime
    entry_price: float
    exit_timestamp: datetime
    exit_price: float
    pnl: float