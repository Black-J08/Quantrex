"""Timeframe decorators for Quantrex framework.

Provides @on_timeframe decorator for registering strategy methods.
"""

from collections.abc import Callable

from quantrex_core.models import Candle


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