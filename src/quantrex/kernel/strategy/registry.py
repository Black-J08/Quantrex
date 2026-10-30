"""Timeframe/method registration helpers."""

from __future__ import annotations

from quantrex.core.models.timeframe import Timeframe


class StrategyRegistry:
    """Registry for strategy timeframe and method mappings.

    Allows strategies to register the timeframes they operate on and
    look them up by name.
    """

    def __init__(self) -> None:
        self._timeframes: dict[str, Timeframe] = {}

    def register_timeframe(self, name: str, timeframe: Timeframe) -> None:
        """Register a timeframe under a given name.

        Args:
            name: The name to register the timeframe under.
            timeframe: The timeframe to register.
        """
        self._timeframes[name] = timeframe

    def get_timeframe(self, name: str) -> Timeframe | None:
        """Retrieve a registered timeframe by name.

        Args:
            name: The name of the timeframe to retrieve.

        Returns:
            The registered timeframe, or ``None`` if not found.
        """
        return self._timeframes.get(name)

    def registered_names(self) -> list[str]:
        """Return the names of all registered timeframes."""
        return list(self._timeframes.keys())
