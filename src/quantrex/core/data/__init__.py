"""Quantrex Data Module.

This module provides:
- Vendor-response normalization to canonical market data models
- Historical data providers that own the cache-aside fetch path

Canonical models (candles, ticks, timeframes) live in
:mod:`quantrex.core.models`. The on-disk cache is an internal implementation
detail of the providers and is deliberately not exported.

Only ``ZerodhaHistoricalDataProvider`` is re-exported here as the data
module's public entry point.
"""

from quantrex.core.data.historical.zerodha_provider import ZerodhaHistoricalDataProvider

__all__ = [
    "ZerodhaHistoricalDataProvider",
]

__version__ = "0.1.0"