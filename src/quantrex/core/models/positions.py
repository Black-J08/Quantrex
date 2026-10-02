"""Position models for the trading framework."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum


class PositionSide(Enum):
    """Position side enumeration."""

    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(slots=True, kw_only=True, frozen=True)
class Position:
    """Position model representing an open position.

    Attributes:
        id: Unique position identifier.
        symbol: Instrument symbol.
        side: Position side (LONG/SHORT).
        quantity: Position quantity (negative for SHORT).
        entry_price: Average entry price.
        current_price: Current market price.
        unrealized_pnl: Unrealized profit/loss.
        entry_time: Position open timestamp.
    """

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    symbol: str
    side: PositionSide
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    entry_time: datetime = field(
        default_factory=lambda: datetime.now().astimezone()
    )

    def __post_init__(self) -> None:
        """Validate position fields."""
        if not self.symbol:
            raise ValueError("symbol cannot be empty")
        if self.side == PositionSide.LONG and self.quantity <= 0:
            raise ValueError("quantity must be positive for LONG position")
        if self.side == PositionSide.SHORT and self.quantity >= 0:
            raise ValueError("quantity must be negative for SHORT position")
        if self.entry_price < 0:
            raise ValueError("entry_price cannot be negative")
        if self.current_price < 0:
            raise ValueError("current_price cannot be negative")
        if self.entry_time.tzinfo is None:
            raise ValueError("entry_time must be timezone-aware UTC")