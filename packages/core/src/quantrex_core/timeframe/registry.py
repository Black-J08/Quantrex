"""Timeframe registry for Quantrex framework.

Maps interval strings to lists of bound methods.
"""

from collections import defaultdict
from collections.abc import Callable

from quantrex_core.models import Candle


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