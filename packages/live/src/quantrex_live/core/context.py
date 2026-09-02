from datetime import datetime
from quantrex_core.models.enums import OrderType, OrderSide
from quantrex_core.models.order import Order
from quantrex_core.models.position import Position
from quantrex_core.position.manager import PositionManager
from quantrex_core.strategy.context import StrategyContext


class LiveStrategyContext(StrategyContext):
    """Live-specific StrategyContext. Delegates to PositionManager (and future broker)."""

    def __init__(self, position_manager: PositionManager) -> None:
        self._pm = position_manager

    def submit_order(self, symbol: str, side: OrderSide, quantity: float,
                     order_type: OrderType = OrderType.MARKET) -> Order:
        # TODO(live): route to broker once integrated; broker fills will
        # supply the actual fill price. ``0.0`` is a placeholder so the
        # ``PositionManager.submit_order`` call type-checks today; the
        # live engine still raises ``NotImplementedError`` before any
        # order flows through.
        return self._pm.submit_order(
            symbol, side, quantity, order_type, datetime.now(), 0.0
        )

    def get_position(self, symbol: str) -> Position:
        return self._pm.get_position(symbol)
