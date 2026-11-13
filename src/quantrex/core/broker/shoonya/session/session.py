"""Shoonya HTTP session with lazy authentication."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self
from urllib.parse import urlparse

import httpx

from quantrex.core.broker.shoonya.auth.provider import ShoonyaAuthProvider
from quantrex.core.broker.shoonya.auth.token_store import TokenInfo
from quantrex.core.broker.shoonya.exceptions.exceptions import (
    ShoonyaDataError,
    ShoonyaError,
    ShoonyaHoldingError,
    ShoonyaInputError,
    ShoonyaMarginError,
    ShoonyaNetworkError,
    ShoonyaNotFoundError,
    ShoonyaRateLimitError,
    ShoonyaServerError,
    ShoonyaTokenExpiredError,
)
from quantrex.core.utility.rate_limiter import SlidingWindowRateLimiter

logger = logging.getLogger(__name__)

# Constants
BASE_URL = "https://api.shoonya.com/NorenWClientAPI/"
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


@dataclass(slots=True)
class SessionConfig:
    """Configuration for ShoonyaSession.

    Groups all session configuration into a single object to reduce
    constructor parameter count and improve clarity.
    """

    client_id: str | None = None
    secret_key: str | None = None
    oauth_client_id: str | None = None
    token_path: str | None = None
    redirect_url: str | None = None
    callback_timeout: float | None = None
    timeout: float = DEFAULT_TIMEOUT


class ShoonyaSession:
    """HTTP session for Shoonya API with lazy authentication.

    Features:
    - Lazy authentication: token fetched only when first API request needs it
    - Automatic token refresh on 403 errors
    - Rate limiting for historical data endpoint
    - Connection pooling via httpx.AsyncClient
    - Shoonya request format: Content-Type: text/plain with jData field
    - Shoonya auth header: Authorization: Bearer <AccessToken>
    - Shoonya response validation: stat/emsg field checking
    """

    def __init__(
        self,
        config: SessionConfig | None = None,
    ):
        """Initialize Shoonya session.

        Args:
            config: SessionConfig providing all configuration. Fields not set
                are resolved from environment variables.
        """
        config = config or SessionConfig()

        self.client_id, self.secret_key = self._resolve_credentials(
            config.client_id, config.secret_key
        )
        self.oauth_client_id = self._resolve_oauth_client_id(
            config.oauth_client_id, self.client_id
        )
        self.token_path = self._resolve_token_path(config.token_path)
        (
            self.callback_host,
            self.callback_port,
            self.callback_path,
            self.callback_timeout,
        ) = self._resolve_callback_config(config.redirect_url, config.callback_timeout)

        self._auth_provider = self._build_auth_provider()
        self._client = self._build_http_client(config.timeout)
        self._limiters: dict[str, SlidingWindowRateLimiter] = {}
        self._limiters["historical"] = SlidingWindowRateLimiter(3.0)
        self._token_info: TokenInfo | None = None
        self._token_lock = asyncio.Lock()

    @staticmethod
    def _resolve_credentials(
        client_id: str | None,
        secret_key: str | None,
    ) -> tuple[str, str]:
        """Resolve client ID and secret key from arguments or environment variables."""
        resolved_client_id = client_id or os.getenv("SHOONYA_CLIENT_ID")
        resolved_secret_key = secret_key or os.getenv("SHOONYA_SECRET_KEY")

        if not resolved_client_id or not resolved_secret_key:
            raise ValueError(
                "Client ID and secret key are required "
                "(set SHOONYA_CLIENT_ID and SHOONYA_SECRET_KEY)"
            )

        return resolved_client_id, resolved_secret_key

    @staticmethod
    def _resolve_oauth_client_id(
        oauth_client_id: str | None,
        client_id: str,
    ) -> str:
        """Resolve OAuth client ID from arguments or environment variables.

        Falls back to the regular client_id if no OAuth-specific client ID
        is provided, maintaining backward compatibility.
        """
        return oauth_client_id or os.getenv("SHOONYA_OAUTH_CLIENT_ID") or client_id

    @staticmethod
    def _resolve_token_path(token_path: str | None) -> Path:
        """Resolve the token file path, creating the default cache directory if needed."""
        if token_path is None:
            cache_dir = Path.home() / ".quantrex" / "cache" / "shoonya"
            cache_dir.mkdir(parents=True, exist_ok=True)
            token_path = str(cache_dir / "access_token")
        return Path(token_path)

    @staticmethod
    def _resolve_callback_config(
        redirect_url: str | None,
        callback_timeout: float | None,
    ) -> tuple[str, int, str, float]:
        """Resolve redirect URL and callback configuration from arguments or environment."""
        redirect_url = redirect_url or os.getenv("SHOONYA_REDIRECT_URL")
        if not redirect_url:
            raise ValueError(
                "Redirect URL is required "
                "(set SHOONYA_REDIRECT_URL env var or pass redirect_url parameter)"
            )

        callback_config = CallbackConfig.from_redirect_url(redirect_url)
        resolved_timeout = callback_timeout or float(
            os.getenv("SHOONYA_CALLBACK_TIMEOUT", "120.0")
        )

        return (
            callback_config.host,
            callback_config.port,
            callback_config.path,
            resolved_timeout,
        )

    def _build_auth_provider(self) -> ShoonyaAuthProvider:
        """Build the Shoonya auth provider from resolved session state."""
        return ShoonyaAuthProvider(
            client_id=self.client_id,
            oauth_client_id=self.oauth_client_id,
            secret_key=self.secret_key,
            token_path=str(self.token_path),
            callback_host=self.callback_host,
            callback_port=self.callback_port,
            callback_timeout=self.callback_timeout,
        )

    def _build_http_client(self, timeout: float) -> httpx.AsyncClient:
        """Build the HTTP client with base URL, timeout, and default headers."""
        return httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=timeout,
        )

    async def _get_valid_token(self) -> str:
        """Get a valid access token, authenticating if necessary."""
        async with self._token_lock:
            return await self._get_valid_token_locked()

    async def _get_valid_token_locked(self) -> str:
        """Get a valid access token assuming the token lock is already held.

        Callers must hold ``self._token_lock`` before invoking this method.
        Used internally by error-retry paths that need to invalidate the token
        and obtain a fresh one atomically without releasing the lock.
        """
        # Check cached token
        if self._token_info and self._token_info.is_valid():
            return self._token_info.access_token

        # Load from file
        token_info = await self._auth_provider.load_token()
        if token_info and token_info.is_valid():
            self._token_info = token_info
            return token_info.access_token

        # Need to authenticate
        logger.info("No valid access token found, starting flow...")
        token_info = await self._auth_provider.authenticate()
        self._token_info = token_info
        return token_info.access_token

    def _build_auth_header(self, access_token: str) -> str:
        """Build Authorization header value (Shoonya uses Bearer token)."""
        return f"Bearer {access_token}"

    def _build_request_body(
        self,
        json_payload: dict[str, Any] | None = None,
    ) -> str:
        """Build Shoonya request body as jData=<JSON> string.

        Shoonya APIs use Content-Type: text/plain with a single jData field
        carrying the JSON-encoded payload.
        """
        import json

        if json_payload is None:
            json_payload = {}
        return f"jData={json.dumps(json_payload)}"

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

        Shoonya request format:
        - Content-Type: text/plain
        - Body: jData=<JSON payload>
        - Authorization: Bearer <AccessToken>

        Shoonya response format:
        - {"stat": "Ok", ...} for success
        - {"stat": "Not_Ok", "emsg": "..."} for application-level errors
        """
        access_token = await self._get_valid_token()
        request_headers = {
            "Authorization": self._build_auth_header(access_token),
            "Content-Type": "text/plain",
        }
        if headers:
            request_headers.update(headers)

        body = self._build_request_body(json)

        try:
            response = await self._client.request(
                method=method,
                url=path,
                content=body,
                params=params,
                headers=request_headers,
            )
        except httpx.RequestError as e:
            logger.error("Request failed: %s", e)
            raise ShoonyaNetworkError(f"Request failed: {e}", original_error=e) from e

        # Handle 403 - token expired, retry once with fresh token
        if response.status_code == 403:
            logger.warning("Received 403, access may be expired, retrying with fresh token")
            async with self._token_lock:
                self._token_info = None  # Force re-auth
                # Remove the stale token file so a fresh token is obtained
                # (Shoonya tokens never auto-expire, so is_valid() would
                # otherwise reload the same expired token from disk).
                try:
                    self.token_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning(
                        "Failed to delete stale token file: %s", self.token_path
                    )
                access_token = await self._get_valid_token_locked()
            retry_headers = {
                "Authorization": self._build_auth_header(access_token),
                "Content-Type": "text/plain",
            }
            if headers:
                retry_headers.update(headers)

            try:
                response = await self._client.request(
                    method=method,
                    url=path,
                    content=body,
                    params=params,
                    headers=retry_headers,
                )
            except httpx.RequestError as e:
                logger.error("Retry request failed: %s", e)
                raise ShoonyaNetworkError(f"Retry request failed: {e}", original_error=e) from e

        # Handle Shoonya application-level errors via stat/emsg.
        # If the token is expired per the application-level error (e.g. HTTP 200
        # with stat: Not_Ok and "session expired"/"invalid session" emsg),
        # invalidate the cached token and retry once with a fresh token.
        try:
            self._handle_error_response(response)
        except ShoonyaTokenExpiredError:
            logger.warning(
                "Token expired per application-level error, retrying with fresh token"
            )
            async with self._token_lock:
                self._token_info = None  # Force re-auth
                # Remove the stale token file so a fresh token is obtained
                # (Shoonya tokens never auto-expire, so is_valid() would
                # otherwise reload the same expired token from disk).
                try:
                    self.token_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning(
                        "Failed to delete stale token file: %s", self.token_path
                    )
            access_token = await self._get_valid_token()
            retry_headers = {
                "Authorization": self._build_auth_header(access_token),
                "Content-Type": "text/plain",
            }
            if headers:
                retry_headers.update(headers)

            try:
                response = await self._client.request(
                    method=method,
                    url=path,
                    content=body,
                    params=params,
                    headers=retry_headers,
                )
            except httpx.RequestError as e:
                logger.error("Retry request failed: %s", e)
                raise ShoonyaNetworkError(
                    f"Retry request failed: {e}", original_error=e
                ) from e

            # Validate the retried response (no further retries on token expiry)
            self._handle_error_response(response)

        return response

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Handle error responses from Shoonya API.

        Shoonya does not use HTTP status codes for application-level failures.
        A request can return HTTP 200 with stat: Not_Ok. Always check the
        stat field first.
        """
        # Check HTTP-level errors first
        if response.status_code == 400:
            raise ShoonyaInputError(f"Bad request: {response.text}")
        elif response.status_code == 403:
            raise ShoonyaTokenExpiredError("Access token expired or invalid")
        elif response.status_code == 404:
            raise ShoonyaNotFoundError(f"Resource not found: {response.text}")
        elif response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise ShoonyaRateLimitError(
                "Rate limit exceeded",
                retry_after=float(retry_after) if retry_after else None,
            )
        elif 500 <= response.status_code < 600:
            raise ShoonyaServerError(
                f"Server error: {response.text}", status_code=response.status_code
            )

        # Check Shoonya application-level stat field
        try:
            data = response.json()
        except (ValueError, TypeError):
            # Non-JSON response — treat as error if not empty
            if response.text.strip():
                raise ShoonyaDataError(f"Invalid response: {response.text}")
            return

        # TPSeries and EODChartData return a flat list on success (no stat field).
        # Only dict responses carry the stat/emsg application-level error contract.
        # Any other non-dict type (e.g., a bare string) is malformed and an error.
        if isinstance(data, list):
            return
        if not isinstance(data, dict):
            raise ShoonyaDataError(f"Invalid response: {response.text}")

        stat = data.get("stat")
        if stat == "Not_Ok":
            emsg = data.get("emsg", "Unknown error")
            # "no data" is a valid business condition (empty result), not an error.
            # Let the response pass through so the client can return an empty list.
            if "no data" in str(emsg).lower():
                return
            self._map_shoonya_error(emsg)
        elif stat != "Ok" and stat is not None:
            # Unknown stat value — treat as error
            raise ShoonyaDataError(f"Unexpected stat value: {stat}")

    def _map_shoonya_error(self, emsg: str) -> None:
        """Map Shoonya emsg string to the appropriate exception.

        Matches on substring since wording can vary slightly by cause.
        """
        emsg_lower = emsg.lower()

        if "rate_limited" in emsg_lower:
            raise ShoonyaRateLimitError(emsg)
        elif "invalid session" in emsg_lower or "session expired" in emsg_lower:
            raise ShoonyaTokenExpiredError(emsg)
        elif "invalid input" in emsg_lower:
            raise ShoonyaInputError(emsg)
        elif "not found" in emsg_lower:
            raise ShoonyaNotFoundError(emsg)
        elif "insufficient" in emsg_lower and "margin" in emsg_lower:
            raise ShoonyaMarginError(emsg)
        elif "insufficient" in emsg_lower and "holding" in emsg_lower:
            raise ShoonyaHoldingError(emsg)
        elif "server timeout" in emsg_lower:
            raise ShoonyaServerError(emsg)
        else:
            raise ShoonyaError(emsg)

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
        """Make a POST request with jData body."""
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
