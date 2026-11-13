"""Shoonya authentication provider - handles login flow and token exchange."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime

import httpx

from quantrex.core.broker.shoonya.auth.callback_server import (
    CallbackServer,
    open_browser,
)
from quantrex.core.broker.shoonya.auth.token_store import TokenInfo, TokenStore
from quantrex.core.broker.shoonya.exceptions.exceptions import (
    ShoonyaAuthError,
    ShoonyaNetworkError,
)

logger = logging.getLogger(__name__)

# Constants
AUTHORIZE_URL = "https://api.shoonya.com/OAuthlogin/authorize/oauth?client_id={client_id}"
TOKEN_URL = "https://api.shoonya.com/NorenWClientAPI/GenAcsTok"


@dataclass(slots=True)
class AuthResult:
    """Result of authentication."""

    access_token: str
    user_id: str
    expires_at: datetime


class ShoonyaAuthProvider:
    """Handles Shoonya authentication flow.

    Flow:
    1. Check token store for valid token
    2. If missing/expired: start callback server, open browser to login URL
    3. User logs in → Shoonya redirects to callback URL with authorization code
    4. Callback server captures authorization code
    5. Exchange code + checksum for access token via GenAcsTok
    6. Save token to store
    """

    def __init__(
        self,
        client_id: str,
        secret_key: str,
        token_path: str,
        oauth_client_id: str | None = None,
        callback_host: str = "127.0.0.1",
        callback_port: int = 8765,
        callback_timeout: float = 120.0,
    ):
        """Initialize auth provider.

        Args:
            client_id: Shoonya client ID (used for API calls as uid)
            secret_key: Shoonya secret key
            token_path: Path to token file
            oauth_client_id: OAuth client ID for the authorize URL.
                Falls back to client_id if not provided.
            callback_host: Host for OAuth callback server
            callback_port: Port for OAuth callback server
            callback_timeout: Timeout for OAuth callback in seconds
        """
        self.client_id = client_id
        self.oauth_client_id = oauth_client_id or client_id
        self.secret_key = secret_key
        self.token_store = TokenStore(token_path)
        self.callback_host = callback_host
        self.callback_port = callback_port
        self.callback_timeout = callback_timeout

    def _compute_checksum(self, auth_code: str) -> str:
        """Compute SHA-256 checksum for token exchange.

        Checksum = SHA256(client_id + secret_key + auth_code)
        """
        data = f"{self.client_id}{self.secret_key}{auth_code}"
        return hashlib.sha256(data.encode()).hexdigest()

    def _build_login_url(self, callback_url: str) -> str:
        """Build Shoonya OAuth authorize URL.

        Uses the OAuth client ID (which may have a dynamically assigned
        prefix from Shoonya's backend) for the authorize endpoint.
        Falls back to the regular client_id if no OAuth-specific ID is set.

        Includes the redirect_uri so Shoonya knows where to redirect back
        with the authorization code after the user logs in.
        """
        from urllib.parse import quote

        return (
            f"{AUTHORIZE_URL.format(client_id=self.oauth_client_id)}"
            f"&redirect_uri={quote(callback_url, safe='')}"
        )

    async def load_token(self) -> TokenInfo | None:
        """Load token from store if valid."""
        return self.token_store.load()

    async def authenticate(self) -> TokenInfo:
        """Perform full authentication flow.

        Returns:
            TokenInfo with access_token, user_id, expires_at

        Raises:
            ShoonyaAuthError: If authentication fails
        """
        # Try loading existing token first
        token_info = await self.load_token()
        if token_info and token_info.is_valid():
            logger.info("Using existing token")
            return token_info

        # Need to authenticate
        logger.info("Starting authentication flow...")

        async with CallbackServer(
            port=self.callback_port, host=self.callback_host
        ) as callback_server:
            # Build login URL with our callback
            callback_url = callback_server.get_callback_url()
            login_url = self._build_login_url(callback_url)

            # Open browser for user to log in
            await open_browser(login_url)

            # Wait for callback
            result = await callback_server.wait_for_callback(
                timeout=self.callback_timeout
            )

            if result.error:
                raise ShoonyaAuthError(f"Authentication failed: {result.error}")

            if not result.code:
                raise ShoonyaAuthError("No authorization code received")

            # Exchange authorization code for access token
            token_info = await self._exchange_token(result.code)

            # Save token
            self.token_store.save(token_info)

            logger.info("Authentication complete")
            return token_info

    async def _exchange_token(self, auth_code: str) -> TokenInfo:
        """Exchange authorization code for access_token via Shoonya GenAcsTok API.

        Args:
            auth_code: One-time authorization code from OAuth callback

        Returns:
            TokenInfo with access_token and user details
        """
        checksum = self._compute_checksum(auth_code)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    TOKEN_URL,
                    headers={"Content-Type": "text/plain"},
                    content=f'jData={{"code":"{auth_code}","checksum":"{checksum}"}}',
                )
            except httpx.RequestError as e:
                logger.error("Token exchange failed: %s", e)
                raise ShoonyaNetworkError(f"Token exchange failed: {e}", original_error=e) from e

        data = response.json()

        if data.get("stat") != "Ok":
            raise ShoonyaAuthError(
                f"Token exchange failed: {data.get('emsg', 'Unknown error')}"
            )

        access_token = data["susertoken"]
        user_id = data.get("uid", data.get("actid", ""))

        # Shoonya tokens have no automatic expiry; use far-future sentinel
        expires_at = self.token_store.compute_expiry()

        return TokenInfo(
            access_token=access_token,
            user_id=user_id,
            expires_at=expires_at,
            api_key=self.client_id,
        )
