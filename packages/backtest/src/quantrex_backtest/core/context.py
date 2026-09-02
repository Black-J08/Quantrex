from datetime import datetime
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderType
from quantrex_core.models.order import Order, OrderSide
from quantrex_core.models.position import Position
from quantrex_core.position.manager import PositionManager
from quantrex_core.strategy.context import StrategyContext


class BacktestStrategyContext(StrategyContext):
    """Backtest-specific StrategyContext. Delegates to PositionManager."""

    def __init__(self, position_manager: PositionManager, current_time: datetime) -> None:
        self._pm = position_manager
        self._current_time = current_time
        self._current_candle: Candle | None = None

    def submit_order(self, symbol: str, side: OrderSide, quantity: float,
                     order_type: OrderType = OrderType.MARKET) -> Order:
        if self._current_candle is None:
            raise RuntimeError("Cannot submit order: no current candle available. Call update_time() first.")
        # Use candle's open price as fill price for MARKET orders
        price = self._current_candle.open
        return self._pm.submit_order(symbol, side, quantity, order_type, self._current_time, price)

    def get_position(self, symbol: str) -> Position:
        return self._pm.get_position(symbol)

    def update_time(self, timestamp: datetime) -> None:
        """Called by engine before each candle to update order timestamp."""
        self._current_time = timestamp

    def update_candle(self, candle: Candle) -> None:
        """Called by engine before each candle to provide current candle for pricing."""
        self._current_candle = candle
