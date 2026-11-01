"""Concrete Strategy base class implementing :class:`StrategyProtocol`."""

from __future__ import annotations

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.signals import Signal
from quantrex.kernel.protocols import StrategyProtocol


class Strategy(StrategyProtocol):
    """Base class for trading strategies.

    Subclasses must implement :meth:`on_bar`. Decision logic only —
    no I/O, no clock, no state lifecycle.
    """

    def on_bar(self, candle: OHLCVCandle) -> Signal | None:
        """Handle a new bar/candle.

        Args:
            candle: The completed OHLCV candle.

        Returns:
            An optional trading signal, or ``None`` if no signal is emitted.
        """
        msg = "subclasses must implement on_bar"
        raise NotImplementedError(msg)

    def on_start(self) -> None:
        """Called once before the event loop begins."""

    def on_stop(self) -> None:
        """Called once after the event loop ends."""
