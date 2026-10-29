"""Sliding window rate limiter utility."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque


class SlidingWindowRateLimiter:
    """Sliding window rate limiter.

    Tracks request timestamps in a rolling one-second window and allows
    consumption only when the requested tokens fit within the configured
    rate. Non-blocking: returns ``False`` when the rate limit would be
    exceeded, without recording any timestamps. Thread-safe.

    Args:
        rate: Maximum number of tokens allowed in any rolling one-second
            window. Must be positive.

    Raises:
        ValueError: If ``rate`` is not positive.

    Example:
        >>> limiter = RateLimiter(rate=5)
        >>> limiter.try_consume()
        True
        >>> limiter.try_consume(tokens=5)  # 1 + 5 exceeds 5 within the window
        False
    """

    _WINDOW_SECONDS = 1.0

    def __init__(self, rate: float):
        if rate <= 0:
            raise ValueError("rate must be a positive number")
        self.rate = rate
        # One entry per consumed token, in non-decreasing order of time.
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def try_consume(self, tokens: int = 1) -> bool:
        """Attempt to consume tokens within the sliding window.

        Atomically checks whether the requested tokens fit within the
        sliding window and records the consumption timestamp only if
        allowed. A rejected call has no side effect on limiter state.

        Args:
            tokens: Number of tokens to consume (default 1).

        Returns:
            True if the tokens were consumed, False if the rate limit
            would be exceeded. A request larger than ``rate`` can never
            succeed and always returns False.

        Raises:
            ValueError: If ``tokens`` is not positive.
        """
        if tokens <= 0:
            raise ValueError("tokens must be a positive integer")

        with self._lock:
            # Read the clock inside the lock so concurrent callers append
            # timestamps in order; pruning below relies on a sorted deque.
            now = time.monotonic()
            window_start = now - self._WINDOW_SECONDS

            # Drop timestamps that have left the window. A timestamp exactly
            # one window old is expired, so at most ``rate`` tokens are ever
            # counted per rolling second.
            while self._timestamps and self._timestamps[0] <= window_start:
                self._timestamps.popleft()

            if len(self._timestamps) + tokens > self.rate:
                return False

            self._timestamps.extend([now] * tokens)
            return True

    async def acquire(self, tokens: int = 1) -> None:
        """Acquire rate-limit capacity, waiting until sufficient tokens are available.

        Unlike :meth:`try_consume`, this method blocks asynchronously until the
        requested tokens fit within the sliding window, then consumes them.
        A rejected call has no side effect on limiter state.

        Args:
            tokens: Number of tokens to acquire (default 1).

        Raises:
            ValueError: If ``tokens`` is not positive or exceeds ``rate``.
        """
        if tokens <= 0:
            raise ValueError("tokens must be a positive integer")
        if tokens > self.rate:
            raise ValueError(f"tokens ({tokens}) cannot exceed rate ({self.rate})")

        while True:
            if self.try_consume(tokens):
                return

            # Compute how long to wait until the oldest timestamp leaves the window.
            with self._lock:
                if not self._timestamps:
                    # Window is empty but try_consume returned False — shouldn't happen,
                    # but avoid a busy loop.
                    continue
                oldest = self._timestamps[0]

            now = time.monotonic()
            wait_until = oldest + self._WINDOW_SECONDS
            sleep_for = max(wait_until - now, 1e-6)
            await asyncio.sleep(sleep_for)