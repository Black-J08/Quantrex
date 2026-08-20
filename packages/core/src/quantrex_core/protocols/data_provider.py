"""Data Provider protocol for Quantrex framework.

Protocol for data providers that fetch raw data from a specific source.
Providers handle data acquisition in the source's native format.
They do NOT perform normalization or conversion to engine format.
"""

from typing import Protocol, Any


class DataProvider(Protocol):
    """Protocol for data providers that fetch raw data from a specific source.
    
    Providers handle data acquisition in the source's native format.
    They do NOT perform normalization or conversion to engine format.
    """
    
    def fetch(self) -> Any:
        """Fetch raw data from the source in its native format.
        
        Returns:
            Raw data as returned by the source (e.g., list of CSV rows, 
            API response dict, WebSocket messages, etc.)
        """
        ...
    
    def close(self) -> None:
        """Close any open connections or resources."""
        ...