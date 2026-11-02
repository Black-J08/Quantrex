"""Local callback server for Shoonya OAuth authentication."""

from __future__ import annotations

import asyncio
import logging
import webbrowser
from dataclasses import dataclass
from typing import Self

from aiohttp import web

logger = logging.getLogger(__name__)

CALLBACK_URL_TEMPLATE = "http://{host}:{port}{path}"


@dataclass(slots=True)
class CallbackResult:
    """Result of OAuth callback."""

    code: str | None = None
    error: str | None = None


class CallbackServer:
    """Local HTTP server to handle Shoonya OAuth callback."""

    def __init__(self, port: int = 8765, host: str = "127.0.0.1", path: str = "/callback"):
        """Initialize callback server.

        Args:
            port: Port to listen on
            host: Host to bind to (localhost only for security)
            path: Callback path (e.g., "/callback", "/auth/callback")
        """
        self.port = port
        self.host = host
        self.path = path
        self._result: CallbackResult = CallbackResult()
        self._event = asyncio.Event()
        self._app = web.Application()
        self._app.router.add_get(path, self._handle_callback)
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def _handle_callback(self, request: web.Request) -> web.Response:
        """Handle OAuth callback from Shoonya."""
        code = request.query.get("code")
        error = request.query.get("error")

        if error:
            self._result = CallbackResult(error=error)
            logger.error("Callback error: %s", error)
        elif code:
            self._result = CallbackResult(code=code)
            logger.info("Received authorization code")
        else:
            self._result = CallbackResult(error="No authorization code in callback")
            logger.error("Callback missing authorization code")

        self._event.set()
        return web.Response(text="Authentication complete. You can close this window.")

    async def start(self) -> None:
        """Start the callback server."""
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        logger.info(
            "Callback server started on http://%s:%d%s", self.host, self.port, self.path
        )

    async def stop(self) -> None:
        """Stop the callback server."""
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        logger.info("Callback server stopped")

    async def wait_for_callback(self, timeout: float = 120.0) -> CallbackResult:
        """Wait for OAuth callback.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            CallbackResult with authorization code or error
        """
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except TimeoutError:
            self._result = CallbackResult(error="Callback timeout")
            logger.error("Callback timeout")
        return self._result

    def get_callback_url(self) -> str:
        """Get the callback URL."""
        return CALLBACK_URL_TEMPLATE.format(host=self.host, port=self.port, path=self.path)

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()


async def open_browser(url: str) -> None:
    """Open the default browser to the given URL."""
    webbrowser.open(url)
