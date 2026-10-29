"""Tests for ZerodhaSession."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantrex.core.broker.zerodha.auth.token_store import TokenInfo
from quantrex.core.broker.zerodha.exceptions.exceptions import (
    ZerodhaInputError,
    ZerodhaNetworkError,
    ZerodhaNotFoundError,
    ZerodhaRateLimitError,
    ZerodhaServerError,
)
from quantrex.core.broker.zerodha.session.session import ZerodhaSession
from quantrex.core.utility.rate_limiter import SlidingWindowRateLimiter


class TestZerodhaSession:
    """Tests for ZerodhaSession."""

    def test_create_session_with_env_vars(self, monkeypatch) -> None:
        """Test creating session with environment variables."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")
        monkeypatch.setenv("ZERODHA_REDIRECT_URL", "http://localhost:8765/callback")

        session = ZerodhaSession()
        assert session.api_key == "test_key"
        assert session.api_secret == "test_secret"
        assert session.callback_host == "localhost"
        assert session.callback_port == 8765
        assert session.callback_path == "/callback"

    def test_create_session_with_explicit_args(self) -> None:
        """Test creating session with explicit arguments."""
        session = ZerodhaSession(
            api_key="explicit_key",
            api_secret="explicit_secret",
            redirect_url="http://localhost:9999/auth/callback",
        )
        assert session.api_key == "explicit_key"
        assert session.api_secret == "explicit_secret"
        assert session.callback_host == "localhost"
        assert session.callback_port == 9999
        assert session.callback_path == "/auth/callback"

    def test_create_session_with_redirect_url_env(self, monkeypatch) -> None:
        """Test creating session with redirect URL from env."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")
        monkeypatch.setenv("ZERODHA_REDIRECT_URL", "http://localhost:9999/auth/callback")
        monkeypatch.setenv("ZERODHA_CALLBACK_TIMEOUT", "60.0")

        session = ZerodhaSession()
        assert session.callback_host == "localhost"
        assert session.callback_port == 9999
        assert session.callback_path == "/auth/callback"
        assert session.callback_timeout == 60.0

    def test_create_session_missing_credentials(self, monkeypatch) -> None:
        """Test creating session without credentials raises error."""
        monkeypatch.delenv("ZERODHA_API_KEY", raising=False)
        monkeypatch.delenv("ZERODHA_API_SECRET", raising=False)

        with pytest.raises(ValueError, match="API key and secret are required"):
            ZerodhaSession()

    def test_create_session_missing_redirect_url(self, monkeypatch) -> None:
        """Test creating session without redirect URL raises error."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")
        monkeypatch.delenv("ZERODHA_REDIRECT_URL", raising=False)

        with pytest.raises(ValueError, match="Redirect URL is required"):
            ZerodhaSession()

    @pytest.mark.asyncio
    async def test_get_valid_token_from_cache(self) -> None:
        """Test getting valid token from cache."""
        session = ZerodhaSession(
            api_key="test_key",
            api_secret="test_secret",
            redirect_url="http://localhost:8765/callback",
        )

        # Set a valid cached token
        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="cached_token",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        )
        session._token_info = token_info

        token = await session._get_valid_token()
        assert token == "cached_token"

    @pytest.mark.asyncio
    async def test_get_valid_token_expired_cache(self) -> None:
        """Test getting token when cached token is expired."""
        session = ZerodhaSession(
            api_key="test_key",
            api_secret="test_secret",
            redirect_url="http://localhost:8765/callback",
        )

        # Set an expired cached token
        past = datetime.now(UTC) - timedelta(hours=1)
        token_info = TokenInfo(
            access_token="expired_token",
            user_id="user123",
            expires_at=past,
            api_key="test_key",
        )
        session._token_info = token_info

        # Mock auth provider to return new token
        future = datetime.now(UTC) + timedelta(hours=1)
        new_token_info = TokenInfo(
            access_token="new_token",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        )
        session._auth_provider.load_token = AsyncMock(return_value=None)
        session._auth_provider.authenticate = AsyncMock(return_value=new_token_info)

        token = await session._get_valid_token()
        assert token == "new_token"
        session._auth_provider.authenticate.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_valid_token_from_file(self) -> None:
        """Test loading valid token from file."""
        session = ZerodhaSession(
            api_key="test_key",
            api_secret="test_secret",
            redirect_url="http://localhost:8765/callback",
        )

        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="file_token",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        )
        session._auth_provider.load_token = AsyncMock(return_value=token_info)

        token = await session._get_valid_token()
        assert token == "file_token"
        session._auth_provider.load_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_success(self) -> None:
        """Test successful request."""
        session = ZerodhaSession(
            api_key="test_key",
            api_secret="test_secret",
            redirect_url="http://localhost:8765/callback",
        )

        # Mock token
        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="valid_token",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        )
        session._token_info = token_info

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "data": {}}
        session._client.request = AsyncMock(return_value=mock_response)

        response = await session.get("/test/path")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_request_403_retry(self) -> None:
        """Test request retry on 403."""
        session = ZerodhaSession(
            api_key="test_key",
            api_secret="test_secret",
            redirect_url="http://localhost:8765/callback",
        )

        # Mock token
        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="valid_token",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        )
        session._token_info = token_info

        # Mock HTTP client - first 403, then success
        mock_response_403 = MagicMock()
        mock_response_403.status_code = 403

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"status": "success", "data": {}}

        session._client.request = AsyncMock(side_effect=[mock_response_403, mock_response_200])
        session._auth_provider.authenticate = AsyncMock(return_value=TokenInfo(
            access_token="new_token",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        ))

        response = await session.get("/test/path")
        assert response.status_code == 200
        assert session._client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_request_network_error(self) -> None:
        """Test network error handling."""
        import httpx
        session = ZerodhaSession(
            api_key="test_key",
            api_secret="test_secret",
            redirect_url="http://localhost:8765/callback",
        )

        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="valid_token",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        )
        session._token_info = token_info

        session._client.request = AsyncMock(side_effect=httpx.RequestError("Connection failed"))

        with pytest.raises(ZerodhaNetworkError):
            await session.get("/test/path")

    @pytest.mark.asyncio
    async def test_handle_error_responses(self) -> None:
        """Test error response handling."""
        session = ZerodhaSession(
            api_key="test_key",
            api_secret="test_secret",
            redirect_url="http://localhost:8765/callback",
        )

        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="valid_token",
            user_id="user123",
            expires_at=future,
            api_key="test_key",
        )
        session._token_info = token_info

        # Test 400
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        session._client.request = AsyncMock(return_value=mock_response)

        with pytest.raises(ZerodhaInputError):
            await session.get("/test/path")

        # Test 404
        mock_response.status_code = 404
        mock_response.text = "Not found"
        with pytest.raises(ZerodhaNotFoundError):
            await session.get("/test/path")

        # Test 429
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "5"}
        with pytest.raises(ZerodhaRateLimitError) as exc_info:
            await session.get("/test/path")
        assert exc_info.value.retry_after == 5.0

        # Test 500
        mock_response.status_code = 500
        mock_response.text = "Server error"
        with pytest.raises(ZerodhaServerError):
            await session.get("/test/path")

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        """Test async context manager."""
        session = ZerodhaSession(
            api_key="test_key",
            api_secret="test_secret",
            redirect_url="http://localhost:8765/callback",
        )
        session._client.aclose = AsyncMock()

        async with session as s:
            assert s is session

        session._client.aclose.assert_called_once()

    def test_historical_limiter_returns_shared_instance(self) -> None:
        """Test that historical_limiter returns the same instance on repeated access."""
        session = ZerodhaSession(
            api_key="test_key",
            api_secret="test_secret",
            redirect_url="http://localhost:8765/callback",
        )

        limiter1 = session.historical_limiter
        limiter2 = session.historical_limiter

        assert limiter1 is limiter2
        assert isinstance(limiter1, SlidingWindowRateLimiter)

    def test_historical_limiter_rate_is_three_per_second(self) -> None:
        """Test that the historical limiter is configured at 3 requests per second."""
        session = ZerodhaSession(
            api_key="test_key",
            api_secret="test_secret",
            redirect_url="http://localhost:8765/callback",
        )

        assert session.historical_limiter.rate == 3.0

    @pytest.mark.asyncio
    async def test_historical_limiter_paces_concurrent_clients(self) -> None:
        """Test that multiple clients sharing a session are paced by the same limiter."""
        session = ZerodhaSession(
            api_key="test_key",
            api_secret="test_secret",
            redirect_url="http://localhost:8765/callback",
        )

        limiter = session.historical_limiter
        # Consume all 3 tokens
        assert limiter.try_consume() is True
        assert limiter.try_consume() is True
        assert limiter.try_consume() is True
        assert limiter.try_consume() is False

        # A fourth acquire should wait for the window to expire
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.9
