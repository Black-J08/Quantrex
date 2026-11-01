"""BaseEngine — shared interface for all mode-specific engines.

BaseEngine defines the interface shared by all mode-specific engines
(backtest, live, research). The engine is the only layer that differs
between modes: it owns the kernel lifecycle, sources data, and decides
what to do with strategy signals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.signals import Signal
from quantrex.kernel.kernel import Kernel


class BaseEngine(ABC):
    """Base class for all trading engines.

    The engine owns the kernel lifecycle, sources data via an iterator,
    and handles strategy signals emitted by the kernel.
    """

    def __init__(self) -> None:
        self._kernel: Kernel | None = None

    @property
    def kernel(self) -> Kernel:
        """The kernel owned by this engine."""
        if self._kernel is None:
            msg = "kernel has not been created yet"
            raise RuntimeError(msg)
        return self._kernel

    @abstractmethod
    def create_kernel(self, strategy) -> Kernel:
        """Create and return a kernel for the given strategy.

        The kernel's ``on_signal`` callback must be wired to
        :meth:`on_signal` so the engine receives strategy decisions.

        Args:
            strategy: The strategy to run.

        Returns:
            A configured Kernel instance.
        """
        ...

    @abstractmethod
    def data_iterator(self) -> Iterator[OHLCVCandle]:
        """Return an iterator of market data candles/ticks.

        Returns:
            An iterator of OHLCV candles sorted by timestamp.
        """
        ...

    @abstractmethod
    def on_signal(self, signal: Signal) -> None:
        """Handle a signal emitted by the kernel.

        This is where the engine decides what to do with the signal:
        convert to order, place order, or write to trade log.

        Args:
            signal: The trading signal from the strategy.
        """
        ...

    def get_pending_fills(self) -> list:
        """Return and clear any pending trade fills.

        Returns:
            A list of trades that have been filled since the last call.
        """
        return []

    def start(self, strategy) -> None:
        """Create, configure, and start the kernel for the given strategy.

        Args:
            strategy: The strategy to run.
        """
        self._kernel = self.create_kernel(strategy)
        self._kernel.run(self.data_iterator())

    def stop(self) -> None:
        """Stop the kernel.

        Kernel.run() completes when the data iterator is exhausted.
        """
