"""Tests for RateLimiter."""

from __future__ import annotations

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
