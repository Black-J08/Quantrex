"""Zerodha authentication provider - handles login flow and token exchange."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime

import httpx

from quantrex.core.broker.zerodha.auth.callback_server import (
    CallbackServer,
    open_browser,
)
from quantrex.core.broker.zerodha.auth.token_store import TokenInfo, TokenStore
from quantrex.core.broker.zerodha.exceptions.exceptions import (
    ZerodhaAuthError,
    ZerodhaNetworkError,
)

logger = logging.getLogger(__name__)

LOGIN_URL = "https://kite.zerodha.com/connect/login?v=3&api_key={api_key}&redirect_params=redirect_url%3D{callback_url}"
TOKEN_URL = "https://api.kite.trade/session/token"


@dataclass(slots=True)
class AuthResult:
    """Result of authentication."""

    access_token: str
    user_id: str
    expires_at: datetime


class ZerodhaAuthProvider:
    """Handles Zerodha authentication flow.

    Flow:
    1. Check token store for valid token
    2. If missing/expired: start callback server, open browser to login URL
    3. User logs in → Zerodha redirects to callback URL with request_token
    4. Callback server captures request_token
    5. Exchange request_token + checksum for access_token
    6. Save token to store
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        token_path: str,
        callback_host: str = "127.0.0.1",
        callback_port: int = 8765,
        callback_timeout: float = 120.0,
    ):
        """Initialize auth provider.

        Args:
            api_key: Zerodha API key
            api_secret: Zerodha API secret
            token_path: Path to token file
            callback_host: Host for OAuth callback server
            callback_port: Port for OAuth callback server
            callback_timeout: Timeout for OAuth callback in seconds
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.token_store = TokenStore(token_path)
        self.callback_host = callback_host
        self.callback_port = callback_port
        self.callback_timeout = callback_timeout

    def _compute_checksum(self, request_token: str) -> str:
        """Compute SHA-256 checksum for token exchange.

        Checksum = SHA256(api_key + request_token + api_secret)
        """
        data = f"{self.api_key}{request_token}{self.api_secret}"
        return hashlib.sha256(data.encode()).hexdigest()

    def _build_login_url(self, callback_url: str) -> str:
        """Build Zerodha login URL."""
        return LOGIN_URL.format(api_key=self.api_key, callback_url=callback_url)

    async def load_token(self) -> TokenInfo | None:
        """Load token from store if valid."""
        return self.token_store.load()

    async def authenticate(self) -> TokenInfo:
        """Perform full authentication flow.

        Returns:
            TokenInfo with access_token, user_id, expires_at

        Raises:
            ZerodhaAuthError: If authentication fails
        """
        # Try loading existing token first
        token_info = await self.load_token()
        if token_info and token_info.is_valid():
            logger.info("Using existing valid token")
            return token_info

        # Need to authenticate
        logger.info("Starting authentication flow...")

        async with CallbackServer(port=self.callback_port, host=self.callback_host) as callback_server:
            # Build login URL with our callback
            callback_url = callback_server.get_callback_url()
            login_url = self._build_login_url(callback_url)

            # Open browser for user to log in
            await open_browser(login_url)

            # Wait for callback
            result = await callback_server.wait_for_callback(timeout=self.callback_timeout)

            if result.error:
                raise ZerodhaAuthError(f"Authentication failed: {result.error}")

            if not result.request_token:
                raise ZerodhaAuthError("No request_token received")

            # Exchange request_token for access_token
            token_info = await self._exchange_token(result.request_token)

            # Save token
            self.token_store.save(token_info)

            logger.info("Authentication successful for user: %s", token_info.user_id)
            return token_info

    async def _exchange_token(self, request_token: str) -> TokenInfo:
        """Exchange request_token for access_token via Zerodha API.

        Uses httpx directly to avoid circular import with ZerodhaSession.

        Args:
            request_token: One-time token from OAuth callback

        Returns:
            TokenInfo with access_token and user details
        """
        checksum = self._compute_checksum(request_token)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    TOKEN_URL,
                    headers={"X-Kite-Version": "3"},
                    data={
                        "api_key": self.api_key,
                        "request_token": request_token,
                        "checksum": checksum,
                    },
                )
            except httpx.RequestError as e:
                logger.error("Token exchange failed: %s", e)
                raise ZerodhaNetworkError(f"Token exchange failed: {e}", original_error=e) from e

        data = response.json()

        if data.get("status") != "success":
            raise ZerodhaAuthError(f"Token exchange failed: {data.get('message', 'Unknown error')}")

        token_data = data["data"]
        access_token = token_data["access_token"]
        user_id = token_data["user_id"]

        # Compute expiry (6 AM next day)
        expires_at = self.token_store.compute_expiry()

        return TokenInfo(
            access_token=access_token,
            user_id=user_id,
            expires_at=expires_at,
            api_key=self.api_key,
        )
