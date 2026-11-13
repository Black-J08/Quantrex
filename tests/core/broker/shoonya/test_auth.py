"""Tests for Shoonya authentication."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantrex.core.broker.shoonya.auth.callback_server import (
    CallbackServer,
)
from quantrex.core.broker.shoonya.auth.provider import ShoonyaAuthProvider
from quantrex.core.broker.shoonya.auth.token_store import TokenInfo, TokenStore
from quantrex.core.broker.shoonya.exceptions.exceptions import (
    ShoonyaAuthError,
    ShoonyaNetworkError,
)


class TestTokenStore:
    """Tests for TokenStore."""

    def test_save_and_load_token(self, tmp_path) -> None:
        """Test saving and loading token."""
        token_file = tmp_path / "token.json"
        store = TokenStore(token_file)

        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="test_token",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        )

        store.save(token_info)
        loaded = store.load()

        assert loaded is not None
        assert loaded.access_token == "test_token"
        assert loaded.user_id == "user123"
        assert loaded.api_key == "test_key"

    def test_load_nonexistent_token(self, tmp_path) -> None:
        """Test loading token from nonexistent file."""
        token_file = tmp_path / "nonexistent.json"
        store = TokenStore(token_file)

        loaded = store.load()
        assert loaded is None

    def test_load_invalid_token(self, tmp_path) -> None:
        """Test loading invalid token file."""
        token_file = tmp_path / "invalid.json"
        token_file.write_text("invalid json")
        store = TokenStore(token_file)

        loaded = store.load()
        assert loaded is None

    def test_delete_token(self, tmp_path) -> None:
        """Test deleting token file."""
        token_file = tmp_path / "token.json"
        store = TokenStore(token_file)

        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="test_token",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        )
        store.save(token_info)
        assert token_file.exists()

        store.delete()
        assert not token_file.exists()

    def test_compute_expiry(self) -> None:
        """Test computing token expiry (far-future for Shoonya)."""
        store = TokenStore("/tmp/token.json")
        expiry = store.compute_expiry()

        # Should be 1 year from now
        now = datetime.now(UTC)
        assert expiry.year == now.year + 1
        assert expiry.tzinfo == UTC

    def test_token_info_is_expired_false(self) -> None:
        """Test Shoonya is_expired always returns False."""
        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="test_token",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        )
        assert not token_info.is_expired()

    def test_token_info_is_valid_true(self) -> None:
        """Test Shoonya is_valid returns True for non-empty token."""
        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="test_token",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        )
        assert token_info.is_valid()

    def test_token_info_is_valid_false_empty(self) -> None:
        """Test Shoonya is_valid returns False for empty token."""
        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        )
        assert not token_info.is_valid()


class TestTokenInfo:
    """Tests for TokenInfo serialization."""

    def test_to_dict_and_from_dict(self) -> None:
        """Test serialization round-trip."""
        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="test_token",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        )

        data = token_info.to_dict()
        loaded = TokenInfo.from_dict(data)

        assert loaded.access_token == token_info.access_token
        assert loaded.user_id == token_info.user_id
        assert loaded.expires_at == token_info.expires_at
        assert loaded.api_key == token_info.api_key


class TestCallbackServer:
    """Tests for CallbackServer."""

    @pytest.mark.asyncio
    async def test_callback_server_start_stop(self) -> None:
        """Test starting and stopping callback server."""
        server = CallbackServer(port=8766)
        await server.start()
        assert server._runner is not None
        assert server._site is not None
        await server.stop()

    @pytest.mark.asyncio
    async def test_get_callback_url(self) -> None:
        """Test getting callback URL."""
        server = CallbackServer(port=8766)
        url = server.get_callback_url()
        assert url == "http://127.0.0.1:8766/callback"

    @pytest.mark.asyncio
    async def test_wait_for_callback_timeout(self) -> None:
        """Test callback timeout."""
        server = CallbackServer(port=8767)
        await server.start()

        result = await server.wait_for_callback(timeout=0.1)

        assert result.error == "Callback timeout"
        assert result.code is None


class TestShoonyaAuthProvider:
    """Tests for ShoonyaAuthProvider."""

    def test_compute_checksum(self) -> None:
        """Test SHA-256 checksum computation."""
        provider = ShoonyaAuthProvider(
            client_id="test_client",
            secret_key="test_secret",
            token_path="/tmp/token.json",
        )
        checksum = provider._compute_checksum("auth_code_123")

        import hashlib

        expected = hashlib.sha256(
            b"test_clienttest_secretauth_code_123"
        ).hexdigest()
        assert checksum == expected

    def test_build_login_url(self) -> None:
        """Test building authorize URL includes redirect_uri."""
        provider = ShoonyaAuthProvider(
            client_id="test_client",
            secret_key="test_secret",
            token_path="/tmp/token.json",
        )
        url = provider._build_login_url("http://localhost:8765/callback")
        assert url == (
            "https://api.shoonya.com/OAuthlogin/authorize/oauth"
            "?client_id=test_client"
            "&redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fcallback"
        )

    def test_build_login_url_with_oauth_client_id(self) -> None:
        """Test building authorize URL uses OAuth client ID when provided."""
        provider = ShoonyaAuthProvider(
            client_id="test_client",
            secret_key="test_secret",
            token_path="/tmp/token.json",
            oauth_client_id="PREFIX_test_client",
        )
        url = provider._build_login_url("http://localhost:8765/callback")
        assert url == (
            "https://api.shoonya.com/OAuthlogin/authorize/oauth"
            "?client_id=PREFIX_test_client"
            "&redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fcallback"
        )

    def test_build_login_url_oauth_client_id_falls_back_to_client_id(self) -> None:
        """Test authorize URL falls back to client_id when no OAuth client ID set."""
        provider = ShoonyaAuthProvider(
            client_id="test_client",
            secret_key="test_secret",
            token_path="/tmp/token.json",
        )
        assert provider.oauth_client_id == "test_client"
        url = provider._build_login_url("http://localhost:8765/callback")
        assert url == (
            "https://api.shoonya.com/OAuthlogin/authorize/oauth"
            "?client_id=test_client"
            "&redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fcallback"
        )

    def test_oauth_client_id_defaults_to_client_id(self) -> None:
        """Test oauth_client_id attribute defaults to client_id when not provided."""
        provider = ShoonyaAuthProvider(
            client_id="test_client",
            secret_key="test_secret",
            token_path="/tmp/token.json",
        )
        assert provider.oauth_client_id == "test_client"

    def test_oauth_client_id_is_stored_separately(self) -> None:
        """Test oauth_client_id is stored separately from client_id."""
        provider = ShoonyaAuthProvider(
            client_id="test_client",
            secret_key="test_secret",
            token_path="/tmp/token.json",
            oauth_client_id="PREFIX_test_client",
        )
        assert provider.client_id == "test_client"
        assert provider.oauth_client_id == "PREFIX_test_client"

    @pytest.mark.asyncio
    async def test_authenticate_with_valid_cached_token(self) -> None:
        """Test authenticate returns cached token without re-auth."""
        provider = ShoonyaAuthProvider(
            client_id="test_client",
            secret_key="test_secret",
            token_path="/tmp/token.json",
        )

        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="cached_token",
            user_id="user123",
            expires_at=future,
            api_key="test_client",
        )
        provider.token_store.save(token_info)

        result = await provider.authenticate()
        assert result.access_token == "cached_token"
        assert result.user_id == "user123"

    @pytest.mark.asyncio
    async def test_exchange_token_success(self) -> None:
        """Test successful token exchange via GenAcsTok."""
        provider = ShoonyaAuthProvider(
            client_id="test_client",
            secret_key="test_secret",
            token_path="/tmp/token.json",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "stat": "Ok",
            "susertoken": "access_token_123",
            "uid": "ABC1234",
            "actid": "ABC1234",
        }

        with patch.object(provider.token_store, "compute_expiry") as mock_expiry:
            mock_expiry.return_value = datetime.now(UTC) + timedelta(days=365)

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await provider._exchange_token("auth_code_123")

        assert result.access_token == "access_token_123"
        assert result.user_id == "ABC1234"

    @pytest.mark.asyncio
    async def test_exchange_token_failure(self) -> None:
        """Test token exchange failure raises ShoonyaAuthError."""
        provider = ShoonyaAuthProvider(
            client_id="test_client",
            secret_key="test_secret",
            token_path="/tmp/token.json",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "stat": "Not_Ok",
            "emsg": "Invalid checksum",
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(ShoonyaAuthError, match="Invalid checksum"):
                await provider._exchange_token("auth_code_123")

    @pytest.mark.asyncio
    async def test_exchange_token_network_error(self) -> None:
        """Test network error during token exchange raises ShoonyaNetworkError."""
        provider = ShoonyaAuthProvider(
            client_id="test_client",
            secret_key="test_secret",
            token_path="/tmp/token.json",
        )

        import httpx

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.RequestError("Connection failed"))
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(ShoonyaNetworkError):
                await provider._exchange_token("auth_code_123")
