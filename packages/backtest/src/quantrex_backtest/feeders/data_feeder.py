"""Data feeder protocol for backtest engine."""

from typing import Protocol


class DataFeeder(Protocol):
    """Protocol for data feeders that provide OHLCV candle data.

    Any class implementing this protocol can be used as a data source
    for the BacktestEngine. The CSVReader from quantrex-data already
    satisfies this protocol via duck typing.
    """

    def read(self) -> list[dict]:
        """Read and return all candle data as a list of dictionaries.

        Each dict should contain at minimum the keys required by Candle:
        - datetime: str (timestamp in a parseable format)
        - open: str or float
        - high: str or float
        - low: str or float
        - close: str or float
        - volume: str or float

        Returns:
            List of raw candle data dictionaries.
        """
        ...