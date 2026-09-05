from datetime import datetime
from quantrex_core.logging import get_logger
from quantrex_core.models import Candle
from quantrex_core.models.enums import OrderStatus, OrderType
from quantrex_core.models.order import Order, OrderSide
from quantrex_core.models.position import Position
from quantrex_core.order import OrderManagementSystem
from quantrex_core.position.manager import PositionManager
from quantrex_core.strategy.context import StrategyContext


logger = get_logger(__name__)


class BacktestStrategyContext(StrategyContext):
    """Backtest-specific StrategyContext.

    Queues orders through the OMS for T+1 execution and delegates position
    updates to PositionManager.
    """

    def __init__(
        self,
        position_manager: PositionManager,
        oms: OrderManagementSystem,
        current_time: datetime,
    ) -> None:
        self._pm = position_manager
        self._oms = oms
        self._current_time = current_time
        self._current_candle: Candle | None = None

    def submit_order(self, symbol: str, side: OrderSide, quantity: float,
                     order_type: OrderType = OrderType.MARKET) -> Order:
        if self._current_candle is None:
            raise RuntimeError("Cannot submit order: no current candle available. Call update_time() first.")
        # Reject non-positive quantity — return a REJECTED Order rather than
        # raising, so the audit trail records it with the same shape as an
        # ACCEPTED order (same timestamp, symbol, side, qty, type).
        if quantity <= 0:
            rejected = Order(
                id="0",
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                status=OrderStatus.REJECTED,
                timestamp=self._current_time,
            )
            logger.info(
                "[%s %s] ORDER id=%s status=REJECTED side=%s qty=%s type=%s price=%s",
                symbol,
                self._current_time.isoformat(),
                rejected.id,
                side.value,
                quantity,
                order_type.value,
                self._current_candle.open,
            )
            return rejected
        # Build the order in PENDING state and queue it for T+1 drain.
        # The OMS holds it until the engine drains at the next candle's open.
        order = Order(
            id="",  # Placeholder; engine assigns real id at drain time
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            status=OrderStatus.PENDING,
            timestamp=self._current_time,
        )
        # Store fill context: the order will be filled at the NEXT candle's open.
        self._oms.submit(order, fill_price=self._current_candle.open, fill_timestamp=self._current_time)
        return order

    def get_position(self, symbol: str) -> Position:
        return self._pm.get_position(symbol)

    def update_time(self, timestamp: datetime) -> None:
        """Called by engine before each candle to update order timestamp."""
        self._current_time = timestamp

    def update_candle(self, candle: Candle) -> None:
        """Called by engine before each candle to provide current candle for pricing."""
        self._current_candle = candle
