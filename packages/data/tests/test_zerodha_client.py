"""Tests for Zerodha HTTP client error handling and non-JSON body safety.

These tests pin the behavior of ``ZerodhaAPIClient._request`` when Zerodha returns
non-JSON bodies (e.g., 502/503 HTML for server errors). Before
the fix, the client called ``response.json()`` directly on these bodies and
the underlying ``JSONDecodeError`` was wrapped in a misleading
``ZerodhaAPIError``, hiding the real status code.
"""

import json
from unittest.mock import Mock, patch

import httpx
import pytest

from quantrex_data.providers.zerodha_provider.client import ZerodhaAPIClient
from quantrex_data.providers.zerodha_provider.config import ZerodhaProviderConfig
from quantrex_data.providers.zerodha_provider.exceptions import (
    ZerodhaAPIError,
    ZerodhaAuthenticationError,
    ZerodhaInvalidParameterError,
    ZerodhaRateLimitError,
)


def _make_client() -> ZerodhaAPIClient:
    """Build a ZerodhaAPIClient without performing a network request."""
    config = ZerodhaProviderConfig(
        api_key="test_key",
        api_secret="test_secret",
        access_token="test_token",
        symbol="RELIANCE",
        exchange="NSE",
        from_date="2024-01-01",
        to_date="2024-01-31",
    )
    return ZerodhaAPIClient(config)


def _fake_response(status_code: int, body: str, content_type: str = "text/html") -> httpx.Response:
    """Construct an httpx.Response for unit tests without going through the network."""
    return httpx.Response(
        status_code=status_code,
        content=body.encode("utf-8"),
        headers={"content-type": content_type},
    )


class TestSafeResponseJson:
    """Unit tests for the JSON-safe body parser."""

    def test_empty_body_returns_none(self):
        response = httpx.Response(204, content=b"")
        assert ZerodhaAPIClient._safe_response_json(response) is None

    def test_json_content_type_parses_correctly(self):
        response = httpx.Response(
            200,
            content=b'{"key": "value"}',
            headers={"content-type": "application/json"},
        )
        assert ZerodhaAPIClient._safe_response_json(response) == {"key": "value"}

    def test_html_body_returns_preview_dict(self):
        """Zerodha 502/HTML for server errors must not crash JSON parsing."""
        body = "<html><head><title>502 Bad Gateway</title></head></html>"
        response = _fake_response(502, body, content_type="text/html")
        result = ZerodhaAPIClient._safe_response_json(response)
        assert isinstance(result, dict)
        assert "raw_body" in result
        assert "502 Bad Gateway" in result["raw_body"]
        assert result["content_type"] == "text/html"

    def test_plain_text_body_returns_preview_dict(self):
        body = "Internal Server Error"
        response = _fake_response(500, body, content_type="text/plain")
        result = ZerodhaAPIClient._safe_response_json(response)
        assert isinstance(result, dict)
        assert "Internal Server Error" in result["raw_body"]

    def test_json_content_type_with_invalid_json_returns_preview(self):
        """Even when content-type claims JSON, malformed bodies must not crash."""
        body = "not really json{"
        response = _fake_response(502, body, content_type="application/json")
        result = ZerodhaAPIClient._safe_response_json(response)
        assert isinstance(result, dict)
        assert "raw_body" in result


class TestRequestErrorHandling:
    """Integration-style tests for _request error paths."""

    def test_403_with_token_exception_raises_auth_error(self):
        """Zerodha returns 403 with TokenException - must raise ZerodhaAuthenticationError."""
        client = _make_client()
        with patch.object(client._client, "request") as mock_request:
            mock_request.return_value = _fake_response(
                403,
                '{"status": "error", "message": "TokenException: Token expired", "error_type": "TokenException"}',
                content_type="application/json",
            )
            with pytest.raises(ZerodhaAuthenticationError) as exc:
                client._request("GET", "/test")
            assert "TokenException" in str(exc.value)
            assert exc.value.status_code == 403

    def test_403_with_html_body_raises_auth_error(self):
        """Zerodha returns 403/HTML for invalid auth - must raise ZerodhaAuthenticationError."""
        client = _make_client()
        with patch.object(client._client, "request") as mock_request:
            mock_request.return_value = _fake_response(
                403,
                "<html><head><title>403 Forbidden</title></head></html>",
            )
            with pytest.raises(ZerodhaAuthenticationError) as exc:
                client._request("GET", "/test")
            assert exc.value.status_code == 403

    def test_429_raises_rate_limit_error(self):
        """429 must raise ZerodhaRateLimitError."""
        client = _make_client()
        with patch.object(client._client, "request") as mock_request:
            mock_request.return_value = _fake_response(
                429,
                '{"status": "error", "message": "Rate limit exceeded", "error_type": "RateLimitException"}',
                content_type="application/json",
            )
            with pytest.raises(ZerodhaRateLimitError) as exc:
                client._request("GET", "/test")
            assert exc.value.status_code == 429

    def test_400_input_exception_raises_invalid_param_error(self):
        """400 with InputException must raise ZerodhaInvalidParameterError."""
        client = _make_client()
        with patch.object(client._client, "request") as mock_request:
            mock_request.return_value = _fake_response(
                400,
                '{"status": "error", "message": "InputException: Invalid instrument_token", "error_type": "InputException"}',
                content_type="application/json",
            )
            with pytest.raises(ZerodhaInvalidParameterError) as exc:
                client._request("GET", "/test")
            assert exc.value.status_code == 400

    def test_500_raises_api_error(self):
        """500 must raise ZerodhaAPIError."""
        client = _make_client()
        with patch.object(client._client, "request") as mock_request:
            mock_request.return_value = _fake_response(
                500,
                '{"status": "error", "message": "Internal server error", "error_type": "GeneralException"}',
                content_type="application/json",
            )
            with pytest.raises(ZerodhaAPIError) as exc:
                client._request("GET", "/test")
            assert exc.value.status_code == 500

    def test_502_html_raises_api_error_not_json_decode_error(self):
        """502 with HTML body must raise ZerodhaAPIError, not JSONDecodeError."""
        client = _make_client()
        with patch.object(client._client, "request") as mock_request:
            mock_request.return_value = _fake_response(
                502,
                "<html><head><title>502 Bad Gateway</title></head><body>Gateway Error</body></html>",
            )
            with pytest.raises(ZerodhaAPIError) as exc:
                client._request("GET", "/test")
            assert exc.value.status_code == 502
            # The error should contain the HTML preview
            assert "502 Bad Gateway" in str(exc.value)


class TestRateLimiter:
    """Tests for TokenBucketRateLimiter."""

    def test_rate_limiter_allows_burst(self):
        """Rate limiter should allow burst up to bucket size."""
        from quantrex_data.providers.zerodha_provider.client import TokenBucketRateLimiter
        limiter = TokenBucketRateLimiter(rate=10.0, burst=5)
        # Should allow 5 immediate requests
        for _ in range(5):
            limiter.acquire()
        # 6th should block (we won't test blocking to keep test fast)

    def test_rate_limiter_refills_over_time(self):
        """Rate limiter should refill tokens over time."""
        from quantrex_data.providers.zerodha_provider.client import TokenBucketRateLimiter
        import time
        limiter = TokenBucketRateLimiter(rate=100.0, burst=1)  # Very fast refill
        limiter.acquire()  # Use the one token
        time.sleep(0.02)  # Wait for refill (100 tokens/sec = 0.01 sec per token)
        # Should be able to acquire again without long block
        limiter.acquire()