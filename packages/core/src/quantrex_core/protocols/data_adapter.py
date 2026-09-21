"""Data Adapter protocol for Quantrex framework.

Protocol for data adapters that normalize provider data for the engine.
Adapters consume a DataProvider and convert its source-specific data
into the standardized market-data interface required by the Backtest Engine.
"""

from datetime import time
from typing import Protocol
from quantrex_core.protocols.data_provider import DataProvider


class DataAdapter(Protocol):
    """Protocol for data adapters that normalize provider data for the engine.
    
    Adapters consume a DataProvider and convert its source-specific data
    into the standardized market-data interface required by the Backtest Engine.
    """
    
    def __init__(self, provider: DataProvider) -> None:
        """Initialize adapter with a data provider.
        
        Args:
            provider: DataProvider instance to consume data from
        """
        ...
    
    def read(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        """Read normalized OHLCV data ready for the engine (base timeframe).
        
        Args:
            from_date: Optional start date for data filtering (ISO format "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS").
                      If provided, overrides any date range configured in the underlying provider.
            to_date: Optional end date for data filtering (ISO format "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS").
                    If provided, overrides any date range configured in the underlying provider.
        
        Returns:
            List of dictionaries with standardized keys:
            'datetime', 'open', 'high', 'low', 'close', 'volume'
            (and optionally additional fields)
        """
        ...
    
    def read_timeframe(
        self,
        timeframe: str,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        """Read normalized OHLCV data for a specific timeframe.
        
        If the adapter natively supports the requested timeframe, returns
        the provider's native data for that timeframe. Otherwise, the
        adapter MUST aggregate/resample from 1-minute data (obtained via
        the underlying provider's ``fetch("1M")``) to produce the requested
        timeframe. If 1-minute data is unavailable and the timeframe is
        not natively supported, raise ``ValueError`` with a clear message
        naming the missing timeframe and available alternatives.
        
        Args:
            timeframe: Timeframe interval (e.g., "1M", "1H", "1D").
            from_date: Optional start date for data filtering (ISO format "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS").
                      If provided, overrides any date range configured in the underlying provider.
            to_date: Optional end date for data filtering (ISO format "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS").
                    If provided, overrides any date range configured in the underlying provider.
        
        Returns:
            List of dictionaries with standardized keys for the given timeframe.
        
        Raises:
            ValueError: If the timeframe cannot be provided natively and
                1-minute data is unavailable for aggregation.
        """
        ...
    
    @property
    def supported_timeframes(self) -> list[str]:
        """Return list of supported timeframe intervals.
        
        Returns:
            List of timeframe strings supported by this adapter.
        """
        ...
    
    @property
    def datetime_format(self) -> str:
        """Format string used by the adapter for datetime parsing.
        
        The engine reads this property to know how to parse the
        'datetime' values produced by ``read()``. This ensures a
        single source of truth: the adapter owns the format.
        
        Returns:
            The datetime format string (e.g., "%Y%m%d %H:%M").
        """
        ...
    
    def get_origin_time(self) -> time:
        """Return the origin time for this adapter's market.
        
        The origin time is the start of the first interval of the trading day
        (e.g., 09:15 for NSE). This is used for correct timeframe aggregation
        and close-time alignment.
        
        Returns:
            Origin time as a datetime.time object.
        """
        ...
    
    def close(self) -> None:
        """Close the underlying provider and release resources."""
        ...