"""HTTP client for Zerodha API with rate limiting and retry logic."""

import hashlib
import time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from quantrex_core.logging import get_logger

from .config import ZerodhaProviderConfig
from .exceptions import (
    ZerodhaAPIError,
    ZerodhaAuthenticationError,
    ZerodhaDataNotFoundError,
    ZerodhaInvalidParameterError,
    ZerodhaRateLimitError,
)
from .models import HistoricalDataResponse

logger = get_logger(__name__)


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


class ZerodhaAPIClient:
    """HTTP client for Zerodha Kite Connect API with rate limiting, retry logic, and error handling."""

    # Rate limits per endpoint type (requests per second)
    HISTORICAL_RATE = 3.0  # 3 req/sec for historical data
    DEFAULT_RATE = 10.0    # 10 req/sec for other endpoints

    def __init__(self, config: ZerodhaProviderConfig) -> None:
        """Initialize Zerodha API client.

        Args:
            config: Provider configuration.
        """
        self._config = config
        self._access_token = config.access_token
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Kite-Version": "3",
            },
        )
        # Separate rate limiters for different endpoint types
        self._historical_limiter = TokenBucketRateLimiter(rate=self.HISTORICAL_RATE, burst=3)
        self._default_limiter = TokenBucketRateLimiter(rate=self.DEFAULT_RATE, burst=10)

        # Set authorization header if access token is available
        if self._access_token:
            self._client.headers["Authorization"] = f"token {config.api_key}:{self._access_token}"

    def _ensure_auth(self) -> None:
        """Ensure Authorization header is set with current access token."""
        if not self._access_token:
            raise ZerodhaAuthenticationError("No access token available. Complete login flow first.")
        self._client.headers["Authorization"] = f"token {self._config.api_key}:{self._access_token}"

    def update_access_token(self, access_token: str) -> None:
        """Update the access token and refresh the Authorization header.

        Args:
            access_token: New access token.
        """
        self._access_token = access_token
        self._client.headers["Authorization"] = f"token {self._config.api_key}:{access_token}"
        logger.debug("Updated access token in client headers")

    @staticmethod
    def _safe_response_json(response: httpx.Response) -> Any:
        """Parse response body as JSON, tolerating non-JSON payloads.

        Zerodha can return HTML for errors (e.g., 502/503). This helper
        returns a dict with raw body preview when JSON parsing fails.

        Args:
            response: HTTP response.

        Returns:
            Parsed JSON or dict with raw_body preview.
        """
        if not response.content:
            return None
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type.lower():
            text_preview = response.text[:500]
            return {"raw_body": text_preview, "content_type": content_type}
        try:
            return response.json()
        except Exception:
            text_preview = response.text[:500]
            return {"raw_body": text_preview, "content_type": content_type}

    def _get_rate_limiter(self, endpoint: str) -> TokenBucketRateLimiter:
        """Get appropriate rate limiter for endpoint.

        Args:
            endpoint: API endpoint path.

        Returns:
            Rate limiter instance.
        """
        if "/instruments/historical/" in endpoint:
            return self._historical_limiter
        return self._default_limiter

    def _requires_auth(self, endpoint: str) -> bool:
        """Check if endpoint requires authentication.

        Args:
            endpoint: API endpoint path.

        Returns:
            True if endpoint requires auth, False otherwise.
        """
        # Token exchange endpoint doesn't require access token
        if endpoint == "/session/token":
            return False
        return True

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((ZerodhaRateLimitError, httpx.HTTPError)),
        reraise=True,
    )
    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json_data: dict | None = None,
        data: dict | None = None,
    ) -> dict:
        """Make HTTP request with rate limiting and retry logic.

        Args:
            method: HTTP method (GET, POST).
            endpoint: API endpoint path.
            params: Query parameters.
            json_data: JSON request body.
            data: Form data request body.

        Returns:
            Parsed JSON response.

        Raises:
            ZerodhaAuthenticationError: 403/TokenException errors.
            ZerodhaRateLimitError: 429 errors.
            ZerodhaInvalidParameterError: 400/InputException errors.
            ZerodhaDataNotFoundError: Empty data response.
            ZerodhaAPIError: Other API errors.
        """
        if self._requires_auth(endpoint):
            self._ensure_auth()
        limiter = self._get_rate_limiter(endpoint)
        limiter.acquire()

        # Set appropriate Content-Type for form data
        if data is not None:
            self._client.headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif json_data is not None:
            self._client.headers["Content-Type"] = "application/json"

        try:
            response = self._client.request(method, endpoint, params=params, json=json_data, data=data)
        except httpx.TimeoutException as e:
            raise ZerodhaAPIError(f"Request timeout: {e}") from e
        except httpx.HTTPError as e:
            raise ZerodhaAPIError(f"HTTP error: {e}") from e

        # Handle HTTP status codes
        if response.status_code == 403:
            error_data = self._safe_response_json(response)
            # Check for TokenException in response
            error_type = error_data.get("error_type") if isinstance(error_data, dict) else None
            if error_type == "TokenException" or response.status_code == 403:
                raise ZerodhaAuthenticationError(
                    "Authentication failed: token expired or invalid (TokenException). "
                    "Re-login required.",
                    status_code=response.status_code,
                    response_data=error_data,
                )

        if response.status_code == 429:
            raise ZerodhaRateLimitError(
                "Rate limit exceeded. Please retry after 1 second.",
                status_code=response.status_code,
                response_data=self._safe_response_json(response),
            )

        if response.status_code == 400:
            error_data = self._safe_response_json(response)
            error_type = error_data.get("error_type") if isinstance(error_data, dict) else None
            error_message = error_data.get("message", "Invalid request parameters") if isinstance(error_data, dict) else "Invalid request parameters"
            if error_type == "InputException":
                raise ZerodhaInvalidParameterError(
                    error_message,
                    status_code=response.status_code,
                    response_data=error_data,
                )
            raise ZerodhaInvalidParameterError(
                error_message,
                status_code=response.status_code,
                response_data=error_data,
            )

        if response.status_code >= 500:
            raise ZerodhaAPIError(
                f"Server error: {response.status_code}",
                status_code=response.status_code,
                response_data=self._safe_response_json(response),
            )

        if response.status_code != 200:
            raise ZerodhaAPIError(
                f"API error: {response.status_code}",
                status_code=response.status_code,
                response_data=self._safe_response_json(response),
            )

        # Parse response
        try:
            data = response.json()
        except Exception as e:
            raise ZerodhaAPIError(f"Failed to parse JSON response: {e}") from e

        # Check for API-level errors
        if isinstance(data, dict) and data.get("status") == "error":
            error_type = data.get("error_type", "")
            error_message = data.get("message", "Unknown error")

            if error_type == "TokenException":
                raise ZerodhaAuthenticationError(
                    error_message,
                    status_code=403,
                    response_data=data,
                )

            if error_type == "RateLimitException":
                raise ZerodhaRateLimitError(
                    error_message,
                    status_code=429,
                    response_data=data,
                )

            if error_type == "InputException":
                raise ZerodhaInvalidParameterError(
                    error_message,
                    status_code=400,
                    response_data=data,
                )

            raise ZerodhaAPIError(
                error_message,
                status_code=400,
                response_data=data,
            )

        return data

    def get_historical_data(
        self,
        instrument_token: str,
        interval: str,
        from_date: str,
        to_date: str,
        continuous: bool = False,
        oi: bool = False,
    ) -> HistoricalDataResponse:
        """Get historical candle data.

        Args:
            instrument_token: Instrument token from instrument master.
            interval: Candle interval (minute, 3minute, 5minute, etc.).
            from_date: Start date in YYYY-MM-DD HH:MM:SS format.
            to_date: End date in YYYY-MM-DD HH:MM:SS format.
            continuous: Whether to get continuous futures data.
            oi: Whether to include open interest.

        Returns:
            Parsed historical data response.

        Raises:
            ZerodhaDataNotFoundError: If no data returned.
        """
        endpoint = f"/instruments/historical/{instrument_token}/{interval}"
        params = {
            "from": from_date,
            "to": to_date,
            "continuous": "1" if continuous else "0",
            "oi": "1" if oi else "0",
        }

        logger.debug(
            "Fetching historical data: instrument_token=%s, interval=%s, from=%s, to=%s",
            instrument_token,
            interval,
            from_date,
            to_date,
        )

        data = self._request("GET", endpoint, params=params)

        if not data or not data.get("data", {}).get("candles"):
            raise ZerodhaDataNotFoundError(
                f"No historical data returned for instrument_token={instrument_token}, "
                f"interval={interval}, from={from_date}, to={to_date}"
            )

        response = HistoricalDataResponse(**data)
        response.validate_lengths()
        return response

    def get_instruments(self, exchange: str | None = None) -> str:
        """Get instrument master CSV.

        Args:
            exchange: Optional exchange to filter (e.g., "NSE", "NFO").

        Returns:
            Raw CSV content as string.
        """
        if exchange:
            endpoint = f"/instruments/{exchange}"
        else:
            endpoint = "/instruments"

        logger.debug("Fetching instrument master (exchange=%s)", exchange or "all")

        # For CSV download, we need to handle non-JSON response
        self._ensure_auth()
        limiter = self._default_limiter
        limiter.acquire()

        try:
            response = self._client.get(endpoint)
        except httpx.TimeoutException as e:
            raise ZerodhaAPIError(f"Request timeout: {e}") from e
        except httpx.HTTPError as e:
            raise ZerodhaAPIError(f"HTTP error: {e}") from e

        if response.status_code == 403:
            raise ZerodhaAuthenticationError(
                "Authentication failed for instrument master download.",
                status_code=response.status_code,
            )

        if response.status_code != 200:
            raise ZerodhaAPIError(
                f"Failed to download instrument master: {response.status_code}",
                status_code=response.status_code,
            )

        return response.text

    def get_profile(self) -> dict:
        """Get user profile (used for token validation).

        Returns:
            User profile data.
        """
        data = self._request("GET", "/user/profile")
        return data.get("data", {})

    def generate_session(self, request_token: str) -> dict:
        """Exchange request_token for access_token (login flow step 2).

        Args:
            request_token: Request token obtained from login redirect.

        Returns:
            Session data including access_token.
        """
        # Calculate checksum: SHA256(api_key + request_token + api_secret)
        checksum = hashlib.sha256(
            f"{self._config.api_key}{request_token}{self._config.api_secret}".encode()
        ).hexdigest()

        payload = {
            "api_key": self._config.api_key,
            "request_token": request_token,
            "checksum": checksum,
        }

        logger.debug("Exchanging request_token for access_token")

        data = self._request("POST", "/session/token", json_data=payload)
        return data.get("data", {})

    def invalidate_token(self) -> bool:
        """Logout and invalidate the access token.

        Returns:
            True if successful.
        """
        params = {
            "api_key": self._config.api_key,
            "access_token": self._config.access_token,
        }

        data = self._request("DELETE", "/session/token", params=params)
        return data.get("data", False)

    def close(self) -> None:
        """Close the HTTP client."""
        logger.debug("Closing ZerodhaAPIClient")
        self._client.close()

    def __enter__(self) -> "ZerodhaAPIClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()