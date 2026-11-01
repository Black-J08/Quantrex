"""LiveEngine — mode-specific engine for live trading.

Owns the kernel lifecycle, sources live data via a data iterator,
converts strategy signals to orders, and places them via a broker
adapter.
"""

from __future__ import annotations

from collections.abc import Iterator

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.signals import Signal
from quantrex.core.models.trades import Trade
from quantrex.engine.base import BaseEngine
from quantrex.engine.signal_to_order import signal_to_order
from quantrex.kernel.kernel import Kernel


class LiveEngine(BaseEngine):
    """Live engine.

    Creates and owns the kernel, feeds it live candles/ticks from a
    data iterator, handles signals by converting them to orders and
    submitting them to a live broker adapter.
    """

    def __init__(self) -> None:
        self._pending_fills: list[Trade] = []
        self._candles: list[OHLCVCandle] = []

    def create_kernel(self, strategy) -> Kernel:
        """Create a kernel wired to this engine's signal handler."""
        return Kernel(strategy, on_signal=self.on_signal)

    def data_iterator(self) -> Iterator[OHLCVCandle]:
        """Return an iterator of live candles/ticks."""
        return iter(self._candles)

    def set_candles(self, candles: list[OHLCVCandle]) -> None:
        """Set the live candles/ticks to feed to the kernel.

        Args:
            candles: List of OHLCV candles sorted by timestamp.
        """
        self._candles = list(candles)

    def on_signal(self, signal: Signal) -> None:
        """Handle a signal emitted by the kernel.

        Converts the signal to an order and submits it to the live
        broker adapter for execution.
        """
        order = signal_to_order(signal)
        from quantrex.engine.live_engine.execution.broker import BrokerAdapter

        broker = BrokerAdapter(self)
        broker.submit_order(order)

    def add_fill(self, trade: Trade) -> None:
        """Record a trade fill (internal use by the broker adapter)."""
        self._pending_fills.append(trade)

    def get_pending_fills(self) -> list[Trade]:
        """Return and clear any pending trade fills."""
        fills = list(self._pending_fills)
        self._pending_fills.clear()
        return fills
