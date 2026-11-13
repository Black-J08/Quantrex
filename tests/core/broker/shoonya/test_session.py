"""Tests for ShoonyaSession."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantrex.core.broker.shoonya.auth.token_store import TokenInfo
from quantrex.core.broker.shoonya.exceptions.exceptions import (
    ShoonyaDataError,
    ShoonyaInputError,
    ShoonyaNotFoundError,
    ShoonyaRateLimitError,
    ShoonyaServerError,
    ShoonyaTokenExpiredError,
)
from quantrex.core.broker.shoonya.session.session import SessionConfig, ShoonyaSession
from quantrex.core.utility.rate_limiter import SlidingWindowRateLimiter


class TestShoonyaSession:
    """Tests for ShoonyaSession."""

    def test_create_session_with_env_vars(self, monkeypatch) -> None:
        """Test creating session with environment variables."""
        monkeypatch.setenv("SHOONYA_CLIENT_ID", "test_client")
        monkeypatch.setenv("SHOONYA_SECRET_KEY", "test_secret")
        monkeypatch.setenv("SHOONYA_REDIRECT_URL", "http://localhost:8765/callback")

        session = ShoonyaSession()
        assert session.client_id == "test_client"
        assert session.secret_key == "test_secret"
        assert session.callback_host == "localhost"
        assert session.callback_port == 8765
        assert session.callback_path == "/callback"

    def test_create_session_with_oauth_client_id_explicit(self) -> None:
        """Test creating session with explicit OAuth client ID."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                oauth_client_id="PREFIX_test_client",
                redirect_url="http://localhost:8765/callback",
            )
        )
        assert session.client_id == "test_client"
        assert session.oauth_client_id == "PREFIX_test_client"

    def test_create_session_with_oauth_client_id_from_env(self, monkeypatch) -> None:
        """Test creating session with OAuth client ID from environment variable."""
        monkeypatch.setenv("SHOONYA_CLIENT_ID", "test_client")
        monkeypatch.setenv("SHOONYA_SECRET_KEY", "test_secret")
        monkeypatch.setenv("SHOONYA_OAUTH_CLIENT_ID", "PREFIX_test_client")
        monkeypatch.setenv("SHOONYA_REDIRECT_URL", "http://localhost:8765/callback")

        session = ShoonyaSession()
        assert session.client_id == "test_client"
        assert session.oauth_client_id == "PREFIX_test_client"

    def test_create_session_oauth_client_id_falls_back_to_client_id(
        self, monkeypatch
    ) -> None:
        """Test OAuth client ID falls back to regular client_id when not specified."""
        monkeypatch.delenv("SHOONYA_OAUTH_CLIENT_ID", raising=False)
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )
        assert session.client_id == "test_client"
        assert session.oauth_client_id == "test_client"

    def test_create_session_oauth_client_id_env_falls_back_to_client_id(
        self, monkeypatch
    ) -> None:
        """Test OAuth client ID env var falls back to client_id when not set."""
        monkeypatch.setenv("SHOONYA_CLIENT_ID", "test_client")
        monkeypatch.setenv("SHOONYA_SECRET_KEY", "test_secret")
        monkeypatch.setenv("SHOONYA_REDIRECT_URL", "http://localhost:8765/callback")
        monkeypatch.delenv("SHOONYA_OAUTH_CLIENT_ID", raising=False)
        # SHOONYA_OAUTH_CLIENT_ID not set

        session = ShoonyaSession()
        assert session.client_id == "test_client"
        assert session.oauth_client_id == "test_client"

    def test_create_session_with_explicit_args(self) -> None:
        """Test creating session with explicit arguments."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="explicit_client",
                secret_key="explicit_secret",
                redirect_url="http://localhost:9999/auth/callback",
            )
        )
        assert session.client_id == "explicit_client"
        assert session.secret_key == "explicit_secret"
        assert session.callback_host == "localhost"
        assert session.callback_port == 9999
        assert session.callback_path == "/auth/callback"

    def test_create_session_with_redirect_url_env(self, monkeypatch) -> None:
        """Test creating session with redirect URL from env."""
        monkeypatch.setenv("SHOONYA_CLIENT_ID", "test_client")
        monkeypatch.setenv("SHOONYA_SECRET_KEY", "test_secret")
        monkeypatch.setenv("SHOONYA_REDIRECT_URL", "http://localhost:9999/auth/callback")
        monkeypatch.setenv("SHOONYA_CALLBACK_TIMEOUT", "60.0")

        session = ShoonyaSession()
        assert session.callback_host == "localhost"
        assert session.callback_port == 9999
        assert session.callback_path == "/auth/callback"
        assert session.callback_timeout == 60.0

    def test_create_session_missing_credentials(self, monkeypatch) -> None:
        """Test creating session without credentials raises error."""
        monkeypatch.delenv("SHOONYA_CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOONYA_SECRET_KEY", raising=False)

        with pytest.raises(ValueError, match="Client ID and secret key are required"):
            ShoonyaSession()

    def test_create_session_missing_redirect_url(self, monkeypatch) -> None:
        """Test creating session without redirect URL raises error."""
        monkeypatch.setenv("SHOONYA_CLIENT_ID", "test_client")
        monkeypatch.setenv("SHOONYA_SECRET_KEY", "test_secret")
        monkeypatch.delenv("SHOONYA_REDIRECT_URL", raising=False)

        with pytest.raises(ValueError, match="Redirect URL is required"):
            ShoonyaSession()

    @pytest.mark.asyncio
    async def test_get_valid_token_from_cache(self) -> None:
        """Test getting valid token from cache."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )

        # Set a valid cached token
        future = datetime.now(UTC) + timedelta(hours=1)
        token_info = TokenInfo(
            access_token="cached_token",
            user_id="user123",
            expires_at=future,
            api_key="test_client",
        )
        session._token_info = token_info

        token = await session._get_valid_token()
        assert token == "cached_token"

    def _make_mock_response(
        self, status_code: int, json_data: Any | None = None
    ) -> MagicMock:
        """Create a mock httpx response."""
        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.text = ""
        mock_response.headers = {}
        if json_data is not None:
            mock_response.json.return_value = json_data
        else:
            mock_response.json.side_effect = ValueError("No JSON")
        return mock_response

    def test_handle_error_response_400(self) -> None:
        """Test HTTP 400 maps to ShoonyaInputError."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )
        response = self._make_mock_response(400, {"stat": "Not_Ok", "emsg": "Bad request"})
        with pytest.raises(ShoonyaInputError):
            session._handle_error_response(response)

    def test_handle_error_response_403(self) -> None:
        """Test HTTP 403 maps to ShoonyaTokenExpiredError."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )
        response = self._make_mock_response(403)
        with pytest.raises(ShoonyaTokenExpiredError):
            session._handle_error_response(response)

    def test_handle_error_response_404(self) -> None:
        """Test HTTP 404 maps to ShoonyaNotFoundError."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )
        response = self._make_mock_response(404)
        with pytest.raises(ShoonyaNotFoundError):
            session._handle_error_response(response)

    def test_handle_error_response_429(self) -> None:
        """Test HTTP 429 maps to ShoonyaRateLimitError."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )
        response = self._make_mock_response(429)
        response.headers = {"Retry-After": "10"}
        with pytest.raises(ShoonyaRateLimitError) as exc_info:
            session._handle_error_response(response)
        assert exc_info.value.retry_after == 10.0

    def test_handle_error_response_500(self) -> None:
        """Test HTTP 500 maps to ShoonyaServerError."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )
        response = self._make_mock_response(500)
        with pytest.raises(ShoonyaServerError):
            session._handle_error_response(response)

    def test_handle_error_response_stat_not_ok_rate_limited(self) -> None:
        """Test stat: Not_Ok with Rate_Limited maps to ShoonyaRateLimitError."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )
        response = self._make_mock_response(
            200, {"stat": "Not_Ok", "emsg": "Rate_Limited: too many requests"}
        )
        with pytest.raises(ShoonyaRateLimitError):
            session._handle_error_response(response)

    def test_handle_error_response_stat_not_ok_invalid_session(self) -> None:
        """Test stat: Not_Ok with Invalid Session maps to ShoonyaTokenExpiredError."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )
        response = self._make_mock_response(
            200, {"stat": "Not_Ok", "emsg": "Invalid Session Key"}
        )
        with pytest.raises(ShoonyaTokenExpiredError):
            session._handle_error_response(response)

    def test_handle_error_response_stat_ok(self) -> None:
        """Test stat: Ok does not raise."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )
        response = self._make_mock_response(200, {"stat": "Ok", "data": {}})
        session._handle_error_response(response)  # Should not raise

    def test_handle_error_response_list_success(self) -> None:
        """Test TPSeries/EODChartData flat list success response does not raise."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )
        # TPSeries returns a flat list of candle dicts on success
        response = self._make_mock_response(
            200,
            [
                {
                    "time": "07-12-2022 09:15:00",
                    "into": "255.00",
                    "inth": "255.65",
                    "intl": "254.65",
                    "intc": "255.65",
                    "intv": "146",
                    "v": "146",
                    "oi": "0",
                },
            ],
        )
        session._handle_error_response(response)  # Should not raise

    def test_handle_error_response_empty_list(self) -> None:
        """Test empty list response does not raise (no data in range)."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )
        response = self._make_mock_response(200, [])
        session._handle_error_response(response)  # Should not raise

    def test_handle_error_response_non_dict_non_list(self) -> None:
        """Test non-dict, non-list JSON response raises ShoonyaDataError."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )
        response = self._make_mock_response(200, "not a dict or list")
        with pytest.raises(ShoonyaDataError):
            session._handle_error_response(response)

    def test_build_request_body(self) -> None:
        """Test building jData request body."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )
        body = session._build_request_body({"uid": "ABC123", "sym": "NSE:INFY"})
        assert body == 'jData={"uid": "ABC123", "sym": "NSE:INFY"}'

    def test_build_auth_header(self) -> None:
        """Test building Bearer auth header."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )
        header = session._build_auth_header("my_token")
        assert header == "Bearer my_token"

    def test_historical_limiter_is_shared(self) -> None:
        """Test historical_limiter returns a SlidingWindowRateLimiter."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )
        limiter = session.historical_limiter
        assert isinstance(limiter, SlidingWindowRateLimiter)
        # Same instance on repeated access
        assert session.historical_limiter is limiter

    @pytest.mark.asyncio
    async def test_request_retries_on_application_level_token_expiry(self) -> None:
        """Regression test: _request retries once when _handle_error_response raises ShoonyaTokenExpiredError.

        Shoonya can return HTTP 200 with stat: Not_Ok and "session expired"/"invalid session"
        emsg. Previously _request only retried on HTTP 403, so application-level token expiry
        propagated uncaught. Now it invalidates the cached token and retries once with a fresh token.
        """
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )

        # First response: HTTP 200 with "session expired" emsg -> triggers retry
        first_response = self._make_mock_response(
            200, {"stat": "Not_Ok", "emsg": "Session Expired : Invalid Session Key"}
        )
        # Second response: HTTP 200 with stat: Ok -> success
        second_response = self._make_mock_response(200, {"stat": "Ok", "data": {}})

        session._client.request = AsyncMock(
            side_effect=[first_response, second_response]
        )
        session._get_valid_token = AsyncMock(return_value="fresh_token")

        response = await session._request("POST", "/TPSeries", json={"uid": "ABC123"})

        assert response is second_response
        # Token was invalidated and refreshed
        assert session._get_valid_token.await_count == 2
        # Two HTTP requests made (original + retry)
        assert session._client.request.await_count == 2

    @pytest.mark.asyncio
    async def test_request_propagates_when_retry_also_token_expired(self) -> None:
        """Edge-case test: _request propagates ShoonyaTokenExpiredError if retry also fails.

        Only one retry is attempted; if the retried request also returns an application-level
        token expiry error, the exception propagates to the caller.
        """
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )

        # Both responses: HTTP 200 with "session expired" emsg
        expired_response = self._make_mock_response(
            200, {"stat": "Not_Ok", "emsg": "Session Expired : Invalid Session Key"}
        )
        session._client.request = AsyncMock(return_value=expired_response)
        session._get_valid_token = AsyncMock(return_value="fresh_token")

        with pytest.raises(ShoonyaTokenExpiredError):
            await session._request("POST", "/TPSeries", json={"uid": "ABC123"})

        # Original request + exactly one retry
        assert session._client.request.await_count == 2
        # Token invalidated and refreshed once
        assert session._get_valid_token.await_count == 2

    @pytest.mark.asyncio
    async def test_request_403_deletes_token_file_and_retries_with_fresh_token(
        self, tmp_path
    ) -> None:
        """Regression test: HTTP 403 deletes token file and retries with fresh token.

        Previously the 403 handler only cleared the in-memory token but left the
        stale token file on disk. On retry, _get_valid_token() would reload the
        same invalid token from disk, causing a retry loop. Now the token file is
        deleted before obtaining a fresh token.
        """
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
                token_path=str(tmp_path / "token.json"),
            )
        )

        # Pre-populate token file with a stale token
        stale_token = TokenInfo(
            access_token="stale_token",
            user_id="user123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            api_key="test_client",
        )
        session.token_path.parent.mkdir(parents=True, exist_ok=True)
        session.token_path.write_text(json.dumps(stale_token.to_dict()))
        assert session.token_path.exists()

        # First response: HTTP 403 -> triggers retry
        first_response = self._make_mock_response(403)
        # Second response: HTTP 200 OK -> success
        second_response = self._make_mock_response(200, {"stat": "Ok", "data": {}})

        session._client.request = AsyncMock(
            side_effect=[first_response, second_response]
        )
        # Mock authenticate to return a fresh token (avoids real OAuth flow)
        session._auth_provider.authenticate = AsyncMock(
            return_value=TokenInfo(
                access_token="fresh_token",
                user_id="user123",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                api_key="test_client",
            )
        )

        response = await session._request("POST", "/TPSeries", json={"uid": "ABC123"})

        assert response is second_response
        # Token file was deleted before retry
        assert not session.token_path.exists()
        # Fresh token obtained on retry
        assert session._auth_provider.authenticate.await_count == 1
        # Two HTTP requests made (original + retry)
        assert session._client.request.await_count == 2

    @pytest.mark.asyncio
    async def test_concurrent_403s_serialize_retries(self) -> None:
        """Regression test: concurrent 403s serialize retries via token lock.

        Previously the 403 handler released the lock before calling
        _get_valid_token(), allowing multiple concurrent 403s to each trigger a
        separate OAuth flow concurrently. Now the lock is held through the retry,
        so concurrent 403s are serialized (one at a time) rather than overlapping.
        """
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
            )
        )

        # Each request gets 403 then OK on retry
        resp_403 = self._make_mock_response(403)
        resp_ok = self._make_mock_response(200, {"stat": "Ok", "data": {}})
        session._client.request = AsyncMock(
            side_effect=[resp_403, resp_ok, resp_403, resp_ok, resp_403, resp_ok]
        )
        # Mock authenticate to return a fresh token (avoids real OAuth flow)
        session._auth_provider.authenticate = AsyncMock(
            return_value=TokenInfo(
                access_token="fresh_token",
                user_id="user123",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                api_key="test_client",
            )
        )

        # Fire 3 concurrent requests
        responses = await asyncio.gather(
            *[
                session._request("POST", "/TPSeries", json={"uid": "ABC123"})
                for _ in range(3)
            ]
        )

        # All 3 requests succeeded
        assert len(responses) == 3
        # Lock serialized the retries: 1 initial authenticate + 3 retries = 4 total
        # (each retry sees _token_info=None and authenticates separately)
        assert session._auth_provider.authenticate.await_count == 4
        # 6 total HTTP requests (3 original + 3 retries)
        assert session._client.request.await_count == 6

    # ------------------------------------------------------------------
    # Token persistence and reuse tests
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_token_reused_across_multiple_requests(self, tmp_path) -> None:
        """A valid cached token is reused across multiple requests without re-authentication."""
        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
                token_path=str(tmp_path / "token.json"),
            )
        )

        # Pre-populate token file with a valid token
        valid_token = TokenInfo(
            access_token="cached_access_token",
            user_id="user123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            api_key="test_client",
        )
        session.token_path.parent.mkdir(parents=True, exist_ok=True)
        session.token_path.write_text(json.dumps(valid_token.to_dict()))

        # First request loads token from file
        resp_ok = self._make_mock_response(200, {"stat": "Ok", "data": {}})
        session._client.request = AsyncMock(return_value=resp_ok)
        session._auth_provider.authenticate = AsyncMock()

        token1 = await session._get_valid_token()
        assert token1 == "cached_access_token"
        # authenticate should NOT be called since token was loaded from file
        session._auth_provider.authenticate.assert_not_awaited()

        # Second request reuses the in-memory cached token
        token2 = await session._get_valid_token()
        assert token2 == "cached_access_token"
        # Still no authenticate call
        session._auth_provider.authenticate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_token_loaded_from_file_on_new_session(self, tmp_path) -> None:
        """A new session loads a valid token from the token file on disk."""
        token_file = tmp_path / "token.json"

        # Pre-populate token file with a valid token
        valid_token = TokenInfo(
            access_token="persisted_token",
            user_id="user123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            api_key="test_client",
        )
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(json.dumps(valid_token.to_dict()))

        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
                token_path=str(token_file),
            )
        )

        resp_ok = self._make_mock_response(200, {"stat": "Ok", "data": {}})
        session._client.request = AsyncMock(return_value=resp_ok)
        session._auth_provider.authenticate = AsyncMock()

        token = await session._get_valid_token()
        assert token == "persisted_token"
        # authenticate should NOT be called since token was loaded from file
        session._auth_provider.authenticate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_token_file_triggers_reauth(self, tmp_path) -> None:
        """An empty/invalid token file triggers re-authentication."""
        token_file = tmp_path / "token.json"
        token_file.write_text("")  # Empty file

        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
                token_path=str(token_file),
            )
        )

        resp_ok = self._make_mock_response(200, {"stat": "Ok", "data": {}})
        session._client.request = AsyncMock(return_value=resp_ok)
        fresh_token = TokenInfo(
            access_token="fresh_token",
            user_id="user123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            api_key="test_client",
        )
        session._auth_provider.authenticate = AsyncMock(return_value=fresh_token)

        token = await session._get_valid_token()
        assert token == "fresh_token"
        session._auth_provider.authenticate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_malformed_token_file_triggers_reauth(self, tmp_path) -> None:
        """A malformed token file triggers re-authentication."""
        token_file = tmp_path / "token.json"
        token_file.write_text("{not valid json")

        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
                token_path=str(token_file),
            )
        )

        resp_ok = self._make_mock_response(200, {"stat": "Ok", "data": {}})
        session._client.request = AsyncMock(return_value=resp_ok)
        fresh_token = TokenInfo(
            access_token="fresh_token",
            user_id="user123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            api_key="test_client",
        )
        session._auth_provider.authenticate = AsyncMock(return_value=fresh_token)

        token = await session._get_valid_token()
        assert token == "fresh_token"
        session._auth_provider.authenticate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_token_with_empty_access_token_triggers_reauth(self, tmp_path) -> None:
        """A token file with an empty access_token triggers re-authentication."""
        token_file = tmp_path / "token.json"

        invalid_token = TokenInfo(
            access_token="",
            user_id="user123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            api_key="test_client",
        )
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(json.dumps(invalid_token.to_dict()))

        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
                token_path=str(token_file),
            )
        )

        resp_ok = self._make_mock_response(200, {"stat": "Ok", "data": {}})
        session._client.request = AsyncMock(return_value=resp_ok)
        fresh_token = TokenInfo(
            access_token="fresh_token",
            user_id="user123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            api_key="test_client",
        )
        session._auth_provider.authenticate = AsyncMock(return_value=fresh_token)

        token = await session._get_valid_token()
        assert token == "fresh_token"
        session._auth_provider.authenticate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_token_file_deleted_on_403_forces_reauth_on_retry(self, tmp_path) -> None:
        """After a 403, the token file is deleted and a fresh token is obtained on retry."""
        token_file = tmp_path / "token.json"

        # Pre-populate token file with a stale token
        stale_token = TokenInfo(
            access_token="stale_token",
            user_id="user123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            api_key="test_client",
        )
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(json.dumps(stale_token.to_dict()))

        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
                token_path=str(token_file),
            )
        )

        # First response: 403 -> triggers retry
        # Second response: 200 OK -> success
        resp_403 = self._make_mock_response(403)
        resp_ok = self._make_mock_response(200, {"stat": "Ok", "data": {}})
        session._client.request = AsyncMock(side_effect=[resp_403, resp_ok])
        fresh_token = TokenInfo(
            access_token="fresh_token",
            user_id="user123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            api_key="test_client",
        )
        session._auth_provider.authenticate = AsyncMock(return_value=fresh_token)

        response = await session._request("POST", "/TPSeries", json={"uid": "ABC123"})

        assert response is resp_ok
        # Token file was deleted
        assert not token_file.exists()
        # Fresh token obtained via authenticate
        session._auth_provider.authenticate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_token_file_deleted_on_application_level_expiry(self, tmp_path) -> None:
        """After application-level token expiry, the token file is deleted and a fresh token is obtained."""
        token_file = tmp_path / "token.json"

        # Pre-populate token file with a stale token
        stale_token = TokenInfo(
            access_token="stale_token",
            user_id="user123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            api_key="test_client",
        )
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(json.dumps(stale_token.to_dict()))

        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
                token_path=str(token_file),
            )
        )

        # First response: 200 with "session expired" -> triggers retry
        # Second response: 200 OK -> success
        expired_response = self._make_mock_response(
            200, {"stat": "Not_Ok", "emsg": "Session Expired : Invalid Session Key"}
        )
        resp_ok = self._make_mock_response(200, {"stat": "Ok", "data": {}})
        session._client.request = AsyncMock(side_effect=[expired_response, resp_ok])
        fresh_token = TokenInfo(
            access_token="fresh_token",
            user_id="user123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            api_key="test_client",
        )
        session._auth_provider.authenticate = AsyncMock(return_value=fresh_token)

        response = await session._request("POST", "/TPSeries", json={"uid": "ABC123"})

        assert response is resp_ok
        # Token file was deleted
        assert not token_file.exists()
        # Fresh token obtained via authenticate
        session._auth_provider.authenticate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_token_reuse_after_successful_reauth(self, tmp_path) -> None:
        """After re-authentication, the new token is cached and reused on subsequent requests."""
        token_file = tmp_path / "token.json"

        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
                token_path=str(token_file),
            )
        )

        # No token file exists initially -> authenticate
        resp_ok = self._make_mock_response(200, {"stat": "Ok", "data": {}})
        session._client.request = AsyncMock(return_value=resp_ok)
        fresh_token = TokenInfo(
            access_token="fresh_token",
            user_id="user123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            api_key="test_client",
        )
        session._auth_provider.authenticate = AsyncMock(return_value=fresh_token)

        # First request triggers authentication
        token1 = await session._get_valid_token()
        assert token1 == "fresh_token"
        session._auth_provider.authenticate.assert_awaited_once()

        # Simulate what the real authenticate() does: save token to file
        session._auth_provider.token_store.save(fresh_token)
        assert token_file.exists()

        # Second request reuses the in-memory cached token
        token2 = await session._get_valid_token()
        assert token2 == "fresh_token"
        # authenticate should NOT be called again
        session._auth_provider.authenticate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_concurrent_requests_share_single_token(self, tmp_path) -> None:
        """Concurrent requests that all need a token share a single authentication flow."""
        token_file = tmp_path / "token.json"

        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
                token_path=str(token_file),
            )
        )

        resp_ok = self._make_mock_response(200, {"stat": "Ok", "data": {}})
        session._client.request = AsyncMock(return_value=resp_ok)
        fresh_token = TokenInfo(
            access_token="fresh_token",
            user_id="user123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            api_key="test_client",
        )
        session._auth_provider.authenticate = AsyncMock(return_value=fresh_token)

        # Fire 5 concurrent requests with no cached token
        tokens = await asyncio.gather(
            *[
                session._get_valid_token()
                for _ in range(5)
            ]
        )

        # All requests got the same token
        assert all(t == "fresh_token" for t in tokens)
        # Only ONE authenticate call (lock serialized access)
        session._auth_provider.authenticate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_authenticate_failure_propagates(self, tmp_path) -> None:
        """If authentication fails, the error propagates to the caller."""
        token_file = tmp_path / "token.json"

        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
                token_path=str(token_file),
            )
        )

        from quantrex.core.broker.shoonya.exceptions.exceptions import ShoonyaAuthError

        session._auth_provider.authenticate = AsyncMock(
            side_effect=ShoonyaAuthError("OAuth failed")
        )

        with pytest.raises(ShoonyaAuthError, match="OAuth failed"):
            await session._get_valid_token()

    @pytest.mark.asyncio
    async def test_load_token_returns_none_when_file_missing(self, tmp_path) -> None:
        """load_token returns None when the token file does not exist."""
        token_file = tmp_path / "nonexistent.json"

        session = ShoonyaSession(
            SessionConfig(
                client_id="test_client",
                secret_key="test_secret",
                redirect_url="http://localhost:8765/callback",
                token_path=str(token_file),
            )
        )

        token_info = await session._auth_provider.load_token()
        assert token_info is None

    @pytest.mark.asyncio
    async def test_save_and_load_token_roundtrip(self, tmp_path) -> None:
        """TokenStore save/load roundtrip preserves all token fields."""
        from quantrex.core.broker.shoonya.auth.token_store import TokenStore

        token_file = tmp_path / "token.json"
        store = TokenStore(token_file)

        original = TokenInfo(
            access_token="access_token_123",
            user_id="user456",
            expires_at=datetime.now(UTC) + timedelta(days=30),
            api_key="api_key_789",
        )

        store.save(original)
        loaded = store.load()

        assert loaded is not None
        assert loaded.access_token == original.access_token
        assert loaded.user_id == original.user_id
        assert loaded.api_key == original.api_key
        assert loaded.expires_at == original.expires_at
        assert loaded.is_valid()
