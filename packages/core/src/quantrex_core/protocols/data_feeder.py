"""Data feeder protocol for Quantrex framework.

Protocol for data feeders that provide OHLCV candle data.
Any class implementing this protocol can be used as a data source
for execution engines. The CSVReader from quantrex-data already
satisfies this protocol via duck typing.
"""

from typing import Protocol


class DataFeeder(Protocol):
    """Protocol for data feeders that provide OHLCV candle data."""
    
    def read(self) -> list[dict]:
        """Read OHLCV data from the data source.
        
        Returns:
            List of dictionaries representing raw candle data.
            Each dictionary should contain at least: 
            'datetime', 'open', 'high', 'low', 'close', 'volume'
        """
        ...