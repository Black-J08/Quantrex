"""BacktestEngine — mode-specific engine for backtesting.

Inherits BaseEngine and implements the backtest execution workflow:
Signal → Order → simulated fill → Trade.
"""

from __future__ import annotations

from quantrex.core.models.orders import Order
from quantrex.core.models.signals import Signal
from quantrex.core.models.trades import Trade
from quantrex.engine.base import BaseEngine


class BacktestEngine(BaseEngine):
    """Backtest engine.

    Converts strategy signals into orders via its own execution package
    (``execution/signal_to_order.py``) and submits them to a simulated
    broker (``execution/simulator.py``).
    """

    def __init__(self) -> None:
        self._pending_fills: list[Trade] = []

    def execute_signal(self, signal: Signal) -> Order:
        """Convert a signal to an order and submit for simulated execution.

        Args:
            signal: The trading signal from the strategy.

        Returns:
            The resulting order (filled by the simulator).
        """
        from quantrex.engine.backtest_engine.execution.signal_to_order import (
            signal_to_order,
        )
        from quantrex.engine.backtest_engine.execution.simulator import Simulator

        order = signal_to_order(signal)
        simulator = Simulator(self)
        return simulator.submit_order(order)

    def get_pending_fills(self) -> list[Trade]:
        """Return and clear any pending trade fills."""
        fills = list(self._pending_fills)
        self._pending_fills.clear()
        return fills

    def add_fill(self, trade: Trade) -> None:
        """Record a trade fill (internal use by the simulator)."""
        self._pending_fills.append(trade)
