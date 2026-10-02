"""Trade models for the trading framework."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True, kw_only=True, frozen=True)
class Trade:
    """Trade model representing an executed trade.

    Attributes:
        id: Unique trade identifier.
        symbol: Instrument symbol.
        side: Trade side (BUY/SELL).
        quantity: Trade quantity.
        entry_price: Entry price.
        exit_price: Exit price.
        entry_time: Entry timestamp.
        exit_time: Exit timestamp.
        entry_reason: Entry Reason
        exit_reason: Exit Reason
        pnl: Realized profit/loss.
    """

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    entry_time: datetime
    exit_time: datetime
    entry_reason: str | None = None
    exit_reason: str | None = None
    pnl: Decimal

    def __post_init__(self) -> None:
        """Validate trade fields."""
        if not self.symbol:
            raise ValueError("symbol cannot be empty")
        if self.side not in ("BUY", "SELL"):
            raise ValueError("side must be 'BUY' or 'SELL'")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.entry_price < 0:
            raise ValueError("entry_price cannot be negative")
        if self.exit_price < 0:
            raise ValueError("exit_price cannot be negative")
        if self.entry_time.tzinfo is None:
            raise ValueError("entry_time must be timezone-aware")
        if self.exit_time.tzinfo is None:
            raise ValueError("exit_time must be timezone-aware")
        if self.exit_time < self.entry_time:
            raise ValueError("exit_time must be >= entry_time")