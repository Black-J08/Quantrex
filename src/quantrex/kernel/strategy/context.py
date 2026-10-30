"""Strategy context helpers."""

from __future__ import annotations

from datetime import datetime

from quantrex.core.models.market_data import OHLCVCandle
from quantrex.kernel.context import KernelContext


class StrategyContext:
    """Helper context for strategies, wrapping :class:`KernelContext`.

    Provides a convenient, read-only view of the execution context for
    use within strategy methods.
    """

    def __init__(self, kernel_context: KernelContext) -> None:
        self._ctx = kernel_context

    @property
    def current_time(self) -> datetime:
        """Current simulation/live time."""
        return self._ctx.current_time

    @property
    def history(self) -> tuple[OHLCVCandle, ...]:
        """Read-only snapshot of historical candles seen so far."""
        return self._ctx.history
