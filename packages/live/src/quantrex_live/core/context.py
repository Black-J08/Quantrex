from datetime import datetime
from quantrex_core.models.enums import OrderType, OrderSide
from quantrex_core.models.order import Order
from quantrex_core.models.position import Position
from quantrex_core.position.manager import PositionManager
from quantrex_core.protocols import StrategyContext


class LiveStrategyContext:
    """Live-specific StrategyContext. Delegates to PositionManager (and future broker)."""

    def __init__(self, position_manager: PositionManager) -> None:
        self._pm = position_manager

    def submit_order(self, symbol: str, side: OrderSide, quantity: float,
                     order_type: OrderType = OrderType.MARKET) -> Order:
        # Future: send to broker, then record in PositionManager
        # For now: same as backtest (accept and update position)
        return self._pm.submit_order(symbol, side, quantity, order_type, datetime.now())

    def get_position(self, symbol: str) -> Position:
        return self._pm.get_position(symbol)
