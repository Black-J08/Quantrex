"""Zerodha HTTP session with lazy authentication."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self
from urllib.parse import urlparse

import httpx

from quantrex.core.broker.zerodha.auth.provider import ZerodhaAuthProvider
from quantrex.core.broker.zerodha.auth.token_store import TokenInfo
from quantrex.core.broker.zerodha.exceptions.exceptions import (
    ZerodhaInputError,
    ZerodhaNetworkError,
    ZerodhaNotFoundError,
    ZerodhaRateLimitError,
    ZerodhaServerError,
    ZerodhaTokenExpiredError,
)
from quantrex.core.utility.rate_limiter import SlidingWindowRateLimiter

logger = logging.getLogger(__name__)

# Constants
BASE_URL = "https://api.kite.trade"
DEFAULT_TIMEOUT = 30.0


@dataclass(slots=True, frozen=True)
class CallbackConfig:
    """Parsed callback configuration from redirect URL."""

    host: str
    port: int
    path: str

    @classmethod
    def from_redirect_url(cls, redirect_url: str) -> CallbackConfig:
        """Parse redirect URL to extract callback configuration.

        Args:
            redirect_url: Full redirect URL (e.g., "http://localhost:8765/callback")

        Returns:
            CallbackConfig with host, port, and path
        """
        parsed = urlparse(redirect_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid redirect URL: {redirect_url}")

        # Extract host and port
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        # Extract path (default to /callback if empty)
        path = parsed.path or "/callback"

        return cls(host=host, port=port, path=path)


class ZerodhaSession:
    """HTTP session for Zerodha Kite Connect API with lazy authentication.

    Features:
    - Lazy authentication: token fetched only when first API request needs it
    - Automatic token refresh on 403 errors
    - Rate limiting for historical data endpoint
    - Connection pooling via httpx.AsyncClient
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        token_path: str | None = None,
        redirect_url: str | None = None,
        callback_timeout: float | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """Initialize Zerodha session.

        Args:
            api_key: Zerodha API key (defaults to ZERODHA_API_KEY env var)
            api_secret: Zerodha API secret (defaults to ZERODHA_API_SECRET env var)
            token_path: Path to token file (defaults to ~/.quantrex/cache/zerodha/access_token)
            redirect_url: Full redirect URL configured in Zerodha console (defaults to ZERODHA_REDIRECT_URL env var)
            callback_timeout: Timeout for OAuth callback in seconds (defaults to ZERODHA_CALLBACK_TIMEOUT env var or 120.0)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or os.getenv("ZERODHA_API_KEY")
        self.api_secret = api_secret or os.getenv("ZERODHA_API_SECRET")

        if not self.api_key or not self.api_secret:
            raise ValueError("API key and secret are required (set ZERODHA_API_KEY and ZERODHA_API_SECRET)")

        # Token storage
        if token_path is None:
            cache_dir = Path.home() / ".quantrex" / "cache" / "zerodha"
            cache_dir.mkdir(parents=True, exist_ok=True)
            token_path = str(cache_dir / "access_token")
        self.token_path = Path(token_path)

        # Parse redirect URL for callback configuration
        redirect_url = redirect_url or os.getenv("ZERODHA_REDIRECT_URL")
        if not redirect_url:
            raise ValueError("Redirect URL is required (set ZERODHA_REDIRECT_URL env var or pass redirect_url parameter)")

        callback_config = CallbackConfig.from_redirect_url(redirect_url)
        self.callback_host = callback_config.host
        self.callback_port = callback_config.port
        self.callback_path = callback_config.path
        self.callback_timeout = callback_timeout or float(os.getenv("ZERODHA_CALLBACK_TIMEOUT", "120.0"))

        # Auth provider
        self._auth_provider = ZerodhaAuthProvider(
            api_key=self.api_key,
            api_secret=self.api_secret,
            token_path=str(self.token_path),
            callback_host=self.callback_host,
            callback_port=self.callback_port,
            callback_timeout=self.callback_timeout,
        )

        # HTTP client
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=timeout,
            headers={"X-Kite-Version": "3"},
        )

        # Shared rate limiters, keyed by endpoint name.
        # All clients using this session share the same limiter instances,
        # so concurrent requests across clients are paced together.
        self._limiters: dict[str, SlidingWindowRateLimiter] = {}
        self._limiters["historical"] = SlidingWindowRateLimiter(3.0)

        # Token cache
        self._token_info: TokenInfo | None = None
        self._token_lock = asyncio.Lock()

    async def _get_valid_token(self) -> str:
        """Get a valid access token, authenticating if necessary."""
        async with self._token_lock:
            # Check cached token
            if self._token_info and self._token_info.is_valid():
                return self._token_info.access_token

            # Load from file
            token_info = await self._auth_provider.load_token()
            if token_info and token_info.is_valid():
                self._token_info = token_info
                return token_info.access_token

            # Need to authenticate
            logger.info("No valid token found, starting authentication...")
            token_info = await self._auth_provider.authenticate()
            self._token_info = token_info
            return token_info.access_token

    def _build_auth_header(self, access_token: str) -> str:
        """Build Authorization header value."""
        return f"token {self.api_key}:{access_token}"

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make an authenticated HTTP request with retry on 403.

        Rate limiting is not enforced here — clients are responsible for
        acquiring capacity from the appropriate shared limiter (e.g.,
        ``session.historical_limiter.acquire()``) before making a request.
        """
        access_token = await self._get_valid_token()
        request_headers = {"Authorization": self._build_auth_header(access_token)}
        if headers:
            request_headers.update(headers)

        try:
            response = await self._client.request(
                method=method,
                url=path,
                params=params,
                json=json,
                headers=request_headers,
            )
        except httpx.RequestError as e:
            logger.error("Request failed: %s", e)
            raise ZerodhaNetworkError(f"Request failed: {e}", original_error=e) from e

        # Handle 403 - token expired, retry once with fresh token
        if response.status_code == 403:
            logger.warning("Received 403, token may be expired, retrying with fresh token")
            async with self._token_lock:
                self._token_info = None  # Force re-auth
            access_token = await self._get_valid_token()
            request_headers["Authorization"] = self._build_auth_header(access_token)

            try:
                response = await self._client.request(
                    method=method,
                    url=path,
                    params=params,
                    json=json,
                    headers=request_headers,
                )
            except httpx.RequestError as e:
                logger.error("Retry request failed: %s", e)
                raise ZerodhaNetworkError(f"Retry request failed: {e}", original_error=e) from e

        # Handle other error status codes
        self._handle_error_response(response)

        return response

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Handle error responses from Zerodha API."""
        if response.status_code == 400:
            raise ZerodhaInputError(f"Bad request: {response.text}")
        elif response.status_code == 403:
            raise ZerodhaTokenExpiredError("Access token expired or invalid")
        elif response.status_code == 404:
            raise ZerodhaNotFoundError(f"Resource not found: {response.text}")
        elif response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise ZerodhaRateLimitError(
                "Rate limit exceeded",
                retry_after=float(retry_after) if retry_after else None,
            )
        elif 500 <= response.status_code < 600:
            raise ZerodhaServerError(f"Server error: {response.text}", status_code=response.status_code)

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make a GET request."""
        return await self._request("GET", path, params=params)

    async def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make a POST request."""
        return await self._request("POST", path, json=json, params=params)

    async def delete(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make a DELETE request."""
        return await self._request("DELETE", path, params=params)

    @property
    def historical_limiter(self) -> SlidingWindowRateLimiter:
        """Shared rate limiter for historical data endpoints.

        All clients using this session share the same limiter instance, so
        concurrent requests across clients are paced together at the
        configured rate (3 requests per second).
        """
        return self._limiters["historical"]

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
