"""Timeframe registry for Quantrex framework.

Maps interval strings to lists of bound methods.
"""

from collections import defaultdict
from collections.abc import Callable

from quantrex_core.models import Candle
from quantrex_core.timeframe.arithmetic import is_multiple_of
from quantrex_core.timeframe.parser import interval_to_minutes


class TimeframeRegistry:
    """Registry for timeframe-specific strategy methods.

    Maps interval strings (e.g., "1H") to lists of bound methods.
    """

    def __init__(self) -> None:
        self._methods: dict[str, list[Callable[[Candle], None]]] = defaultdict(list)

    def register(self, interval: str, method: Callable[[Candle], None]) -> None:
        """Register a method for the given interval.

        Validates that if a base timeframe (smallest registered) exists,
        the new interval is an exact multiple of it. This ensures correct
        aggregation semantics and predictable dispatch timing.
        """
        # If this is the first interval, it becomes the base
        if not self._methods:
            self._methods[interval].append(method)
            return

        # Find the base timeframe (smallest registered interval)
        base_interval = min(self._methods.keys(), key=interval_to_minutes)
        
        # If the new interval is smaller than base, it becomes the new base
        # (no validation needed - it's the new smallest)
        if interval_to_minutes(interval) < interval_to_minutes(base_interval):
            self._methods[interval].append(method)
            return

        # Otherwise, validate that the new interval is a multiple of the base
        if not is_multiple_of(base_interval, interval):
            raise ValueError(
                f"Timeframe {interval!r} must be a multiple of base timeframe {base_interval!r}. "
                f"Registered timeframes: {list(self._methods.keys())}"
            )

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