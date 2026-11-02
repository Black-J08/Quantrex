"""Shoonya-specific exceptions."""

from __future__ import annotations


class ShoonyaError(Exception):
    """Base exception for all Shoonya errors."""

    def __init__(self, message: str, error_type: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.error_type = error_type
        self.status_code = status_code


class ShoonyaAuthError(ShoonyaError):
    """Authentication/authorization error (403, token expired, invalid token)."""

    def __init__(self, message: str = "Authentication failed", status_code: int = 403):
        super().__init__(message, error_type="TokenException", status_code=status_code)


class ShoonyaTokenExpiredError(ShoonyaAuthError):
    """Access token has expired or been invalidated."""

    def __init__(self, message: str = "Access token expired"):
        super().__init__(message, status_code=403)


class ShoonyaRateLimitError(ShoonyaError):
    """Rate limit exceeded (429)."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: float | None = None):
        super().__init__(message, error_type="RateLimitException", status_code=429)
        self.retry_after = retry_after


class ShoonyaNetworkError(ShoonyaError):
    """Network-level error (connection failed, timeout, DNS)."""

    def __init__(self, message: str = "Network error", original_error: Exception | None = None):
        super().__init__(message, error_type="NetworkException")
        self.original_error = original_error


class ShoonyaServerError(ShoonyaError):
    """Server error (500, 502, 503, 504)."""

    def __init__(self, message: str = "Server error", status_code: int = 500):
        super().__init__(message, error_type="GeneralException", status_code=status_code)


class ShoonyaInputError(ShoonyaError):
    """Invalid input parameters (400)."""

    def __init__(self, message: str = "Invalid input", status_code: int = 400):
        super().__init__(message, error_type="InputException", status_code=status_code)


class ShoonyaNotFoundError(ShoonyaError):
    """Resource not found (404)."""

    def __init__(self, message: str = "Resource not found", status_code: int = 404):
        super().__init__(message, error_type="NotFoundException", status_code=status_code)


class ShoonyaOrderError(ShoonyaError):
    """Order-related error."""

    def __init__(self, message: str = "Order error", status_code: int = 400):
        super().__init__(message, error_type="OrderException", status_code=status_code)


class ShoonyaMarginError(ShoonyaError):
    """Insufficient margin error."""

    def __init__(self, message: str = "Insufficient margin", status_code: int = 400):
        super().__init__(message, error_type="MarginException", status_code=status_code)


class ShoonyaHoldingError(ShoonyaError):
    """Insufficient holdings error."""

    def __init__(self, message: str = "Insufficient holdings", status_code: int = 400):
        super().__init__(message, error_type="HoldingException", status_code=status_code)


class ShoonyaUserError(ShoonyaError):
    """User account related error."""

    def __init__(self, message: str = "User error", status_code: int = 400):
        super().__init__(message, error_type="UserException", status_code=status_code)


class ShoonyaDataError(ShoonyaError):
    """Internal data error."""

    def __init__(self, message: str = "Data error", status_code: int = 500):
        super().__init__(message, error_type="DataException", status_code=status_code)


class InstrumentMasterError(ShoonyaError):
    """Base exception for instrument master errors."""

    def __init__(self, message: str = "Instrument master error"):
        super().__init__(message, error_type="InstrumentMasterException")
