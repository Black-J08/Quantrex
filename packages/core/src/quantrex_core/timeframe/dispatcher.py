"""Timeframe dispatcher for Quantrex framework.

Dispatches candles to registered timeframe methods.
"""

from collections import defaultdict
from collections.abc import Callable

from quantrex_core.models import Candle
from quantrex_core.strategy.context import StrategyContext
from quantrex_core.timeframe.registry import TimeframeRegistry
from quantrex_core.timeframe.parser import interval_to_minutes


class TimeframeDispatcher:
    """Dispatches candles to registered timeframe methods.

    Reads filtered candles from StrategyContext.timeframe_history()
    and invokes all registered methods for that interval.
    """

    def __init__(self, registry: TimeframeRegistry) -> None:
        self._registry = registry
        self._last_dispatched_index: dict[str, int] = defaultdict(int)

    def dispatch(self, ctx: StrategyContext, interval: str) -> None:
        """Dispatch latest timeframe candles to registered methods.

        Args:
            ctx: StrategyContext with timeframe_history support
            interval: Timeframe interval (e.g., "1H")
        """
        methods = self._registry.get_methods(interval)
        if not methods:
            return

        tf_history = ctx.timeframe_history(interval)
        if not tf_history:
            return

        last_idx = self._last_dispatched_index[interval]
        new_candles = tf_history[last_idx:]

        for candle in new_candles:
            for method in methods:
                method(candle)

        self._last_dispatched_index[interval] = len(tf_history)

    def dispatch_all(self, ctx: StrategyContext) -> None:
        """Dispatch for all registered intervals, ordered by duration (smallest first)."""
        # Sort intervals by duration (minutes) so smaller timeframes dispatch first
        intervals = sorted(self._registry.intervals(), key=interval_to_minutes)
        for interval in intervals:
            self.dispatch(ctx, interval)

    def reset(self) -> None:
        """Reset dispatch state (e.g., for new backtest run)."""
        self._last_dispatched_index.clear()