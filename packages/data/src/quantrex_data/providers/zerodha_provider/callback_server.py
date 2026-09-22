"""Local HTTP callback server for Zerodha Kite Connect OAuth flow."""

import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
from urllib.parse import urlparse, parse_qs

from quantrex_core.logging import get_logger

logger = get_logger(__name__)


class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the callback endpoint."""

    def __init__(self, *args, server_instance: 'CallbackServer', **kwargs):
        self.server_instance = server_instance
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        """Handle GET request to callback endpoint."""
        parsed = urlparse(self.path)
        if parsed.path != self.server_instance.path:
            self.send_error(404, "Not Found")
            return

        query_params = parse_qs(parsed.query)
        request_token = query_params.get("request_token", [None])[0]
        status = query_params.get("status", [None])[0]

        if status == "error":
            error_message = query_params.get("message", ["Unknown error"])[0]
            self.server_instance._set_error(f"Zerodha login failed: {error_message}")
            self._send_error_page(error_message)
        elif request_token:
            self.server_instance._set_token(request_token)
            self._send_success_page()
        else:
            self.server_instance._set_error("No request_token or status in callback")
            self._send_error_page("Invalid callback: missing request_token")

    def _send_success_page(self) -> None:
        """Send HTML success page to browser."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = """
<!DOCTYPE html>
<html>
<head>
    <title>Zerodha Authentication Successful</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
               max-width: 600px; margin: 50px auto; padding: 20px; text-align: center; }
        .success { color: #2e7d32; }
        .icon { font-size: 64px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="icon">✓</div>
    <h1 class="success">Authentication Successful</h1>
    <p>You have successfully authenticated with Zerodha Kite Connect.</p>
    <p>You may now close this window and return to the application.</p>
</body>
</html>
"""
        self.wfile.write(html.encode("utf-8"))

    def _send_error_page(self, error_message: str) -> None:
        """Send HTML error page to browser."""
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Zerodha Authentication Failed</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
               max-width: 600px; margin: 50px auto; padding: 20px; text-align: center; }}
        .error {{ color: #c62828; }}
        .icon {{ font-size: 64px; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <div class="icon">✗</div>
    <h1 class="error">Authentication Failed</h1>
    <p>Error: {error_message}</p>
    <p>Please close this window and try again.</p>
</body>
</html>
"""
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format: str, *args) -> None:
        """Suppress default log messages."""
        logger.debug("Callback server: " + format % args)


class CallbackServer:
    """Local HTTP server to receive Zerodha OAuth redirect with request_token.

    Runs in a background thread and provides a blocking wait_for_token() method
    that returns the request_token when received, or raises on timeout/error.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        path: str = "/callback",
        timeout: float = 120.0,
    ) -> None:
        """Initialize callback server.

        Args:
            host: Host to bind to (default: localhost).
            port: Port to bind to (default: 8765).
            path: Path to listen on (default: /callback).
            timeout: Maximum time to wait for callback in seconds (default: 120).
        """
        self.host = host
        self.port = port
        self.path = path
        self.timeout = timeout
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._request_token: Optional[str] = None
        self._error: Optional[str] = None
        self._event = threading.Event()
        self._started = False

    def start(self) -> str:
        """Start the callback server.

        Returns:
            The callback URL (e.g., http://localhost:8765/callback).

        Raises:
            OSError: If the port is already in use.
            RuntimeError: If server is already started.
        """
        if self._started:
            raise RuntimeError("Callback server already started")

        def handler(*args, **kwargs):
            return CallbackHandler(*args, server_instance=self, **kwargs)

        self._server = HTTPServer((self.host, self.port), handler)
        # Update port to actual bound port (in case port=0 was used)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self._started = True

        # Give server a moment to start
        time.sleep(0.1)

        callback_url = f"http://{self.host}:{self.port}{self.path}"
        logger.info("Callback server started at %s", callback_url)
        return callback_url

    def stop(self) -> None:
        """Stop the callback server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._started = False
        logger.info("Callback server stopped")

    def wait_for_token(self) -> str:
        """Block until request_token is received or timeout/error occurs.

        Returns:
            The request_token string.

        Raises:
            TimeoutError: If no callback received within timeout.
            RuntimeError: If an error occurred during callback.
        """
        if not self._started:
            raise RuntimeError("Callback server not started. Call start() first.")

        logger.debug("Waiting for callback (timeout: %.1fs)...", self.timeout)
        signaled = self._event.wait(timeout=self.timeout)

        if not signaled:
            self.stop()
            raise TimeoutError(
                f"Timeout waiting for Zerodha callback after {self.timeout} seconds. "
                "Please ensure the redirect URL is registered in Kite Developer Console."
            )

        if self._error:
            self.stop()
            raise RuntimeError(self._error)

        token = self._request_token
        self.stop()
        logger.info("Received request_token from callback")
        return token

    def _set_token(self, token: str) -> None:
        """Set the received request_token and signal completion."""
        self._request_token = token
        self._event.set()

    def _set_error(self, error: str) -> None:
        """Set an error and signal completion."""
        self._error = error
        self._event.set()

    def __enter__(self) -> 'CallbackServer':
        """Context manager entry."""
        self._callback_url = self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop()