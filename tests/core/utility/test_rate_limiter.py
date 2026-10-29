"""Tests for RateLimiter."""

from __future__ import annotations

import time

import pytest

from quantrex.core.utility.rate_limiter import RateLimiter


class TestRateLimiter:
    """Tests for RateLimiter."""

    @pytest.mark.asyncio
    async def test_acquire_immediate(self) -> None:
        """Test acquiring token when available."""
        limiter = RateLimiter(rate=10.0)
        await limiter.acquire()  # Should not wait
        assert limiter.tokens == 9.0

    @pytest.mark.asyncio
    async def test_acquire_wait(self) -> None:
        """Test acquiring token when bucket empty."""
        limiter = RateLimiter(rate=1.0)
        await limiter.acquire()  # Use the one token
        assert limiter.tokens == 0.0

        # Next acquire should wait
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        # Should wait approximately 1 second
        assert elapsed >= 0.9
