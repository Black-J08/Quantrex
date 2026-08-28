"""HTTP client for Dhan API with rate limiting and retry logic."""

import time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import DhanProviderConfig
from .exceptions import (
    DhanAPIError,
    DhanAuthenticationError,
    DhanDataNotFoundError,
    DhanInvalidParameterError,
    DhanRateLimitError,
)
from .models import HistoricalDataRequest, HistoricalDataResponse, IntradayDataRequest, IntradayDataResponse


class TokenBucketRateLimiter:
    """Token bucket rate limiter for API requests."""

    def __init__(self, rate: float, burst: int = 1) -> None:
        """Initialize rate limiter.

        Args:
            rate: Requests per second.
            burst: Maximum burst size (tokens).
        """
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_update = time.monotonic()

    def acquire(self) -> None:
        """Acquire a token, blocking until available."""
        while True:
            now = time.monotonic()
            elapsed = now - self._last_update
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_update = now

            if self._tokens >= 1:
                self._tokens -= 1
                return

            # Wait for next token
            wait_time = (1 - self._tokens) / self._rate
            time.sleep(wait_time)


class DhanAPIClient:
    """HTTP client for DhanHQ API with rate limiting, retry logic, and error handling."""

    def __init__(self, config: DhanProviderConfig) -> None:
        """Initialize Dhan API client.

        Args:
            config: Provider configuration.
        """
        self._config = config
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        self._rate_limiter = TokenBucketRateLimiter(rate=5.0, burst=5)  # 5 req/sec for Data APIs

        # Set access token if provided
        if config.access_token:
            self._client.headers["access-token"] = config.access_token

    def _get_access_token(self) -> str:
        """Get access token from config or environment."""
        if self._config.access_token:
            return self._config.access_token

        # Try to load from environment
        import os
        from dotenv import load_dotenv

        load_dotenv()
        token = os.getenv("DHAN_ACCESS_TOKEN")
        if not token:
            raise DhanAuthenticationError("DHAN_ACCESS_TOKEN not found in environment or .env file")
        return token

    def _ensure_auth(self) -> None:
        """Ensure access token is set in headers."""
        token = self._get_access_token()
        self._client.headers["access-token"] = token

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((DhanRateLimitError, httpx.HTTPError)),
        reraise=True,
    )
    def _request(self, method: str, endpoint: str, json_data: dict | None = None) -> dict:
        """Make HTTP request with rate limiting and retry logic.

        Args:
            method: HTTP method (GET, POST).
            endpoint: API endpoint path.
            json_data: JSON request body.

        Returns:
            Parsed JSON response.

        Raises:
            DhanAuthenticationError: 401/403 errors.
            DhanRateLimitError: 429 errors.
            DhanInvalidParameterError: 400 errors with error codes.
            DhanDataNotFoundError: Empty data response.
            DhanAPIError: Other API errors.
        """
        self._ensure_auth()
        self._rate_limiter.acquire()

        try:
            response = self._client.request(method, endpoint, json=json_data)
        except httpx.TimeoutException as e:
            raise DhanAPIError(f"Request timeout: {e}") from e
        except httpx.HTTPError as e:
            raise DhanAPIError(f"HTTP error: {e}") from e

        # Handle HTTP status codes
        if response.status_code == 401 or response.status_code == 403:
            raise DhanAuthenticationError(
                "Authentication failed. Check your access token.",
                status_code=response.status_code,
                response_data=response.json() if response.content else None,
            )

        if response.status_code == 429:
            raise DhanRateLimitError(
                "Rate limit exceeded. Please retry after 1 second.",
                status_code=response.status_code,
                response_data=response.json() if response.content else None,
            )

        if response.status_code == 400:
            try:
                error_data = response.json()
                error_code = error_data.get("errorCode")
                if error_code in (812, 813, 814):
                    raise DhanInvalidParameterError(
                        "Invalid request parameters.",
                        error_code=error_code,
                        status_code=response.status_code,
                        response_data=error_data,
                    )
            except Exception:
                pass
            raise DhanInvalidParameterError(
                "Invalid request parameters.",
                status_code=response.status_code,
                response_data=response.json() if response.content else None,
            )

        if response.status_code >= 500:
            raise DhanAPIError(
                f"Server error: {response.status_code}",
                status_code=response.status_code,
                response_data=response.json() if response.content else None,
            )

        if response.status_code != 200:
            raise DhanAPIError(
                f"API error: {response.status_code}",
                status_code=response.status_code,
                response_data=response.json() if response.content else None,
            )

        # Parse response
        try:
            data = response.json()
        except Exception as e:
            raise DhanAPIError(f"Failed to parse JSON response: {e}") from e

        # Check for API-level errors
        if isinstance(data, dict) and data.get("status") == "failure":
            error_type = data.get("errorType", "")
            error_code = data.get("errorCode", "")
            error_message = data.get("errorMessage", "Unknown error")

            if error_type == "RATE_LIMIT_ERROR" or error_code == "RL001":
                raise DhanRateLimitError(error_message, status_code=429, response_data=data)

            if error_code in ("812", "813", "814"):
                raise DhanInvalidParameterError(
                    error_message,
                    error_code=int(error_code) if error_code.isdigit() else None,
                    status_code=400,
                    response_data=data,
                )

            raise DhanAPIError(error_message, status_code=400, response_data=data)

        return data

    def get_daily_historical(self, request: HistoricalDataRequest) -> HistoricalDataResponse:
        """Get daily historical data.

        Args:
            request: Historical data request parameters.

        Returns:
            Parsed historical data response.

        Raises:
            DhanDataNotFoundError: If no data returned.
        """
        data = self._request("POST", "/charts/historical", request.model_dump(by_alias=True, exclude_none=True))

        if not data or not data.get("timestamp"):
            raise DhanDataNotFoundError("No historical data returned for the given parameters")

        response = HistoricalDataResponse(**data)
        response.validate_lengths()
        return response

    def get_intraday_historical(self, request: IntradayDataRequest) -> IntradayDataResponse:
        """Get intraday historical data.

        Args:
            request: Intraday data request parameters.

        Returns:
            Parsed intraday data response.

        Raises:
            DhanDataNotFoundError: If no data returned.
        """
        data = self._request("POST", "/charts/intraday", request.model_dump(by_alias=True, exclude_none=True))

        if not data or not data.get("timestamp"):
            raise DhanDataNotFoundError("No intraday data returned for the given parameters")

        response = IntradayDataResponse(**data)
        response.validate_lengths()
        return response

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> "DhanAPIClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()