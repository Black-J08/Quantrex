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

        # Set access token and client-id if provided up front. The Dhan v2
        # gateway requires BOTH on every request: ``access-token`` for auth and
        # ``client-id`` to identify the client. Missing ``client-id`` causes
        # the gateway to return 301/400 instead of the expected JSON response
        # (verified against dhan-oss/DhanHQ-py SDK behaviour).
        if config.access_token:
            self._client.headers["access-token"] = config.access_token
        if config.client_id:
            self._client.headers["client-id"] = config.client_id

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

    def _get_client_id(self) -> str:
        """Get client ID from config or environment."""
        if self._config.client_id:
            return self._config.client_id

        # Fall back to the env var. The config-time resolution already tried
        # this and the JWT claim, but the env may have been populated after
        # the config was built (e.g. via load_dotenv at process start).
        import os

        env_value = os.getenv("DHAN_CLIENT_ID")
        if env_value:
            return env_value

        raise DhanAuthenticationError(
            "DHAN_CLIENT_ID not found. Set it via the DhanProviderConfig, "
            "the DHAN_CLIENT_ID environment variable, or ensure it can be "
            "extracted from the access-token JWT (claim: dhanClientId)."
        )

    def _ensure_auth(self) -> None:
        """Ensure both ``access-token`` and ``client-id`` headers are set.

        Dhan's gateway requires both headers; sending one without the other
        produces a 301/HTML or 400/JSON response instead of the expected
        success payload. The two are read fresh on every call so that callers
        who set the env var after constructing the client (e.g. via
        ``load_dotenv`` in a script's module-import path) still work.
        """
        token = self._get_access_token()
        self._client.headers["access-token"] = token
        client_id = self._get_client_id()
        self._client.headers["client-id"] = client_id

    @staticmethod
    def _safe_response_json(response: httpx.Response) -> Any:
        """Parse response body as JSON, tolerating non-JSON payloads.

        Dhan's gateway can return HTML (e.g. a 301 Moved Permanently sign-in
        page) for failed auth, transient redirects, or CDN edge errors.
        Calling ``response.json()`` directly on those bodies raises
        ``JSONDecodeError`` and masks the real status code. This helper
        returns ``None`` when the body is not valid JSON, and includes a
        short text preview so debugging context is never lost.
        """
        if not response.content:
            return None
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type.lower():
            # Non-JSON content type (HTML, plain text, etc.) - return a
            # minimal dict so the original error message survives in logs.
            text_preview = response.text[:200]
            return {"raw_body": text_preview, "content_type": content_type}
        try:
            return response.json()
        except Exception:
            text_preview = response.text[:200]
            return {"raw_body": text_preview, "content_type": content_type}

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
                response_data=self._safe_response_json(response),
            )

        if response.status_code == 429:
            raise DhanRateLimitError(
                "Rate limit exceeded. Please retry after 1 second.",
                status_code=response.status_code,
                response_data=self._safe_response_json(response),
            )

        if response.status_code == 400:
            error_data = self._safe_response_json(response)
            # Dhan returns errorCode as either int or string depending on the
            # gateway version; normalize so the typed mapping below works.
            raw_code = error_data.get("errorCode") if isinstance(error_data, dict) else None
            normalized_code: int | None = None
            if isinstance(raw_code, int):
                normalized_code = raw_code
            elif isinstance(raw_code, str) and raw_code.isdigit():
                normalized_code = int(raw_code)
            if normalized_code in (812, 813, 814):
                raise DhanInvalidParameterError(
                    "Invalid request parameters.",
                    error_code=normalized_code,
                    status_code=response.status_code,
                    response_data=error_data,
                )
            raise DhanInvalidParameterError(
                "Invalid request parameters.",
                status_code=response.status_code,
                response_data=error_data,
            )

        if response.status_code >= 500:
            raise DhanAPIError(
                f"Server error: {response.status_code}",
                status_code=response.status_code,
                response_data=self._safe_response_json(response),
            )

        if response.status_code != 200:
            raise DhanAPIError(
                f"API error: {response.status_code}",
                status_code=response.status_code,
                response_data=self._safe_response_json(response),
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
        payload = request.model_dump(by_alias=True)
        # Dhan v2 requires dhanClientId in the request body on every call. The
        # model carries an empty default; we overwrite it here so the value is
        # always sourced from the resolved client_id (config / env / JWT claim).
        payload["dhanClientId"] = self._get_client_id()
        data = self._request("POST", "/charts/historical", payload)

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
        payload = request.model_dump(by_alias=True)
        payload["dhanClientId"] = self._get_client_id()
        data = self._request("POST", "/charts/intraday", payload)

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