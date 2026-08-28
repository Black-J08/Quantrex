"""Tests for Dhan HTTP client error handling and non-JSON body safety.

These tests pin the behavior of ``DhanAPIClient._request`` when Dhan returns
non-JSON bodies (e.g. 301 Moved Permanently HTML for invalid auth). Before
the fix, the client called ``response.json()`` directly on these bodies and
the underlying ``JSONDecodeError`` was wrapped in a misleading
``DhanAPIError``, hiding the real status code.
"""

import json
from unittest.mock import Mock, patch

import httpx
import pytest

from quantrex_data.providers.dhan_provider.client import DhanAPIClient
from quantrex_data.providers.dhan_provider.config import DhanProviderConfig
from quantrex_data.providers.dhan_provider.exceptions import (
    DhanAPIError,
    DhanAuthenticationError,
    DhanInvalidParameterError,
    DhanRateLimitError,
)


def _make_client() -> DhanAPIClient:
    """Build a DhanAPIClient without performing a network request."""
    config = DhanProviderConfig(
        security_id="1333",
        exchange_segment="NSE_EQ",
        instrument="EQUITY",
        from_date="2024-01-01",
        to_date="2024-01-31",
        access_token="test_token",
        client_id="1234567890",
    )
    return DhanAPIClient(config)


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
        assert DhanAPIClient._safe_response_json(response) is None

    def test_json_content_type_parses_correctly(self):
        response = httpx.Response(
            200,
            content=b'{"key": "value"}',
            headers={"content-type": "application/json"},
        )
        assert DhanAPIClient._safe_response_json(response) == {"key": "value"}

    def test_html_body_returns_preview_dict(self):
        """Dhan 301/HTML for failed auth must not crash JSON parsing."""
        body = "<html><head><title>301 Moved Permanently</title></head></html>"
        response = _fake_response(301, body, content_type="text/html")
        result = DhanAPIClient._safe_response_json(response)
        assert isinstance(result, dict)
        assert "raw_body" in result
        assert "301 Moved Permanently" in result["raw_body"]
        assert result["content_type"] == "text/html"

    def test_plain_text_body_returns_preview_dict(self):
        body = "Internal Server Error"
        response = _fake_response(500, body, content_type="text/plain")
        result = DhanAPIClient._safe_response_json(response)
        assert isinstance(result, dict)
        assert "Internal Server Error" in result["raw_body"]

    def test_json_content_type_with_invalid_json_returns_preview(self):
        """Even when content-type claims JSON, malformed bodies must not crash."""
        body = "not really json{"
        response = _fake_response(502, body, content_type="application/json")
        result = DhanAPIClient._safe_response_json(response)
        assert isinstance(result, dict)
        assert "raw_body" in result


class TestRequestErrorHandling:
    """Integration-style tests for _request error paths."""

    def test_401_with_html_body_raises_auth_error(self):
        """Dhan returns 301/HTML for invalid auth - must raise DhanAuthenticationError, not DhanAPIError."""
        client = _make_client()
        # Bypass the retry decorator so this stays a unit test.
        with patch.object(client._client, "request") as mock_request:
            mock_request.return_value = _fake_response(
                401,
                "<html><head><title>401 Unauthorized</title></head></html>",
                content_type="text/html",
            )
            with pytest.raises(DhanAuthenticationError) as exc_info:
                client._request("POST", "/charts/historical", json_data={})
            assert exc_info.value.status_code == 401
            # The HTML body preview should be preserved in response_data.
            assert exc_info.value.response_data is not None
            assert "401 Unauthorized" in exc_info.value.response_data["raw_body"]

    def test_403_with_html_body_raises_auth_error(self):
        client = _make_client()
        with patch.object(client._client, "request") as mock_request:
            mock_request.return_value = _fake_response(403, "<html>forbidden</html>")
            with pytest.raises(DhanAuthenticationError):
                client._request("POST", "/charts/historical", json_data={})

    def test_429_with_json_body_raises_rate_limit(self):
        client = _make_client()
        with patch.object(client._client, "request") as mock_request:
            mock_request.return_value = _fake_response(
                429,
                json.dumps({"errorType": "RATE_LIMIT_ERROR", "errorCode": "RL001"}),
                content_type="application/json",
            )
            with pytest.raises(DhanRateLimitError) as exc_info:
                client._request("POST", "/charts/historical", json_data={})
            assert exc_info.value.status_code == 429
            assert exc_info.value.response_data["errorCode"] == "RL001"

    def test_400_with_dhan_error_code_raises_invalid_param(self):
        """400 with errorCode 813 (Invalid SecurityId) maps to DhanInvalidParameterError."""
        client = _make_client()
        with patch.object(client._client, "request") as mock_request:
            mock_request.return_value = _fake_response(
                400,
                json.dumps({
                    "errorType": "Input_Exception",
                    "errorCode": "813",
                    "errorMessage": "Invalid SecurityId",
                }),
                content_type="application/json",
            )
            with pytest.raises(DhanInvalidParameterError) as exc_info:
                client._request("POST", "/charts/historical", json_data={})
            assert exc_info.value.error_code == 813

    def test_400_with_html_body_does_not_crash(self):
        """A 400 with an HTML body (e.g. CDN error page) must raise a clean exception, not JSONDecodeError."""
        client = _make_client()
        with patch.object(client._client, "request") as mock_request:
            mock_request.return_value = _fake_response(400, "<html>bad gateway</html>")
            with pytest.raises(DhanInvalidParameterError) as exc_info:
                client._request("POST", "/charts/historical", json_data={})
            assert exc_info.value.status_code == 400
            assert exc_info.value.response_data is not None
            assert "bad gateway" in exc_info.value.response_data["raw_body"]

    def test_500_with_html_body_raises_dhan_api_error(self):
        client = _make_client()
        with patch.object(client._client, "request") as mock_request:
            mock_request.return_value = _fake_response(500, "<html>oops</html>")
            with pytest.raises(DhanAPIError) as exc_info:
                client._request("POST", "/charts/historical", json_data={})
            assert exc_info.value.status_code == 500

    def test_301_html_body_raises_dhan_api_error_with_status(self):
        """The original failure: Dhan's CDN returns 301/HTML for invalid auth,
        which used to surface as a JSONDecodeError wrapped in DhanAPIError.
        Now it must surface with the real 301 status code preserved."""
        client = _make_client()
        with patch.object(client._client, "request") as mock_request:
            mock_request.return_value = _fake_response(
                301,
                "<html><head><title>301 Moved Permanently</title></head></html>",
            )
            with pytest.raises(DhanAPIError) as exc_info:
                client._request("POST", "/charts/historical", json_data={})
            assert exc_info.value.status_code == 301
            # 301 isn't auth, isn't rate-limit, isn't 400, isn't 5xx, so it
            # falls through to the generic "API error" path - and the HTML
            # body preview must be preserved for debugging.
            assert "301 Moved Permanently" in exc_info.value.response_data["raw_body"]


class TestClientIdRequired:
    """Dhan v2 requires both ``access-token`` and ``client-id`` headers.

    The official dhan-oss/DhanHQ-py SDK sets both on every request, and a
    missing ``client-id`` causes the gateway to return 301/400 instead of the
    expected JSON. These tests pin the client_id handling in three places:
    header injection, body injection, and error reporting when missing.
    """

    def test_request_injects_client_id_header(self):
        """The client must set the ``client-id`` header on every request."""
        client = _make_client()
        with patch.object(client._client, "request") as mock_request:
            mock_request.return_value = _fake_response(
                200, '{"open":[],"high":[],"low":[],"close":[],"volume":[],"timestamp":[]}',
                content_type="application/json",
            )
            client._request("GET", "/some/endpoint")
            # The httpx.Client.request was called with kwargs containing
            # the merged headers. httpx stores the live headers in
            # ``self._client.headers`` (a HeaderDict), so check there.
            assert client._client.headers.get("client-id") == "1234567890"
            assert client._client.headers.get("access-token") == "test_token"

    def test_request_raises_when_client_id_missing(self):
        """Missing client-id must surface as a clean DhanAuthenticationError."""
        config = DhanProviderConfig(
            security_id="1333",
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date="2024-01-01",
            to_date="2024-01-31",
            access_token="test_token",
            # No client_id, no env, no JWT claim.
        )
        client = DhanAPIClient(config)
        with pytest.raises(DhanAuthenticationError, match="DHAN_CLIENT_ID not found"):
            client._request("GET", "/some/endpoint")

    def test_get_daily_historical_injects_dhan_client_id_in_body(self):
        """The daily-historical request body must include ``dhanClientId``."""
        from quantrex_data.providers.dhan_provider.models import HistoricalDataRequest

        client = _make_client()
        request = HistoricalDataRequest(
            securityId="1333",
            exchangeSegment="NSE_EQ",
            instrument="EQUITY",
            expiryCode=0,
            oi=False,
            fromDate="2024-01-01",
            toDate="2024-01-05",
        )
        with patch.object(client._client, "request") as mock_request:
            mock_request.return_value = _fake_response(
                200, '{"open":[1.0],"high":[1.0],"low":[1.0],"close":[1.0],"volume":[1],"timestamp":[1]}',
                content_type="application/json",
            )
            client.get_daily_historical(request)
            # Inspect the request body the client sent.
            call_kwargs = mock_request.call_args.kwargs
            assert call_kwargs["json"]["dhanClientId"] == "1234567890"

    def test_get_intraday_historical_injects_dhan_client_id_in_body(self):
        """The intraday request body must include ``dhanClientId``."""
        from quantrex_data.providers.dhan_provider.models import IntradayDataRequest

        client = _make_client()
        request = IntradayDataRequest(
            securityId="1333",
            exchangeSegment="NSE_EQ",
            instrument="EQUITY",
            interval="5",
            oi=False,
            fromDate="2024-01-01",
            toDate="2024-01-05",
        )
        with patch.object(client._client, "request") as mock_request:
            mock_request.return_value = _fake_response(
                200, '{"open":[1.0],"high":[1.0],"low":[1.0],"close":[1.0],"volume":[1],"timestamp":[1]}',
                content_type="application/json",
            )
            client.get_intraday_historical(request)
            call_kwargs = mock_request.call_args.kwargs
            assert call_kwargs["json"]["dhanClientId"] == "1234567890"


class TestV2BaseUrl:
    """Dhan v2 endpoints are served under ``/v2/``; the legacy base URL
    returns 301/HTML from CloudFront. These tests pin the wiring so the
    framework never silently falls back to the legacy base.
    """

    def test_client_uses_v2_base_url_by_default(self):
        """The httpx client must be constructed with the /v2 base URL."""
        client = _make_client()
        assert str(client._client.base_url).rstrip("/") == "https://api.dhan.co/v2"

    def test_get_daily_historical_uses_relative_path(self):
        """``/charts/historical`` is the path under the v2 base URL."""
        from quantrex_data.providers.dhan_provider.models import HistoricalDataRequest

        client = _make_client()
        request = HistoricalDataRequest(
            securityId="1333",
            exchangeSegment="NSE_EQ",
            instrument="EQUITY",
            expiryCode=0,
            oi=False,
            fromDate="2024-01-01",
            toDate="2024-01-05",
        )
        with patch.object(client._client, "request") as mock_request:
            mock_request.return_value = _fake_response(
                200, '{"open":[1.0],"high":[1.0],"low":[1.0],"close":[1.0],"volume":[1],"timestamp":[1]}',
                content_type="application/json",
            )
            client.get_daily_historical(request)
            # The relative path passed to the client. With the v2 base URL,
            # httpx will resolve this to https://api.dhan.co/v2/charts/historical.
            assert mock_request.call_args.args[1] == "/charts/historical"
