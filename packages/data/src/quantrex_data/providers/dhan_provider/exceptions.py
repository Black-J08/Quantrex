"""Exceptions for Dhan Data Provider."""

from typing import Any


class DhanAPIError(Exception):
    """Base exception for Dhan API errors."""

    def __init__(self, message: str, status_code: int | None = None, response_data: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class DhanAuthenticationError(DhanAPIError):
    """Raised when authentication fails (401/403)."""

    def __init__(self, message: str = "Authentication failed. Check your access token.", status_code: int | None = None, response_data: Any = None) -> None:
        super().__init__(message, status_code, response_data)


class DhanRateLimitError(DhanAPIError):
    """Raised when rate limit is exceeded (429, RL001)."""

    def __init__(self, message: str = "Rate limit exceeded. Please retry after 1 second.", status_code: int | None = None, response_data: Any = None) -> None:
        super().__init__(message, status_code, response_data)


class DhanDataNotFoundError(DhanAPIError):
    """Raised when no data is found for the given parameters."""

    def __init__(self, message: str = "No data found for the given parameters.", status_code: int | None = None, response_data: Any = None) -> None:
        super().__init__(message, status_code, response_data)


class DhanInvalidParameterError(DhanAPIError):
    """Raised when request parameters are invalid (400, error codes 812, 813, 814)."""

    ERROR_CODES = {
        812: "Invalid Date Format",
        813: "Invalid SecurityId",
        814: "Invalid Request",
    }

    def __init__(
        self,
        message: str = "Invalid request parameters.",
        error_code: int | None = None,
        status_code: int | None = None,
        response_data: Any = None,
    ) -> None:
        if error_code and error_code in self.ERROR_CODES:
            message = f"{message} (Error {error_code}: {self.ERROR_CODES[error_code]})"
        super().__init__(message, status_code, response_data)
        self.error_code = error_code


class DhanSymbolNotFoundError(DhanAPIError):
    """Raised when a trading symbol is not found in the instrument master."""

    def __init__(
        self,
        symbol: str,
        exchange_segment: str,
        message: str | None = None,
        status_code: int | None = None,
        response_data: Any = None,
    ) -> None:
        if message is None:
            message = f"Symbol '{symbol}' not found in instrument master for exchange segment '{exchange_segment}'"
        super().__init__(message, status_code, response_data)
        self.symbol = symbol
        self.exchange_segment = exchange_segment


class DhanInstrumentMasterError(DhanAPIError):
    """Raised when instrument master CSV download or parsing fails."""

    def __init__(
        self,
        message: str = "Failed to download or parse instrument master CSV.",
        status_code: int | None = None,
        response_data: Any = None,
    ) -> None:
        super().__init__(message, status_code, response_data)