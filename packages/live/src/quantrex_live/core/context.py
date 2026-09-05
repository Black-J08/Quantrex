"""Live trading strategy context (placeholder).

Minimal context for live trading — routes orders directly to the broker
(via PositionManager) without an OMS queue, since T+1 execution semantics
apply only to the backtest engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from quantrex_core import StrategyContext
from quantrex_core.models.enums import OrderSide, OrderType, OrderStatus

if TYPE_CHECKING:
    from quantrex_core.position.manager import PositionManager


class LiveStrategyContext(StrategyContext):
    """Live trading context — no OMS, orders go directly to broker/PM.

    For live trading, orders are submitted to the broker in real-time.
    The PositionManager records them for position tracking.  An OMS for
    live trading (e.g. to handle exchange-side latency) is TODO.
    """

    def __init__(self, position_manager: PositionManager) -> None:
        self._pm: PositionManager = position_manager

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: float | None = None,
    ):
        if quantity <= 0:
            return Order(status=OrderStatus.REJECTED, id="0")
        return self._pm.submit_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
        )

    def get_position(self, symbol: str):
        return self._pm.get_position(symbol)
