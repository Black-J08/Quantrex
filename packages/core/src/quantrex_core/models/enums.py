from enum import Enum

class PositionSide(Enum):
    """Net position side, derived from the sign of :attr:`Position.quantity`.

    * ``LONG`` — net quantity > 0.
    * ``SHORT`` — net quantity < 0.
    * ``FLAT`` — net quantity == 0 (no exposure). Returned by
      :meth:`Position.zero` and by the fast-path of
      :meth:`quantrex_core.position.PositionManager.get_position` for
      symbols with no live map entry.
    """

    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"

class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    MARKET = "MARKET"


class OrderStatus(Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"