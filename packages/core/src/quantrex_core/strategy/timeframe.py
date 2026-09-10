"""Timeframe dispatch registry for Quantrex framework.

Provides @on_timeframe decorator and TimeframeDispatcher for
multi-timeframe strategy support.
"""

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from quantrex_core.models import Candle
from quantrex_core.strategy.context import StrategyContext


class TimeframeRegistry:
    """Registry for timeframe-specific strategy methods.

    Maps interval strings (e.g., "1H") to lists of bound methods.
    """

    def __init__(self) -> None:
        self._methods: dict[str, list[Callable[[Candle], None]]] = defaultdict(list)

    def register(self, interval: str, method: Callable[[Candle], None]) -> None:
        """Register a method for the given interval."""
        self._methods[interval].append(method)

    def get_methods(self, interval: str) -> list[Callable[[Candle], None]]:
        """Get all methods registered for an interval."""
        return self._methods.get(interval, [])

    def intervals(self) -> list[str]:
        """Return all registered intervals."""
        return list(self._methods.keys())

    def clear(self) -> None:
        """Clear all registered methods."""
        self._methods.clear()


def on_timeframe(interval: str) -> Callable[[Callable[[Candle], None]], Callable[[Candle], None]]:
    """Decorator to register a strategy method for a specific timeframe.

    Usage:
        class MyStrategy(Strategy):
            @on_timeframe("1H")
            def on_1h_candle(self, candle: Candle) -> None:
                ...

            @on_timeframe("1D")
            def on_daily_candle(self, candle: Candle) -> None:
                ...

    The decorated method will be called by TimeframeDispatcher.dispatch()
    with the latest candle of that timeframe.
    """
    def decorator(method: Callable[[Candle], None]) -> Callable[[Candle], None]:
        # Store the interval on the method for later registration
        method._quantrex_timeframe = interval  # type: ignore[attr-defined]
        return method
    return decorator


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
        """Dispatch for all registered intervals."""
        for interval in self._registry.intervals():
            self.dispatch(ctx, interval)

    def reset(self) -> None:
        """Reset dispatch state (e.g., for new backtest run)."""
        self._last_dispatched_index.clear()