from typing import Protocol
from ..models.enums import OrderSide, OrderType
from ..models.order import Order
from ..models.position import Position


class StrategyContext(Protocol):
    """Single researcher-facing facade for Strategy–Engine interaction."""

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
    ) -> Order:
        """Submit a MARKET order. Returns Order with status ACCEPTED/REJECTED.
        Order accepted immediately; net position updated synchronously.
        Order recorded for audit trail only."""
        ...

    def get_position(self, symbol: str) -> Position:
        """Get current net position for symbol. Returns zero Position if none."""
        ...
