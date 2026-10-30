"""Kernel class — owns the event loop, clock, and execution context.

The kernel is mode-agnostic: it iterates over candles, calls strategy
hooks, manages the clock, and delegates signal-to-order processing to
the engine via ``engine.execute_signal(signal)``.
"""

from __future__ import annotations

from collections.abc import Iterable

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.kernel.context import KernelContext
from quantrex.kernel.protocols import EngineProtocol, StrategyProtocol


class Kernel:
    """The kernel owns the event loop, clock, and execution context.

    The kernel is mode-agnostic and contains no mode-specific logic. It
    iterates over candles, calls strategy hooks, advances the clock, and
    delegates signal-to-order processing to the engine.
    """

    def __init__(
        self,
        strategy: StrategyProtocol,
        engine: EngineProtocol,
    ) -> None:
        self.strategy = strategy
        self.engine = engine
        self.context = KernelContext(
            submit_order_cb=engine.submit_order,
            get_position_cb=engine.get_position,
        )

    def run(self, candles: Iterable[OHLCVCandle]) -> None:
        """Run the event loop over the provided candles.

        Args:
            candles: An iterable of OHLCV candles, sorted by timestamp.
        """
        self.strategy.on_start()
        self.engine.on_start()

        try:
            for candle in candles:
                self.context.current_time = candle.timestamp
                self.context.append_history(candle)

                signal = self.strategy.on_bar(candle)
                if signal is not None:
                    order = self.engine.execute_signal(signal)
                    self.strategy.on_order(order)
                    for trade in self.engine.get_pending_fills():
                        self.strategy.on_fill(trade)
        finally:
            self.strategy.on_stop()
            self.engine.on_stop()
