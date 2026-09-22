"""Tests for CallbackServer."""

import pytest
import threading
import time
from unittest.mock import Mock, patch, MagicMock
from http.client import HTTPConnection

from quantrex_data.providers.zerodha_provider.callback_server import CallbackServer, CallbackHandler


class TestCallbackServer:
    """Tests for CallbackServer."""

    def test_server_starts_and_stops(self):
        """Server should start and stop cleanly."""
        server = CallbackServer(host="localhost", port=0, path="/callback", timeout=1.0)  # port 0 = OS assigns
        callback_url = server.start()

        assert callback_url.startswith("http://localhost:")
        assert server._started is True
        assert server._server is not None
        assert server._thread is not None
        assert server._thread.is_alive()

        server.stop()

        assert server._started is False
        assert server._server is None
        assert server._thread is None

    def test_server_context_manager(self):
        """Server should work as context manager."""
        with CallbackServer(host="localhost", port=0, path="/callback", timeout=1.0) as server:
            callback_url = server._callback_url  # Access the URL set by __enter__
            assert server._started is True
        # Should be stopped after context exit
        assert server._started is False

    def test_wait_for_token_success(self):
        """wait_for_token should return request_token when received."""
        server = CallbackServer(host="localhost", port=0, path="/callback", timeout=5.0)
        callback_url = server.start()

        # Simulate a callback request in a separate thread
        def make_request():
            time.sleep(0.2)
            conn = HTTPConnection("localhost", server.port)
            conn.request("GET", "/callback?request_token=test_token_123")
            response = conn.getresponse()
            assert response.status == 200
            conn.close()

        request_thread = threading.Thread(target=make_request)
        request_thread.start()

        token = server.wait_for_token()

        request_thread.join()
        assert token == "test_token_123"

    def test_wait_for_token_error_status(self):
        """wait_for_token should raise on error status from Zerodha."""
        server = CallbackServer(host="localhost", port=0, path="/callback", timeout=5.0)
        callback_url = server.start()

        def make_request():
            time.sleep(0.2)
            conn = HTTPConnection("localhost", server.port)
            conn.request("GET", "/callback?status=error&message=User%20cancelled")
            response = conn.getresponse()
            assert response.status == 400
            conn.close()

        request_thread = threading.Thread(target=make_request)
        request_thread.start()

        with pytest.raises(RuntimeError, match="Zerodha login failed: User cancelled"):
            server.wait_for_token()

        request_thread.join()

    def test_wait_for_token_timeout(self):
        """wait_for_token should raise TimeoutError on timeout."""
        server = CallbackServer(host="localhost", port=0, path="/callback", timeout=0.5)
        callback_url = server.start()

        # Don't make any request - should timeout
        with pytest.raises(TimeoutError, match="Timeout waiting for Zerodha callback"):
            server.wait_for_token()

    def test_wait_for_token_missing_token(self):
        """wait_for_token should raise on callback without request_token."""
        server = CallbackServer(host="localhost", port=0, path="/callback", timeout=5.0)
        callback_url = server.start()

        def make_request():
            time.sleep(0.2)
            conn = HTTPConnection("localhost", server.port)
            conn.request("GET", "/callback?foo=bar")
            response = conn.getresponse()
            assert response.status == 400
            conn.close()

        request_thread = threading.Thread(target=make_request)
        request_thread.start()

        with pytest.raises(RuntimeError, match="No request_token or status in callback"):
            server.wait_for_token()

        request_thread.join()

    def test_wait_for_token_not_started(self):
        """wait_for_token should raise if server not started."""
        server = CallbackServer(host="localhost", port=0, path="/callback", timeout=1.0)
        # Don't call start()

        with pytest.raises(RuntimeError, match="Callback server not started"):
            server.wait_for_token()

    def test_double_start_raises(self):
        """Starting server twice should raise RuntimeError."""
        server = CallbackServer(host="localhost", port=0, path="/callback", timeout=1.0)
        server.start()

        with pytest.raises(RuntimeError, match="Callback server already started"):
            server.start()

        server.stop()

    def test_callback_handler_404(self):
        """Handler should return 404 for non-callback paths."""
        server = CallbackServer(host="localhost", port=0, path="/callback", timeout=1.0)
        callback_url = server.start()

        conn = HTTPConnection("localhost", server.port)
        conn.request("GET", "/other")
        response = conn.getresponse()
        assert response.status == 404
        conn.close()

        server.stop()

    def test_callback_returns_html_success(self):
        """Callback should return HTML success page."""
        server = CallbackServer(host="localhost", port=0, path="/callback", timeout=5.0)
        callback_url = server.start()

        conn = HTTPConnection("localhost", server.port)
        conn.request("GET", "/callback?request_token=test123")
        response = conn.getresponse()
        assert response.status == 200
        content = response.read().decode("utf-8")
        assert "Authentication Successful" in content
        assert "✓" in content
        conn.close()

        server.wait_for_token()  # Consume the token
        server.stop()

    def test_callback_returns_html_error(self):
        """Callback should return HTML error page."""
        server = CallbackServer(host="localhost", port=0, path="/callback", timeout=5.0)
        callback_url = server.start()

        conn = HTTPConnection("localhost", server.port)
        conn.request("GET", "/callback?status=error&message=Test%20error")
        response = conn.getresponse()
        assert response.status == 400
        content = response.read().decode("utf-8")
        assert "Authentication Failed" in content
        assert "Test error" in content
        conn.close()

        server.stop()

    def test_port_conflict_raises_oserror(self):
        """Starting server on port already in use should raise OSError."""
        server1 = CallbackServer(host="localhost", port=0, path="/callback", timeout=1.0)
        callback_url = server1.start()
        # Extract the actual port assigned
        actual_port = server1.port

        server2 = CallbackServer(host="localhost", port=actual_port, path="/callback", timeout=1.0)

        with pytest.raises(OSError):
            server2.start()

        server1.stop()

    def test_stop_idempotent(self):
        """Calling stop multiple times should not raise."""
        server = CallbackServer(host="localhost", port=0, path="/callback", timeout=1.0)
        server.start()
        server.stop()
        server.stop()  # Should not raise
        assert server._started is False


class TestCallbackHandler:
    """Tests for CallbackHandler (indirectly via CallbackServer)."""

    def test_handler_extracts_request_token(self):
        """Handler should extract request_token from query."""
        server = CallbackServer(host="localhost", port=0, path="/callback", timeout=5.0)
        callback_url = server.start()

        conn = HTTPConnection("localhost", server.port)
        conn.request("GET", "/callback?request_token=abc123&status=success")
        response = conn.getresponse()
        assert response.status == 200
        conn.close()

        token = server.wait_for_token()
        assert token == "abc123"

    def test_handler_extracts_error_message(self):
        """Handler should extract error message from query."""
        server = CallbackServer(host="localhost", port=0, path="/callback", timeout=5.0)
        callback_url = server.start()

        def make_request():
            time.sleep(0.2)
            conn = HTTPConnection("localhost", server.port)
            conn.request("GET", "/callback?status=error&message=Invalid%20api_key")
            response = conn.getresponse()
            assert response.status == 400
            conn.close()

        request_thread = threading.Thread(target=make_request)
        request_thread.start()

        with pytest.raises(RuntimeError, match="Zerodha login failed: Invalid api_key"):
            server.wait_for_token()

        request_thread.join()

class TestCustomPath:
    """Tests for custom callback path."""

    def test_custom_path(self):
        """Server should work with custom callback path."""
        server = CallbackServer(host="localhost", port=0, path="/auth/zerodha/callback", timeout=5.0)
        callback_url = server.start()

        assert "/auth/zerodha/callback" in callback_url

        def make_request():
            time.sleep(0.2)
            conn = HTTPConnection("localhost", server.port)
            conn.request("GET", "/auth/zerodha/callback?request_token=custom_path_token")
            response = conn.getresponse()
            assert response.status == 200
            conn.close()

        request_thread = threading.Thread(target=make_request)
        request_thread.start()

        token = server.wait_for_token()
        assert token == "custom_path_token"
        request_thread.join()

    def test_custom_path_404_on_wrong_path(self):
        """Server should return 404 for wrong path when using custom path."""
        server = CallbackServer(host="localhost", port=0, path="/auth/zerodha/callback", timeout=5.0)
        callback_url = server.start()

        conn = HTTPConnection("localhost", server.port)
        conn.request("GET", "/callback?request_token=wrong_path_token")
        response = conn.getresponse()
        assert response.status == 404
        conn.close()

        server.stop()
