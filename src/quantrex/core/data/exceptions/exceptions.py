"""Data module exceptions."""

from __future__ import annotations

from typing import Any


class DataError(Exception):
    """Base exception for all data module errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


class CacheError(DataError):
    """Cache-related errors."""

    def __init__(self, message: str, cache_key: str | None = None, details: dict | None = None):
        super().__init__(message, details)
        self.cache_key = cache_key


class CacheMissError(CacheError):
    """Raised when cache lookup fails and no fallback is available."""

    def __init__(self, cache_key: str, message: str = "Cache miss"):
        super().__init__(message, cache_key=cache_key)


class CacheCorruptionError(CacheError):
    """Raised when cache data is corrupted and cannot be read."""

    def __init__(self, cache_key: str, original_error: Exception | None = None):
        details = {"original_error": str(original_error)} if original_error else {}
        super().__init__(
            f"Cache corruption detected for key: {cache_key}",
            cache_key=cache_key,
            details=details,
        )


class NormalizationError(DataError):
    """Raised when vendor response normalization fails."""

    def __init__(self, message: str, vendor: str, raw_data: Any | None = None, details: dict | None = None):
        super().__init__(message, details)
        self.vendor = vendor
        self.raw_data = raw_data


class ProviderError(DataError):
    """Raised when data provider encounters an error."""

    def __init__(self, message: str, provider: str, details: dict | None = None):
        super().__init__(message, details)
        self.provider = provider


class SymbolResolutionError(DataError):
    """Raised when symbol cannot be resolved."""

    def __init__(self, symbol: str, message: str | None = None, suggestions: list[str] | None = None):
        msg = message or f"Symbol not found: {symbol}"
        if suggestions:
            msg += f". Suggestions: {', '.join(suggestions[:5])}"
        super().__init__(msg)
        self.symbol = symbol
        self.suggestions = suggestions or []


class TimeframeNotSupportedError(DataError):
    """Raised when a timeframe is not supported by the provider."""

    def __init__(self, timeframe: str, provider: str, supported: list[str] | None = None):
        msg = f"Timeframe '{timeframe}' not supported by {provider}"
        if supported:
            msg += f". Supported: {', '.join(supported)}"
        super().__init__(msg)
        self.timeframe = timeframe
        self.provider = provider
        self.supported = supported or []


class DataValidationError(DataError):
    """Raised when data fails validation checks."""

    def __init__(self, message: str, field: str | None = None, value: Any | None = None):
        super().__init__(message)
        self.field = field
        self.value = value