from datetime import datetime
from dataclasses import dataclass
from .enums import PositionSide


@dataclass(frozen=True, slots=True)
class Position:
    """Position represents net exposure for a symbol.

    Attributes:
        entry_timestamp: When the position was opened.
        entry_price: Price at which the position was opened.
        symbol: Trading symbol.
        quantity: Net quantity (positive = LONG, negative = SHORT).
        position_side: LONG or SHORT side.
    """
    entry_timestamp: datetime
    entry_price: float
    symbol: str
    quantity: float
    position_side: PositionSide

    @classmethod
    def zero(cls, symbol: str) -> 'Position':
        """Create a zero/empty position for the given symbol.

        Returns a Position with quantity=0 and sensible defaults
        for the other fields, representing no active exposure.
        """
        return cls(
            entry_timestamp=datetime.min,
            entry_price=0.0,
            symbol=symbol,
            quantity=0.0,
            position_side=PositionSide.LONG,
        )