"""Tests for Zerodha authentication."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantrex.core.broker.zerodha.auth.callback_server import (
    CallbackResult,
    CallbackServer,
)
from quantrex.core.broker.zerodha.auth.provider import ZerodhaAuthProvider
from quantrex.core.broker.zerodha.auth.token_store import TokenInfo, TokenStore
from quantrex.core.broker.zerodha.exceptions.exceptions import (
    ZerodhaAuthError,
    ZerodhaNetworkError,
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
        """Test computing token expiry (6 AM next day)."""
        store = TokenStore("/tmp/token.json")
        expiry = store.compute_expiry()

        # Should be at 6 AM UTC
        assert expiry.hour == 6
        assert expiry.minute == 0
        assert expiry.second == 0
        assert expiry.microsecond == 0
        assert expiry.tzinfo == UTC

        # Should be tomorrow
        now = datetime.now(UTC)
        assert expiry.date() == (now + timedelta(days=1)).date()


class TestTokenInfo:
    """Tests for TokenInfo."""

    def test_is_expired_false(self) -> None:
        """Test is_expired returns False for future expiry."""
        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="test_token",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        )
        assert not token_info.is_expired()

    def test_is_expired_true(self) -> None:
        """Test is_expired returns True for past expiry."""
        past = datetime.now(UTC) - timedelta(hours=1)
        token_info = TokenInfo(
            access_token="test_token",
            user_id="user123",
            expires_at=past,
            api_key="test_key",
        )
        assert token_info.is_expired()

    def test_is_valid_true(self) -> None:
        """Test is_valid returns True for valid token."""
        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="test_token",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        )
        assert token_info.is_valid()

    def test_is_valid_false_empty_token(self) -> None:
        """Test is_valid returns False for empty token."""
        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        )
        assert not token_info.is_valid()

    def test_is_valid_false_expired(self) -> None:
        """Test is_valid returns False for expired token."""
        past = datetime.now(UTC) - timedelta(hours=1)
        token_info = TokenInfo(
            access_token="test_token",
            user_id="user123",
            expires_at=past,
            api_key="test_key",
        )
        assert not token_info.is_valid()

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

        await server.stop()


class TestZerodhaAuthProvider:
    """Tests for ZerodhaAuthProvider."""

    def test_compute_checksum(self) -> None:
        """Test checksum computation."""
        provider = ZerodhaAuthProvider(
            api_key="test_key",
            api_secret="test_secret",
            token_path="/tmp/token.json",
        )

        checksum = provider._compute_checksum("request_token_123")
        # SHA256 of "test_keyrequest_token_123test_secret"
        import hashlib
        expected = hashlib.sha256(b"test_keyrequest_token_123test_secret").hexdigest()
        assert checksum == expected

    def test_build_login_url(self) -> None:
        """Test building login URL."""
        provider = ZerodhaAuthProvider(
            api_key="test_key",
            api_secret="test_secret",
            token_path="/tmp/token.json",
        )

        url = provider._build_login_url("http://localhost:8765/callback")
        assert "api_key=test_key" in url
        assert "redirect_url" in url

    @pytest.mark.asyncio
    async def test_load_token(self, tmp_path) -> None:
        """Test loading token from store."""
        token_file = tmp_path / "token.json"
        provider = ZerodhaAuthProvider(
            api_key="test_key",
            api_secret="test_secret",
            token_path=str(token_file),
        )

        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="stored_token",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        )
        provider.token_store.save(token_info)

        loaded = await provider.load_token()
        assert loaded is not None
        assert loaded.access_token == "stored_token"

    @pytest.mark.asyncio
    async def test_authenticate_success(self, tmp_path) -> None:
        """Test successful authentication flow."""
        token_file = tmp_path / "token.json"
        provider = ZerodhaAuthProvider(
            api_key="test_key",
            api_secret="test_secret",
            token_path=str(token_file),
            callback_port=8768,
        )

        # Mock callback server to return request_token
        with patch("quantrex.core.broker.zerodha.auth.provider.CallbackServer") as mock_server_class:
            mock_server = AsyncMock()
            mock_server.__aenter__.return_value = mock_server
            mock_server.wait_for_callback.return_value = CallbackResult(request_token="req_token_123")
            mock_server.get_callback_url.return_value = "http://localhost:8768/callback"
            mock_server_class.return_value = mock_server

            # Mock httpx client for token exchange
            with patch("quantrex.core.broker.zerodha.auth.provider.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_response = MagicMock()
                mock_response.json.return_value = {
                    "status": "success",
                    "data": {
                        "access_token": "access_token_123",
                        "user_id": "user123",
                    },
                }
                mock_client.post.return_value = mock_response
                mock_client_class.return_value = mock_client

                token_info = await provider.authenticate()

                assert token_info.access_token == "access_token_123"
                assert token_info.user_id == "user123"
                assert token_info.api_key == "test_key"

    @pytest.mark.asyncio
    async def test_authenticate_callback_error(self, tmp_path) -> None:
        """Test authentication with callback error."""
        token_file = tmp_path / "token.json"
        provider = ZerodhaAuthProvider(
            api_key="test_key",
            api_secret="test_secret",
            token_path=str(token_file),
            callback_port=8769,
        )

        with patch("quantrex.core.broker.zerodha.auth.provider.CallbackServer") as mock_server_class:
            mock_server = AsyncMock()
            mock_server.__aenter__.return_value = mock_server
            mock_server.wait_for_callback.return_value = CallbackResult(error="access_denied")
            mock_server_class.return_value = mock_server

            with pytest.raises(ZerodhaAuthError, match="Authentication failed: access_denied"):
                await provider.authenticate()

    @pytest.mark.asyncio
    async def test_authenticate_no_request_token(self, tmp_path) -> None:
        """Test authentication with no request_token."""
        token_file = tmp_path / "token.json"
        provider = ZerodhaAuthProvider(
            api_key="test_key",
            api_secret="test_secret",
            token_path=str(token_file),
            callback_port=8770,
        )

        with patch("quantrex.core.broker.zerodha.auth.provider.CallbackServer") as mock_server_class:
            mock_server = AsyncMock()
            mock_server.__aenter__.return_value = mock_server
            mock_server.wait_for_callback.return_value = CallbackResult(request_token=None, error=None)
            mock_server_class.return_value = mock_server

            with pytest.raises(ZerodhaAuthError, match="No request_token received"):
                await provider.authenticate()

    @pytest.mark.asyncio
    async def test_authenticate_token_exchange_failure(self, tmp_path) -> None:
        """Test authentication with token exchange failure."""
        token_file = tmp_path / "token.json"
        provider = ZerodhaAuthProvider(
            api_key="test_key",
            api_secret="test_secret",
            token_path=str(token_file),
            callback_port=8771,
        )

        with patch("quantrex.core.broker.zerodha.auth.provider.CallbackServer") as mock_server_class:
            mock_server = AsyncMock()
            mock_server.__aenter__.return_value = mock_server
            mock_server.wait_for_callback.return_value = CallbackResult(request_token="req_token_123")
            mock_server.get_callback_url.return_value = "http://localhost:8771/callback"
            mock_server_class.return_value = mock_server

            with patch("quantrex.core.broker.zerodha.auth.provider.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_response = MagicMock()
                mock_response.json.return_value = {
                    "status": "error",
                    "message": "Invalid request_token",
                }
                mock_client.post.return_value = mock_response
                mock_client_class.return_value = mock_client

                with pytest.raises(ZerodhaAuthError, match="Token exchange failed"):
                    await provider.authenticate()

    @pytest.mark.asyncio
    async def test_authenticate_network_error(self, tmp_path) -> None:
        """Test authentication with network error during token exchange."""
        token_file = tmp_path / "token.json"
        provider = ZerodhaAuthProvider(
            api_key="test_key",
            api_secret="test_secret",
            token_path=str(token_file),
            callback_port=8772,
        )

        with patch("quantrex.core.broker.zerodha.auth.provider.CallbackServer") as mock_server_class:
            mock_server = AsyncMock()
            mock_server.__aenter__.return_value = mock_server
            mock_server.wait_for_callback.return_value = CallbackResult(request_token="req_token_123")
            mock_server.get_callback_url.return_value = "http://localhost:8772/callback"
            mock_server_class.return_value = mock_server

            with patch("quantrex.core.broker.zerodha.auth.provider.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                import httpx
                mock_client.post.side_effect = httpx.RequestError("Connection failed")
                mock_client_class.return_value = mock_client

                with pytest.raises(ZerodhaNetworkError, match="Token exchange failed"):
                    await provider.authenticate()
