from datetime import datetime
from dataclasses import dataclass
from .enums import PositionSide


@dataclass(frozen=True, slots=True)
class Position:
    """Position represents net exposure for a symbol.

    ``position_side`` is a **derived property** computed from the sign
    of ``quantity``. It is not a constructor argument; callers must
    pass only ``entry_timestamp``, ``entry_price``, ``symbol``, and
    ``quantity``.

    Attributes:
        entry_timestamp: When the position was opened.
        entry_price: Price at which the position was opened.
        symbol: Trading symbol.
        quantity: Net quantity (positive = LONG, negative = SHORT, zero
            = FLAT).
    """
    entry_timestamp: datetime
    entry_price: float
    symbol: str
    quantity: float

    @property
    def position_side(self) -> PositionSide:
        """Derived from the sign of ``quantity``."""
        return _side_from_quantity(self.quantity)

    @classmethod
    def zero(cls, symbol: str) -> 'Position':
        """Create a zero/empty position for the given symbol.

        Returns a :class:`Position` with ``quantity=0.0`` and
        ``position_side=PositionSide.FLAT`` (derived in
        :meth:`__post_init__`), representing no active exposure. The
        other fields carry sensible defaults (``entry_timestamp`` is
        ``datetime.min``, ``entry_price`` is ``0.0``).
        """
        return cls(
            entry_timestamp=datetime.min,
            entry_price=0.0,
            symbol=symbol,
            quantity=0.0,
        )


def _side_from_quantity(quantity: float) -> PositionSide:
    """Map a signed net quantity to the corresponding :class:`PositionSide`.

    ``quantity > 0`` → LONG, ``quantity < 0`` → SHORT, ``quantity == 0``
    → FLAT. Exposed at module level so other modules (e.g. the position
    manager) can derive the same side without re-implementing the rule.
    """
    if quantity > 0:
        return PositionSide.LONG
    if quantity < 0:
        return PositionSide.SHORT
    return PositionSide.FLAT
