"""Kernel execution context implementing :class:`ContextProtocol`."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.core.models.orders import Order
from quantrex.core.models.positions import Position


class KernelContext:
    """Execution context shared between the kernel, strategy, and engine.

    Provides read-only access to historical data and mutable access to
    the current time. Order submission and position lookup are delegated
    to callbacks supplied by the kernel (which in turn delegates to the
    engine's execution layer).

    Implements :class:`ContextProtocol`.
    """

    def __init__(
        self,
        submit_order_cb: Callable[[Order], Order] | None = None,
        get_position_cb: Callable[[str], Position | None] | None = None,
    ) -> None:
        self._current_time: datetime | None = None
        self._history: list[OHLCVCandle] = []
        self._submit_order_cb = submit_order_cb
        self._get_position_cb = get_position_cb

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

    def submit_order(self, order: Order) -> Order:
        """Submit an order for execution.

        Delegates to the callback supplied by the kernel.
        """
        if self._submit_order_cb is None:
            msg = "submit_order is not available in this context"
            raise NotImplementedError(msg)
        return self._submit_order_cb(order)

    def get_position(self, symbol: str) -> Position | None:
        """Get the current position for a symbol.

        Delegates to the callback supplied by the kernel.
        """
        if self._get_position_cb is None:
            msg = "get_position is not available in this context"
            raise NotImplementedError(msg)
        return self._get_position_cb(symbol)
