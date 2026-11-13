"""Tests for ShoonyaSession."""

from __future__ import annotations

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

    def test_create_session_oauth_client_id_falls_back_to_client_id(self) -> None:
        """Test OAuth client ID falls back to regular client_id when not specified."""
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
