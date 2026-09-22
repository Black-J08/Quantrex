"""Authentication helpers for Zerodha Kite Connect login flow."""

import hashlib
import webbrowser
from pathlib import Path
from typing import Any

from quantrex_core.logging import get_logger

from .callback_server import CallbackServer
from .config import ZerodhaProviderConfig
from .exceptions import ZerodhaAuthenticationError

logger = get_logger(__name__)


class ZerodhaAuth:
    """Handles Zerodha Kite Connect authentication flow.

    The login flow:
    1. User navigates to login URL with api_key
    2. After successful login, user is redirected with request_token
    3. Exchange request_token + checksum for access_token
    4. Save access_token for future use
    """

    LOGIN_URL_TEMPLATE = "https://kite.zerodha.com/connect/login?v=3&api_key={api_key}"

    def __init__(self, config: ZerodhaProviderConfig) -> None:
        """Initialize auth helper.

        Args:
            config: Provider configuration with api_key, api_secret, token_file.
        """
        self._config = config
        self._callback_server: CallbackServer | None = None

    def get_login_url(self) -> str:
        """Get the login URL for the user to authenticate.

        Returns:
            Login URL string with redirect URL configured.
        """
        # Per Kite Connect docs, the redirect URL is registered in the developer console.
        # We don't pass redirect_params (state) per user decision to keep it simple.
        return self.LOGIN_URL_TEMPLATE.format(api_key=self._config.api_key)

    def _start_callback_server(self) -> str:
        """Start the local callback server.

        Returns:
            The callback URL.
        """
        self._callback_server = CallbackServer(
            host=self._config.callback_host,
            port=self._config.callback_port,
            path=self._config.callback_path,
            timeout=self._config.callback_timeout,
        )
        return self._callback_server.start()

    def _stop_callback_server(self) -> None:
        """Stop the local callback server if running."""
        if self._callback_server:
            self._callback_server.stop()
            self._callback_server = None

    def open_login_url(self) -> bool:
        """Attempt to open the login URL in the default browser.

        Returns:
            True if browser was opened successfully.
        """
        url = self.get_login_url()
        try:
            webbrowser.open(url)
            logger.info("Opened login URL in browser: %s", url)
            return True
        except Exception as e:
            logger.warning("Could not open browser automatically: %s", e)
            return False

    def calculate_checksum(self, request_token: str) -> str:
        """Calculate SHA256 checksum for token exchange.

        Checksum = SHA256(api_key + request_token + api_secret)

        Args:
            request_token: Request token from login redirect.

        Returns:
            Hex-encoded SHA256 checksum.
        """
        return hashlib.sha256(
            f"{self._config.api_key}{request_token}{self._config.api_secret}".encode()
        ).hexdigest()

    def exchange_request_token(self, request_token: str, client: Any) -> str:
        """Exchange request_token for access_token.

        Args:
            request_token: Request token from login redirect.
            client: ZerodhaAPIClient instance to make the request.

        Returns:
            Access token string.

        Raises:
            ZerodhaAuthenticationError: If exchange fails.
        """
        checksum = self.calculate_checksum(request_token)

        payload = {
            "api_key": self._config.api_key,
            "request_token": request_token,
            "checksum": checksum,
        }

        logger.debug("Exchanging request_token for access_token")

        try:
            # Token exchange endpoint expects form data, not JSON
            data = client._request("POST", "/session/token", data=payload)
            session_data = data.get("data", {})
            access_token = session_data.get("access_token")

            if not access_token:
                raise ZerodhaAuthenticationError("No access_token in session response")

            return access_token

        except Exception as e:
            raise ZerodhaAuthenticationError(f"Failed to exchange request_token: {e}") from e

    def save_access_token(self, access_token: str) -> None:
        """Save access token to token file.

        Args:
            access_token: Access token to save.
        """
        self._config.token_file.write_text(access_token)
        logger.info("Saved access token to %s", self._config.token_file)

    def load_access_token(self) -> str | None:
        """Load access token from token file.

        Returns:
            Access token string or None if not found.
        """
        if self._config.token_file.exists():
            try:
                token = self._config.token_file.read_text().strip()
                if token:
                    logger.debug("Loaded access token from %s", self._config.token_file)
                    return token
            except Exception as e:
                logger.warning("Failed to read token file %s: %s", self._config.token_file, e)
        return None

    def validate_token(self, client: Any) -> bool:
        """Validate current access token by calling profile API.

        Args:
            client: ZerodhaAPIClient instance.

        Returns:
            True if token is valid, False otherwise.
        """
        try:
            client.get_profile()
            return True
        except ZerodhaAuthenticationError:
            return False
        except Exception as e:
            logger.warning("Token validation failed with unexpected error: %s", e)
            return False

    def run_login_flow(self, client: Any) -> str:
        """Run the complete login flow with automated callback server.

        Attempts to start a local callback server to receive the request_token
        automatically. Falls back to manual input if server cannot start.

        Args:
            client: ZerodhaAPIClient instance.

        Returns:
            New access token.

        Raises:
            ZerodhaAuthenticationError: If login flow fails or is cancelled.
        """
        login_url = self.get_login_url()

        print("\n" + "=" * 70)
        print("ZERODHA AUTHENTICATION REQUIRED")
        print("=" * 70)
        print(f"Please open the following URL in your browser to log in:")
        print(f"\n  {login_url}\n")

        # Try automated callback server first
        request_token = None
        try:
            callback_url = self._start_callback_server()
            print(f"Waiting for callback at {callback_url} ...")
            print("=" * 70)

            # Try to open browser automatically
            self.open_login_url()

            # Wait for callback with request_token
            request_token = self._callback_server.wait_for_token()

        except (OSError, RuntimeError, TimeoutError) as e:
            # Server failed to start or timed out - fall back to manual input
            logger.warning("Callback server unavailable (%s), falling back to manual input", e)
            self._stop_callback_server()

            print("Automated callback unavailable. Falling back to manual entry.")
            print("After logging in, you will be redirected to a URL containing a")
            print("'request_token' parameter. Copy that request_token and paste it below.")
            print("=" * 70)

            # Try to open browser automatically
            self.open_login_url()

            # Wait for user to provide request_token
            request_token = input("\nEnter request_token from redirect URL: ").strip()

        if not request_token:
            raise ZerodhaAuthenticationError("No request_token provided. Login flow cancelled.")

        # Exchange request_token for access_token
        access_token = self.exchange_request_token(request_token, client)

        # Save token to file
        self.save_access_token(access_token)

        print("\nAuthentication successful! Access token saved.")
        print("=" * 70 + "\n")

        return access_token

    def ensure_valid_token(self, client: Any) -> str:
        """Ensure we have a valid access token, triggering login flow if needed.

        Args:
            client: ZerodhaAPIClient instance.

        Returns:
            Valid access token.

        Raises:
            ZerodhaAuthenticationError: If unable to obtain valid token.
        """
        # Try to load existing token
        token = self.load_access_token()
        if token:
            client.update_access_token(token)
            if self.validate_token(client):
                logger.debug("Existing access token is valid")
                return token
            logger.info("Existing access token is invalid/expired")

        # Trigger login flow
        return self.run_login_flow(client)