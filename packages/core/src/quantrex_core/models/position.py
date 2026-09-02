from datetime import datetime
from dataclasses import dataclass
from .enums import PositionSide


@dataclass(frozen=True, slots=True)
class Position:
    """Position represents net exposure for a symbol.

    ``position_side`` is a **derived** field: it is computed from the sign
    of ``quantity`` inside :meth:`__post_init__` and overwrites whatever
    the caller passed at construction time. The invariant is:

    * ``quantity > 0``  → :attr:`PositionSide.LONG`
    * ``quantity < 0``  → :attr:`PositionSide.SHORT`
    * ``quantity == 0`` → :attr:`PositionSide.FLAT`

    Callers MUST NOT rely on the constructor argument for
    ``position_side``; it is silently corrected to match ``quantity``.
    Direct assignment after construction is blocked by ``frozen=True``.

    Attributes:
        entry_timestamp: When the position was opened.
        entry_price: Price at which the position was opened.
        symbol: Trading symbol.
        quantity: Net quantity (positive = LONG, negative = SHORT, zero
            = FLAT).
        position_side: Derived from the sign of ``quantity`` in
            :meth:`__post_init__`. Will be :attr:`PositionSide.LONG`,
            :attr:`PositionSide.SHORT`, or :attr:`PositionSide.FLAT`.
    """
    entry_timestamp: datetime
    entry_price: float
    symbol: str
    quantity: float
    position_side: PositionSide

    def __post_init__(self) -> None:
        """Derive ``position_side`` from the sign of ``quantity``.

        Uses ``object.__setattr__`` to bypass the frozen-dataclass guard
        so the field can be corrected regardless of what the caller
        passed. This guarantees the invariant
        ``position_side == _side_from_quantity(quantity)`` always holds
        on every :class:`Position` instance.
        """
        object.__setattr__(self, 'position_side', _side_from_quantity(self.quantity))

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
            # position_side is overwritten by __post_init__ to FLAT.
            position_side=PositionSide.LONG,
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
