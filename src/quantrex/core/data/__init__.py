"""Quantrex Data Module.

This module provides:
- Vendor-response normalization to canonical market data models
- Historical data providers that own the cache-aside fetch path

Canonical models (candles, ticks, timeframes) live in
:mod:`quantrex.core.models`. The on-disk cache is an internal implementation
detail of the providers and is deliberately not exported.
"""

from quantrex.core.data.exceptions import (
    DataError,
    NormalizationError,
    ProviderError,
    SymbolResolutionError,
    TimeframeNotSupportedError,
)
from quantrex.core.data.historical import (
    HistoricalDataProvider,
    ZerodhaHistoricalDataProvider,
)
from quantrex.core.data.normalization import (
    Normalizer,
    ZerodhaNormalizer,
)

__all__ = [
    "DataError",
    "HistoricalDataProvider",
    "NormalizationError",
    "Normalizer",
    "ProviderError",
    "SymbolResolutionError",
    "TimeframeNotSupportedError",
    "ZerodhaHistoricalDataProvider",
    "ZerodhaNormalizer",
]

__version__ = "0.1.0"