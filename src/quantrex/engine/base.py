"""BaseEngine — shared lifecycle hooks and engine interface.

BaseEngine defines the engine interface shared by all mode-specific
engines (backtest, live, research). It contains only lifecycle hooks
and the abstract :meth:`execute_signal` — no signal-to-order logic, no
data feed logic, and no execution logic. Those are owned by each
engine's own ``execution/`` package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from quantrex.core.models.orders import Order
from quantrex.core.models.positions import Position
from quantrex.core.models.signals import Signal
from quantrex.core.models.trades import Trade


class BaseEngine(ABC):
    """Base class for all trading engines.

    Subclasses must implement :meth:`execute_signal` to convert strategy
    signals into orders within their own execution workflow.
    """

    @abstractmethod
    def execute_signal(self, signal: Signal) -> Order:
        """Convert a signal to an order and submit for execution.

        Each engine implements this independently within its own
        ``execution/`` package.

        Args:
            signal: The trading signal from the strategy.

        Returns:
            The resulting order.
        """
        ...

    def get_pending_fills(self) -> list[Trade]:
        """Return and clear any pending trade fills.

        Returns:
            A list of trades that have been filled since the last call.
        """
        return []

    def submit_order(self, order: Order) -> Order:
        """Submit an order for execution.

        Args:
            order: The order to submit.

        Returns:
            The submitted order with updated status.
        """
        return order

    def get_position(self, symbol: str) -> Position | None:
        """Get the current position for a symbol.

        Args:
            symbol: Instrument symbol.

        Returns:
            The current position, or ``None`` if no position exists.
        """
        return None

    def on_start(self) -> None:
        """Called once before the event loop begins."""

    def on_stop(self) -> None:
        """Called once after the event loop ends."""
