"""Signal models for the trading framework."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from quantrex.core.models.base import Event


class SignalType(Enum):
    """Signal type enumeration."""

    ENTRY_LONG = "ENTRY_LONG"
    ENTRY_SHORT = "ENTRY_SHORT"
    EXIT_LONG = "EXIT_LONG"
    EXIT_SHORT = "EXIT_SHORT"


@dataclass(slots=True, kw_only=True, frozen=True)
class Signal(Event):
    """Signal model representing a trading signal from a strategy.

    Attributes:
        symbol: Instrument symbol.
        signal_type: Type of signal (ENTRY_LONG, ENTRY_SHORT, EXIT_LONG, EXIT_SHORT).
        price: Signal price reference.
        quantity: Suggested quantity.
    """

    symbol: str
    signal_type: SignalType
    price: Decimal
    quantity: Decimal | None = None

    def __post_init__(self) -> None:
        """Validate signal fields."""
        if not self.symbol:
            raise ValueError("symbol cannot be empty")
        if self.price < 0:
            raise ValueError("price cannot be negative")
        if self.quantity is not None and self.quantity <= 0:
            raise ValueError("quantity must be positive if provided")