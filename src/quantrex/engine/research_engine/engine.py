"""ResearchEngine — mode-specific engine for research.

Inherits BaseEngine and adds research-specific capabilities:
time-forward distribution (event → forward returns over horizons) and
multiple research components per run.
"""

from __future__ import annotations

from quantrex.core.models.orders import Order
from quantrex.core.models.signals import Signal
from quantrex.core.models.trades import Trade
from quantrex.engine.base import BaseEngine


class ResearchEngine(BaseEngine):
    """Research engine.

    Runs the backtest-style event loop and, after the loop, performs
    time-forward distribution on events emitted by the strategy.
    Supports multiple research components, each receiving on_candle
    per bar.
    """

    def __init__(self) -> None:
        self._pending_fills: list[Trade] = []
        self._components: list[object] = []
        self._events: list[dict[str, object]] = []

    def execute_signal(self, signal: Signal) -> Order:
        """Convert a signal to an order and submit for simulated execution.

        Args:
            signal: The trading signal from the strategy.

        Returns:
            The resulting order.
        """
        from quantrex.engine.research_engine.execution.signal_to_order import (
            signal_to_order,
        )
        from quantrex.engine.research_engine.execution.simulator import Simulator

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

    def register_component(self, component: object) -> None:
        """Register a research component.

        Each registered component receives on_candle calls during the
        research event loop.

        Args:
            component: The research component to register.
        """
        self._components.append(component)

    def emit_event(self, symbol: str, direction: str, timestamp, metadata: dict | None = None) -> None:
        """Record a research event for forward-return tracking.

        Args:
            symbol: Instrument symbol.
            direction: Trade direction (e.g., 'long', 'short').
            timestamp: Event timestamp.
            metadata: Optional metadata associated with the event.
        """
        self._events.append(
            {
                "symbol": symbol,
                "direction": direction,
                "timestamp": timestamp,
                "metadata": metadata or {},
            }
        )

    def get_events(self) -> list[dict[str, object]]:
        """Return all recorded research events."""
        return list(self._events)

    def get_components(self) -> list[object]:
        """Return all registered research components."""
        return list(self._components)
