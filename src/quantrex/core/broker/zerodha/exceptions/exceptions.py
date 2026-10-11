"""Zerodha-specific exceptions."""

from __future__ import annotations


class ZerodhaError(Exception):
    """Base exception for all Zerodha errors."""

    def __init__(self, message: str, error_type: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.error_type = error_type
        self.status_code = status_code


class ZerodhaAuthError(ZerodhaError):
    """Authentication/authorization error (403, token expired, invalid token)."""

    def __init__(self, message: str = "Authentication failed", status_code: int = 403):
        super().__init__(message, error_type="TokenException", status_code=status_code)


class ZerodhaTokenExpiredError(ZerodhaAuthError):
    """Access token has expired (6 AM daily expiry)."""

    def __init__(self, message: str = "Access token expired"):
        super().__init__(message, status_code=403)


class ZerodhaRateLimitError(ZerodhaError):
    """Rate limit exceeded (429)."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: float | None = None):
        super().__init__(message, error_type="RateLimitException", status_code=429)
        self.retry_after = retry_after


class ZerodhaNetworkError(ZerodhaError):
    """Network-level error (connection failed, timeout, DNS)."""

    def __init__(self, message: str = "Network error", original_error: Exception | None = None):
        super().__init__(message, error_type="NetworkException")
        self.original_error = original_error


class ZerodhaServerError(ZerodhaError):
    """Server error (500, 502, 503, 504)."""

    def __init__(self, message: str = "Server error", status_code: int = 500):
        super().__init__(message, error_type="GeneralException", status_code=status_code)


class ZerodhaInputError(ZerodhaError):
    """Invalid input parameters (400)."""

    def __init__(self, message: str = "Invalid input", status_code: int = 400):
        super().__init__(message, error_type="InputException", status_code=status_code)


class ZerodhaNotFoundError(ZerodhaError):
    """Resource not found (404)."""

    def __init__(self, message: str = "Resource not found", status_code: int = 404):
        super().__init__(message, error_type="NotFoundException", status_code=status_code)


class ZerodhaOrderError(ZerodhaError):
    """Order-related error."""

    def __init__(self, message: str = "Order error", status_code: int = 400):
        super().__init__(message, error_type="OrderException", status_code=status_code)


class ZerodhaMarginError(ZerodhaError):
    """Insufficient margin error."""

    def __init__(self, message: str = "Insufficient margin", status_code: int = 400):
        super().__init__(message, error_type="MarginException", status_code=status_code)


class ZerodhaHoldingError(ZerodhaError):
    """Insufficient holdings error."""

    def __init__(self, message: str = "Insufficient holdings", status_code: int = 400):
        super().__init__(message, error_type="HoldingException", status_code=status_code)


class ZerodhaUserError(ZerodhaError):
    """User account related error."""

    def __init__(self, message: str = "User error", status_code: int = 400):
        super().__init__(message, error_type="UserException", status_code=status_code)


class ZerodhaDataError(ZerodhaError):
    """Internal data error."""

    def __init__(self, message: str = "Data error", status_code: int = 500):
        super().__init__(message, error_type="DataException", status_code=status_code)


# Instrument Master Exceptions
class InstrumentMasterError(ZerodhaError):
    """Base exception for instrument master errors."""

    def __init__(self, message: str = "Instrument master error"):
        super().__init__(message, error_type="InstrumentMasterException")


class SymbolNotFoundError(InstrumentMasterError):
    """Raised when a symbol cannot be resolved."""

    def __init__(self, symbol: str, suggestions: list[str] | None = None):
        self.symbol = symbol
        self.suggestions = suggestions or []
        msg = f"Symbol not found: {symbol}"
        if self.suggestions:
            msg += f". Did you mean: {', '.join(self.suggestions[:5])}?"
        super().__init__(msg)


class AmbiguousSymbolError(InstrumentMasterError):
    """Raised when a tradingsymbol maps to multiple exchanges."""

    def __init__(self, tradingsymbol: str, candidates: list):
        self.tradingsymbol = tradingsymbol
        self.candidates = candidates
        exchanges = [f"{c.exchange}:{c.tradingsymbol}" for c in candidates]
        msg = f"Ambiguous symbol '{tradingsymbol}' matches multiple exchanges: {', '.join(exchanges)}"
        super().__init__(msg)