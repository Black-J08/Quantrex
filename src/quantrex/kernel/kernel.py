"""Kernel class — owns the event loop, clock, and execution context.

The kernel is mode-agnostic: it pulls candles from an iterator provided
by the engine, calls strategy hooks, manages the clock, and emits
signals outward via a callback supplied by the engine.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.signals import Signal
from quantrex.kernel.context import KernelContext
from quantrex.kernel.protocols import ClockProtocol, StrategyProtocol


class Kernel:
    """The kernel owns the event loop, clock, and execution context.

    The kernel is mode-agnostic and contains no mode-specific logic. It
    pulls candles from an iterator, calls strategy hooks, advances the
    clock, and emits strategy decisions (signals) outward via a callback.
    The kernel does not know where data comes from or where outputs go.
    """

    def __init__(
        self,
        strategy: StrategyProtocol,
        on_signal: Callable[[Signal], None],
        clock: ClockProtocol | None = None,
    ) -> None:
        self.strategy = strategy
        self.on_signal = on_signal
        self.clock = clock
        self.context = KernelContext()

    def run(self, candles: Iterator[OHLCVCandle]) -> None:
        """Run the event loop over the provided candle iterator.

        Args:
            candles: An iterator of OHLCV candles, sorted by timestamp.
        """
        self.strategy.on_start()

        try:
            for candle in candles:
                if self.clock is not None:
                    self.clock.advance(candle.timestamp)
                self.context.current_time = candle.timestamp
                self.context.append_history(candle)

                signal = self.strategy.on_bar(candle)
                if signal is not None:
                    self.on_signal(signal)
        finally:
            self.strategy.on_stop()
