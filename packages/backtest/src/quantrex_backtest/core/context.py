from datetime import datetime
from quantrex_core.logging import get_logger
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderType
from quantrex_core.models.order import Order, OrderSide
from quantrex_core.models.position import Position
from quantrex_core.position.manager import PositionManager
from quantrex_core.strategy.context import StrategyContext


logger = get_logger(__name__)


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
        order = self._pm.submit_order(symbol, side, quantity, order_type, self._current_time, price)
        # Audit line mirrors the per-bar OHLCV format in engine.run() so a
        # researcher grep'ing execution.log for a candle timestamp sees both
        # the bar and any orders at that bar together. Logs ACCEPTED and
        # REJECTED orders alike — the audit trail is the symmetric record
        # of what was submitted vs. accepted, so dropping rejections would
        # silently under-report.
        logger.info(
            "[%s %s] ORDER id=%s status=%s side=%s qty=%s type=%s price=%s",
            symbol,
            self._current_time.isoformat(),
            order.id,
            order.status.value,
            side.value,
            quantity,
            order_type.value,
            price,
        )
        return order

    def get_position(self, symbol: str) -> Position:
        return self._pm.get_position(symbol)

    def update_time(self, timestamp: datetime) -> None:
        """Called by engine before each candle to update order timestamp."""
        self._current_time = timestamp

    def update_candle(self, candle: Candle) -> None:
        """Called by engine before each candle to provide current candle for pricing."""
        self._current_candle = candle
