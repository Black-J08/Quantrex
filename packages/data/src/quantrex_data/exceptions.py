"""Shared exceptions for Quantrex data package."""

from typing import List, Tuple


class DataNotAvailableError(Exception):
    """Raised when requested historical data is not available in cache and authentication was cancelled.

    This exception provides information about what cached periods are available
    so the user can adjust their backtest date range accordingly.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        symbol: str,
        timeframe: str,
        cached_periods: List[Tuple[str, str]],
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.symbol = symbol
        self.timeframe = timeframe
        self.cached_periods = cached_periods

    def __str__(self) -> str:
        base = super().__str__()
        if self.cached_periods:
            periods_str = "\n  ".join([f"{start} to {end}" for start, end in self.cached_periods])
            return f"{base}\n\nAvailable cached periods for {self.provider}/{self.symbol}/{self.timeframe}:\n  {periods_str}\n\nPlease rerun the backtest using one of these date ranges."
        return base