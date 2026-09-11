"""Zerodha-specific exceptions for Quantrex framework."""

from typing import Any


class ZerodhaError(Exception):
    """Base exception for all Zerodha API errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_data: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_data = response_data

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code is not None:
            parts.append(f"status={self.status_code}")
        if self.response_data is not None:
            parts.append(f"response={self.response_data}")
        return " | ".join(parts)


class ZerodhaAuthenticationError(ZerodhaError):
    """Raised when authentication fails (403, TokenException).

    This indicates the access token is expired, invalid, or the session
    was invalidated. The caller should trigger a re-login flow.
    """


class ZerodhaRateLimitError(ZerodhaError):
    """Raised when rate limit is exceeded (429)."""


class ZerodhaInvalidParameterError(ZerodhaError):
    """Raised when request parameters are invalid (400, InputException)."""

    def __init__(
        self,
        message: str,
        *,
        error_code: int | None = None,
        status_code: int | None = None,
        response_data: Any = None,
    ) -> None:
        super().__init__(message, status_code=status_code, response_data=response_data)
        self.error_code = error_code


class ZerodhaDataNotFoundError(ZerodhaError):
    """Raised when no data is returned for the given parameters."""


class ZerodhaInstrumentMasterError(ZerodhaError):
    """Raised when instrument master download or parsing fails."""


class ZerodhaSymbolNotFoundError(ZerodhaError):
    """Raised when a symbol cannot be resolved to an instrument token."""

    def __init__(
        self,
        message: str,
        *,
        symbol: str | None = None,
        exchange: str | None = None,
        status_code: int | None = None,
        response_data: Any = None,
    ) -> None:
        super().__init__(message, status_code=status_code, response_data=response_data)
        self.symbol = symbol
        self.exchange = exchange


class ZerodhaAPIError(ZerodhaError):
    """Raised for other API errors (5xx, network errors, etc.)."""