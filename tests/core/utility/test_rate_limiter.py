"""Tests for RateLimiter."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from quantrex.core.utility.rate_limiter import SlidingWindowRateLimiter


class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_try_consume_immediate_under_limit(self) -> None:
        """Test consuming tokens when under the rate limit."""
        limiter = SlidingWindowRateLimiter(rate=10.0)
        for _ in range(10):
            assert limiter.try_consume() is True
        # 11th request exceeds the rate limit
        assert limiter.try_consume() is False

    def test_try_consume_false_when_window_full(self) -> None:
        """Test that try_consume returns False when the window is full."""
        limiter = SlidingWindowRateLimiter(rate=1.0)
        assert limiter.try_consume() is True
        assert limiter.try_consume() is False
        assert limiter.try_consume() is False

    def test_window_expiry_allows_new_consume(self) -> None:
        """Test that expired window entries allow new consumption."""
        limiter = SlidingWindowRateLimiter(rate=1.0)
        assert limiter.try_consume() is True
        assert limiter.try_consume() is False

        # Wait for the window to expire
        time.sleep(1.1)
        assert limiter.try_consume() is True

    def test_try_consume_weighted_tokens(self) -> None:
        """Test consuming multiple tokens at once."""
        limiter = SlidingWindowRateLimiter(rate=5.0)
        assert limiter.try_consume(tokens=3) is True
        # 3 + 3 > 5, so this should be rejected
        assert limiter.try_consume(tokens=3) is False
        # 3 + 2 <= 5, so this should be allowed
        assert limiter.try_consume(tokens=2) is True
        # Window is now full (5 tokens)
        assert limiter.try_consume() is False

    def test_try_consume_atomic_no_partial_record(self) -> None:
        """Test that a rejected consume records no timestamps."""
        limiter = SlidingWindowRateLimiter(rate=1.0)
        assert limiter.try_consume() is True
        # Window is full; rejected consume records nothing
        assert limiter.try_consume(tokens=2) is False
        # A single-token consume is still rejected until window expires
        assert limiter.try_consume() is False

    def test_try_consume_invalid_tokens(self) -> None:
        """Test that non-positive token counts raise ValueError."""
        limiter = SlidingWindowRateLimiter(rate=10.0)
        with pytest.raises(ValueError):
            limiter.try_consume(tokens=0)
        with pytest.raises(ValueError):
            limiter.try_consume(tokens=-1)

    def test_rate_limiter_invalid_rate(self) -> None:
        """Test that non-positive rate raises ValueError."""
        with pytest.raises(ValueError):
            SlidingWindowRateLimiter(rate=0.0)
        with pytest.raises(ValueError):
            SlidingWindowRateLimiter(rate=-1.0)

    def test_concurrent_try_consume_serializes(self) -> None:
        """Test that concurrent try_consume calls are serialized."""
        limiter = SlidingWindowRateLimiter(rate=10.0)
        results: list[bool] = []

        def worker() -> None:
            results.append(limiter.try_consume())

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # At most `rate` consumes should succeed within the window
        assert results.count(True) <= 10
        assert results.count(True) + results.count(False) == 20

    @pytest.mark.asyncio
    async def test_acquire_immediate_under_limit(self) -> None:
        """Test acquire() returns immediately when under the rate limit."""
        limiter = SlidingWindowRateLimiter(rate=10.0)
        await limiter.acquire()
        await limiter.acquire(tokens=3)
        # 1 + 3 = 4 tokens consumed, 6 remain
        assert limiter.try_consume(tokens=6) is True
        assert limiter.try_consume() is False

    @pytest.mark.asyncio
    async def test_acquire_waits_when_window_full(self) -> None:
        """Test acquire() waits until the window expires when full."""
        limiter = SlidingWindowRateLimiter(rate=1.0)
        assert limiter.try_consume() is True
        assert limiter.try_consume() is False

        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start

        # Should have waited approximately one second for the window to expire
        assert elapsed >= 0.9
        # Window now has one token from the acquire
        assert limiter.try_consume() is False

    @pytest.mark.asyncio
    async def test_acquire_invalid_tokens(self) -> None:
        """Test acquire() rejects non-positive token counts."""
        limiter = SlidingWindowRateLimiter(rate=10.0)
        with pytest.raises(ValueError, match="tokens must be a positive integer"):
            await limiter.acquire(tokens=0)
        with pytest.raises(ValueError, match="tokens must be a positive integer"):
            await limiter.acquire(tokens=-1)

    @pytest.mark.asyncio
    async def test_acquire_tokens_exceeds_rate(self) -> None:
        """Test acquire() rejects token counts exceeding the rate."""
        limiter = SlidingWindowRateLimiter(rate=3.0)
        with pytest.raises(ValueError, match="cannot exceed rate"):
            await limiter.acquire(tokens=4)

    @pytest.mark.asyncio
    async def test_acquire_cancellation_no_tokens_consumed(self) -> None:
        """Test that cancelling acquire() consumes no tokens."""
        limiter = SlidingWindowRateLimiter(rate=1.0)
        assert limiter.try_consume() is True

        async def cancel_after_delay() -> None:
            await asyncio.sleep(0.1)
            task.cancel()

        task = asyncio.create_task(limiter.acquire())
        cancel_task = asyncio.create_task(cancel_after_delay())

        with pytest.raises(asyncio.CancelledError):
            await task
        await cancel_task

        # No tokens should have been consumed by the cancelled acquire
        assert limiter.try_consume() is False

    @pytest.mark.asyncio
    async def test_acquire_weighted_tokens(self) -> None:
        """Test acquire() with weighted token consumption."""
        limiter = SlidingWindowRateLimiter(rate=5.0)
        await limiter.acquire(tokens=3)
        # 3 + 3 > 5, so this should wait
        acquire_task = asyncio.create_task(limiter.acquire(tokens=3))
        await asyncio.sleep(0.1)
        assert not acquire_task.done()
        # Free up tokens by waiting for the window to expire
        await asyncio.sleep(1.0)
        await acquire_task
        # Window now has 3 tokens from the second acquire; 2 more fit within rate=5
        assert limiter.try_consume(tokens=2) is True
        # Window is now full (5 tokens)
        assert limiter.try_consume() is False

    @pytest.mark.asyncio
    async def test_acquire_concurrent_serializes(self) -> None:
        """Test that concurrent acquire() calls are serialized by the limiter."""
        limiter = SlidingWindowRateLimiter(rate=3.0)
        results: list[float] = []

        async def worker() -> None:
            start = time.monotonic()
            await limiter.acquire()
            results.append(time.monotonic() - start)

        # Launch 5 concurrent acquires; only 3 can proceed immediately
        tasks = [asyncio.create_task(worker()) for _ in range(5)]
        await asyncio.gather(*tasks)

        # At most 3 should have waited ~0 seconds; the rest waited for window expiry
        immediate = sum(1 for r in results if r < 0.1)
        assert immediate <= 3
        assert len(results) == 5
