"""Historical data provider module for Quantrex data layer."""

from quantrex.core.data.historical.provider import HistoricalDataProvider
from quantrex.core.data.historical.zerodha_provider import ZerodhaHistoricalDataProvider

__all__ = [
    "HistoricalDataProvider",
    "ZerodhaHistoricalDataProvider",
]