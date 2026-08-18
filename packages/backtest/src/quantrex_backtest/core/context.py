from datetime import datetime
from quantrex_core.models.enums import OrderType
from quantrex_core.models.order import Order, OrderSide
from quantrex_core.models.position import Position
from quantrex_core.position.manager import PositionManager
from quantrex_core.protocols import StrategyContext


class BacktestStrategyContext:
    """Backtest-specific StrategyContext. Delegates to PositionManager."""

    def __init__(self, position_manager: PositionManager, current_time: datetime) -> None:
        self._pm = position_manager
        self._current_time = current_time

    def submit_order(self, symbol: str, side: OrderSide, quantity: float,
                     order_type: OrderType = OrderType.MARKET) -> Order:
        return self._pm.submit_order(symbol, side, quantity, order_type, self._current_time)

    def get_position(self, symbol: str) -> Position:
        return self._pm.get_position(symbol)

    def update_time(self, timestamp: datetime) -> None:
        """Called by engine before each candle to update order timestamp."""
        self._current_time = timestamp
