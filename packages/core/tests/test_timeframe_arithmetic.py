"""Unit tests for timeframe arithmetic module."""

import pytest
from datetime import datetime, time
from quantrex_core.timeframe.arithmetic import (
    align_to_origin,
    get_interval_bounds,
    is_interval_complete,
    compare_timeframes,
    is_multiple_of,
    get_next_interval_start,
)


class TestAlignToOrigin:
    """Tests for align_to_origin function."""

    def test_align_to_origin_nse(self):
        """Test alignment with NSE origin time (09:15)."""
        origin = time(9, 15)
        # 10:15 should align to 10:15 for 1H interval
        ts = datetime(2024, 1, 1, 10, 15)
        result = align_to_origin(ts, origin, 60)
        assert result == datetime(2024, 1, 1, 10, 15)

    def test_align_to_origin_mid_interval(self):
        """Test alignment for timestamp in middle of interval."""
        origin = time(9, 15)
        # 10:30 should align to 10:15 for 1H interval
        ts = datetime(2024, 1, 1, 10, 30)
        result = align_to_origin(ts, origin, 60)
        assert result == datetime(2024, 1, 1, 10, 15)

    def test_align_to_origin_15min(self):
        """Test alignment with 15-minute intervals."""
        origin = time(9, 15)
        # 09:20 should align to 09:15 for 15M interval
        ts = datetime(2024, 1, 1, 9, 20)
        result = align_to_origin(ts, origin, 15)
        assert result == datetime(2024, 1, 1, 9, 15)

    def test_align_to_origin_midnight(self):
        """Test alignment with midnight origin."""
        origin = time(0, 0)
        ts = datetime(2024, 1, 1, 10, 30)
        result = align_to_origin(ts, origin, 60)
        assert result == datetime(2024, 1, 1, 10, 0)


class TestGetIntervalBounds:
    """Tests for get_interval_bounds function."""

    def test_bounds_1h_nse(self):
        """Test bounds for 1H interval with NSE origin."""
        origin = time(9, 15)
        ts = datetime(2024, 1, 1, 10, 30)
        start, end = get_interval_bounds(ts, origin, 60)
        assert start == datetime(2024, 1, 1, 10, 15)
        assert end == datetime(2024, 1, 1, 11, 15)


class TestIsIntervalComplete:
    """Tests for is_interval_complete function."""

    def test_complete_interval(self):
        """Test that interval is complete when current_time >= end."""
        origin = time(9, 15)
        ts = datetime(2024, 1, 1, 10, 30)  # In 10:15-11:15 interval
        current = datetime(2024, 1, 1, 11, 20)  # After interval end
        assert is_interval_complete(ts, origin, 60, current) is True

    def test_incomplete_interval(self):
        """Test that interval is not complete when current_time < end."""
        origin = time(9, 15)
        ts = datetime(2024, 1, 1, 10, 30)
        current = datetime(2024, 1, 1, 11, 0)  # Before interval end
        assert is_interval_complete(ts, origin, 60, current) is False


class TestCompareTimeframes:
    """Tests for compare_timeframes function."""

    def test_1h_vs_15m(self):
        assert compare_timeframes("1H", "15M") == 1  # 1H > 15M
        assert compare_timeframes("15M", "1H") == -1  # 15M < 1H

    def test_equal_timeframes(self):
        assert compare_timeframes("1H", "1H") == 0
        assert compare_timeframes("1D", "1D") == 0

    def test_1d_vs_1h(self):
        assert compare_timeframes("1D", "1H") == 1
        assert compare_timeframes("1H", "1D") == -1


class TestIsMultipleOf:
    """Tests for is_multiple_of function."""

    def test_1h_multiple_of_15m(self):
        assert is_multiple_of("15M", "1H") is True

    def test_1h_not_multiple_of_30m(self):
        assert is_multiple_of("30M", "1H") is True

    def test_4h_multiple_of_1h(self):
        assert is_multiple_of("1H", "4H") is True

    def test_not_multiple(self):
        assert is_multiple_of("7M", "1H") is False  # 60 % 7 != 0
        assert is_multiple_of("7M", "1D") is False  # 1440 % 7 != 0


class TestGetNextIntervalStart:
    """Tests for get_next_interval_start function."""

    def test_next_1h_interval(self):
        origin = time(9, 15)
        ts = datetime(2024, 1, 1, 10, 30)
        next_start = get_next_interval_start(ts, origin, 60)
        assert next_start == datetime(2024, 1, 1, 11, 15)