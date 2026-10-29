"""Sliding window rate limiter utility."""

from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    """Sliding window rate limiter.

    Tracks request timestamps in a rolling one-second window and allows
    consumption only when the requested tokens fit within the configured
    rate. Non-blocking: returns ``False`` when the rate limit would be
    exceeded, without recording any timestamps.
    """

    def __init__(self, rate: float):
        if rate <= 0:
            raise ValueError("rate must be a positive number")
        self.rate = rate
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def try_consume(self, tokens: int = 1) -> bool:
        """Attempt to consume tokens within the sliding window.

        Atomically checks whether the requested tokens fit within the
        sliding window and records the consumption timestamp only if
        allowed.

        Args:
            tokens: Number of tokens to consume (default 1).

        Returns:
            True if the tokens were consumed, False if the rate limit
            would be exceeded.
        """
        if tokens <= 0:
            raise ValueError("tokens must be a positive integer")

        now = time.monotonic()
        window_start = now - (1.0 / self.rate)

        with self._lock:
            # Prune timestamps outside the sliding window
            while self._timestamps and self._timestamps[0] < window_start:
                self._timestamps.popleft()

            if len(self._timestamps) + tokens > self.rate:
                return False

            for _ in range(tokens):
                self._timestamps.append(now)
            return True
