"""Order Management System (OMS) — T+1 execution queue for backtest and live."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Deque, List

from ..models.enums import OrderSide, OrderType, OrderStatus
from ..models.order import Order


@dataclass
class _PendingEntry:
    """Single pending order awaiting execution."""

    order: Order
    fill_price: float
    fill_timestamp: datetime


class OrderManagementSystem:
    """Queues orders and drains them on the next candle open (T+1 semantics).

    Used by :class:`quantrex_backtest.core.context.BacktestStrategyContext`
    to implement the framework's standard signal-to-execution timing:
    an order submitted during ``on_candle(candle_T)`` is queued and drained
    at the **next** candle's open price before the strategy reads that candle.

    The OMS is intentionally **stateless regarding positions** — it only
    tracks pending orders. Position updates are the exclusive responsibility
    of :class:`quantrex_core.position.manager.PositionManager`.

    For the live engine this class is a placeholder; order routing to a
    broker is ``TODO``.
    """

    def __init__(self) -> None:
        self._queue: Deque[_PendingEntry] = deque()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(self, order: Order, fill_price: float, fill_timestamp: datetime) -> None:
        """Queue an order for T+1 execution.

        The order is stored in PENDING state until :meth:`drain` is called.
        """
        self._queue.append(
            _PendingEntry(order=order, fill_price=fill_price, fill_timestamp=fill_timestamp)
        )

    def drain(self, execution_price: float, execution_timestamp: datetime) -> List[_PendingEntry]:
        """Drain all pending orders, updating each to ACCEPTED and returning them with execution context.

        Called by :class:`quantrex_backtest.core.engine.BacktestEngine` at
        the top of each candle loop **before** :meth:`update_time` is called,
        so the timestamp corresponds to the candle being entered.

        All orders in the queue are processed in FIFO order. Each drained
        order has its status set to ACCEPTED. The returned entries carry the
        execution price and timestamp the engine uses to call
        :meth:`quantrex_core.position.manager.PositionManager.apply`.
        """
        drained: List[_PendingEntry] = []
        while self._queue:
            entry = self._queue.popleft()
            # The stored order object is frozen, so we build a new one with
            # ACCEPTED status rather than mutating in-place.
            accepted = Order(
                id=entry.order.id,
                symbol=entry.order.symbol,
                side=entry.order.side,
                quantity=entry.order.quantity,
                order_type=entry.order.order_type,
                status=OrderStatus.ACCEPTED,
                timestamp=entry.order.timestamp,
            )
            drained.append(
                _PendingEntry(order=accepted, fill_price=execution_price, fill_timestamp=execution_timestamp)
            )
        return drained

    def flush_remaining_at_close(
        self, execution_price: float, execution_timestamp: datetime
    ) -> List[_PendingEntry]:
        """Drain all pending orders using the final candle's close price.

        Called by :class:`quantrex_backtest.core.engine.BacktestEngine` when
        the last candle has been processed. Any orders that were submitted
        during the final candle and are still pending are filled at the
        close price rather than being silently dropped.
        """
        return self.drain(execution_price, execution_timestamp)

    @property
    def pending_count(self) -> int:
        """Number of orders currently in the queue."""
        return len(self._queue)
