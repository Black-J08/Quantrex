"""LiveEngine — mode-specific engine for live trading.

Inherits BaseEngine and implements the live execution workflow:
Signal → Order → real broker execution → Fill.
"""

from __future__ import annotations

from quantrex.core.models.orders import Order
from quantrex.core.models.signals import Signal
from quantrex.core.models.trades import Trade
from quantrex.engine.base import BaseEngine


class LiveEngine(BaseEngine):
    """Live engine.

    Converts strategy signals into orders via its own execution package
    (``execution/signal_to_order.py``) and submits them to a real broker
    adapter (``execution/broker.py``).
    """

    def __init__(self) -> None:
        self._pending_fills: list[Trade] = []

    def execute_signal(self, signal: Signal) -> Order:
        """Convert a signal to an order and submit for live execution.

        Args:
            signal: The trading signal from the strategy.

        Returns:
            The resulting order.
        """
        from quantrex.engine.live_engine.execution.broker import BrokerAdapter
        from quantrex.engine.live_engine.execution.signal_to_order import (
            signal_to_order,
        )

        order = signal_to_order(signal)
        broker = BrokerAdapter(self)
        return broker.submit_order(order)

    def get_pending_fills(self) -> list[Trade]:
        """Return and clear any pending trade fills."""
        fills = list(self._pending_fills)
        self._pending_fills.clear()
        return fills

    def add_fill(self, trade: Trade) -> None:
        """Record a trade fill (internal use by the broker adapter)."""
        self._pending_fills.append(trade)
