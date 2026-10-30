"""Live websocket data feed.

Provides a live stream of market data events via websocket.
"""

from __future__ import annotations


class LiveStream:
    """Live websocket stream of market data.

    Connects to a vendor websocket and yields tick/candle events in
    real time.
    """

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self._subscribed = False

    def subscribe(self) -> None:
        """Subscribe to the live feed for the configured symbol."""
        self._subscribed = True

    def is_subscribed(self) -> bool:
        """Return whether the stream is subscribed."""
        return self._subscribed

    def __iter__(self):
        """Yield live tick events.

        This is a placeholder; a real implementation would read from
        a websocket connection.
        """
        if not self._subscribed:
            msg = "stream not subscribed"
            raise RuntimeError(msg)
        return iter(())
