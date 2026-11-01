"""Kernel execution context implementing :class:`ContextProtocol`."""

from __future__ import annotations

from datetime import datetime

from quantrex.core.models.market_data import OHLCVCandle


class KernelContext:
    """Execution context shared between the kernel and strategy.

    Provides read-only access to historical data and mutable access to
    the current time. The kernel owns the clock and history; the strategy
    reads them but cannot submit orders or look up positions.

    Implements :class:`ContextProtocol`.
    """

    def __init__(self) -> None:
        self._current_time: datetime | None = None
        self._history: list[OHLCVCandle] = []

    @property
    def current_time(self) -> datetime:
        """Current simulation/live time."""
        if self._current_time is None:
            msg = "current_time has not been set yet"
            raise RuntimeError(msg)
        return self._current_time

    @current_time.setter
    def current_time(self, value: datetime) -> None:
        self._current_time = value

    @property
    def history(self) -> tuple[OHLCVCandle, ...]:
        """Read-only snapshot of historical candles seen so far."""
        return tuple(self._history)

    def append_history(self, candle: OHLCVCandle) -> None:
        """Append a candle to the history (internal use by the kernel)."""
        self._history.append(candle)
