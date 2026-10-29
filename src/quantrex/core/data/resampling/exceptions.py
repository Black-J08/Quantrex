"""Exceptions for the resampling module."""

from __future__ import annotations

from quantrex.core.data.exceptions.exceptions import DataError


class ResamplingError(DataError):
    """Raised when resampling candles fails."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, details)


class InvalidDerivedTimeframeError(DataError):
    """Raised when a timeframe cannot be derived from a canonical source."""

    def __init__(self, timeframe: str, source: str, details: dict | None = None):
        msg = f"Timeframe '{timeframe}' cannot be derived from canonical source '{source}'"
        super().__init__(msg, details)
        self.timeframe = timeframe
        self.source = source
