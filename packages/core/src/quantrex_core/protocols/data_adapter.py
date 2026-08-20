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
        """Read normalized OHLCV data ready for the engine.
        
        Returns:
            List of dictionaries with standardized keys:
            'datetime', 'open', 'high', 'low', 'close', 'volume'
            (and optionally additional fields)
        """
        ...
    
    def close(self) -> None:
        """Close the underlying provider and release resources."""
        ...