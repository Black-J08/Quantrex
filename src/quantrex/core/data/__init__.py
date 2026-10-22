"""Quantrex Data Module.

This module provides:
- Persistent disk caching for historical market data (Feather format)
- Vendor-response normalization to canonical market data models
- Historical data providers that own the cache-aside fetch path
"""

from quantrex.core.data.cache import (
    OHLCV_SCHEMA,
    CacheKey,
    DiskCache,
    OHLCVCache,
    generate_cache_key,
)
from quantrex.core.data.exceptions import (
    CacheCorruptionError,
    CacheError,
    CacheMissError,
    DataError,
    DataValidationError,
    NormalizationError,
    ProviderError,
    SymbolResolutionError,
    TimeframeNotSupportedError,
)
from quantrex.core.data.historical import (
    HistoricalDataProvider,
    ZerodhaHistoricalDataProvider,
)
from quantrex.core.data.models import (
    OHLCVCandle,
    RawCandle,
    Tick,
    Timeframe,
    TimeframeUnit,
)
from quantrex.core.data.normalization import (
    Normalizer,
    ZerodhaNormalizer,
)

__all__ = [
    "OHLCV_SCHEMA",
    "CacheCorruptionError",
    "CacheError",
    "CacheKey",
    "CacheMissError",
    "DataError",
    "DataValidationError",
    "DiskCache",
    "HistoricalDataProvider",
    "NormalizationError",
    "Normalizer",
    "OHLCVCache",
    "OHLCVCandle",
    "ProviderError",
    "RawCandle",
    "SymbolResolutionError",
    "Tick",
    "Timeframe",
    "TimeframeNotSupportedError",
    "TimeframeUnit",
    "ZerodhaHistoricalDataProvider",
    "ZerodhaNormalizer",
    "generate_cache_key",
]

__version__ = "0.1.0"