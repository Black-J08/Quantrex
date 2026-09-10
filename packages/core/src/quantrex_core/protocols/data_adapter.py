"""Data Adapter protocol for Quantrex framework.

Protocol for data adapters that normalize provider data for the engine.
Adapters consume a DataProvider and convert its source-specific data
into the standardized market-data interface required by the Backtest Engine.
"""

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
    
    def read(self) -> list[dict]:
        """Read normalized OHLCV data ready for the engine (base timeframe).
        
        Returns:
            List of dictionaries with standardized keys:
            'datetime', 'open', 'high', 'low', 'close', 'volume'
            (and optionally additional fields)
        """
        ...
    
    def read_timeframe(self, timeframe: str) -> list[dict]:
        """Read normalized OHLCV data for a specific timeframe.
        
        Args:
            timeframe: Timeframe interval (e.g., "1M", "1H", "1D").
        
        Returns:
            List of dictionaries with standardized keys for the given timeframe.
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
    
    def close(self) -> None:
        """Close the underlying provider and release resources."""
        ...