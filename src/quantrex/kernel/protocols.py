"""Kernel protocols defining the contracts for strategies, context, and clock."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.signals import Signal


@runtime_checkable
class StrategyProtocol(Protocol):
    """Protocol for trading strategies.

    A strategy reacts to market events and may emit signals.
    Decision logic only — no I/O, no clock, no state lifecycle.
    """

    def on_bar(self, candle: OHLCVCandle) -> Signal | None:
        """Handle a new bar/candle.

        Args:
            candle: The completed OHLCV candle.

        Returns:
            An optional trading signal, or ``None`` if no signal is emitted.
        """
        ...

    def on_start(self) -> None:
        """Called once before the event loop begins."""
        ...

    def on_stop(self) -> None:
        """Called once after the event loop ends."""
        ...


@runtime_checkable
class ContextProtocol(Protocol):
    """Protocol for the execution context exposed to strategies."""

    @property
    def current_time(self) -> datetime:
        """Current simulation/live time."""
        ...

    @property
    def history(self) -> tuple[OHLCVCandle, ...]:
        """Read-only snapshot of historical candles seen so far."""
        ...


@runtime_checkable
class ClockProtocol(Protocol):
    """Protocol for the clock used by the kernel."""

    def now(self) -> datetime:
        """Return the current time."""
        ...

    def advance(self, target: datetime) -> None:
        """Advance the clock to the given time.

        Args:
            target: The target time to advance to.
        """
        ...
