"""Unit tests for timeframe filtering module."""

import pytest
from datetime import datetime, time, timedelta
from quantrex_core.models import Candle
from quantrex_core.timeframe.filtering import (
    filter_candles_by_timeframe,
    filter_candles_by_timeframe_minutes,
)


def make_candle(timestamp: datetime, symbol: str = "TEST", close: float = 100.0, timeframe: str = "1M") -> Candle:
    """Create a test candle."""
    close_time = timestamp + timedelta(minutes=1) if timeframe == "1M" else timestamp + timedelta(hours=1)
    return Candle(
        symbol=symbol,
        timestamp=timestamp,
        close_time=close_time,
        timeframe=timeframe,
        open=100.0,
        high=101.0,
        low=99.0,
        close=close,
        volume=1000.0,
    )


class TestFilterCandlesByTimeframe:
    """Tests for filter_candles_by_timeframe function."""

    def test_empty_candles(self):
        """Test filtering empty list returns empty tuple."""
        result = filter_candles_by_timeframe([], "1H", time(9, 15))
        assert result == ()

    def test_single_candle(self):
        """Test filtering single candle."""
        candles = [make_candle(datetime(2024, 1, 1, 10, 30))]
        result = filter_candles_by_timeframe(candles, "1H", time(9, 15))
        assert len(result) == 1
        assert result[0].timestamp == datetime(2024, 1, 1, 10, 30)

    def test_multiple_candles_same_interval(self):
        """Test multiple candles in same interval - only last returned."""
        # All candles in 10:15-11:15 interval with NSE origin 09:15
        candles = [
            make_candle(datetime(2024, 1, 1, 10, 15)),
            make_candle(datetime(2024, 1, 1, 10, 30)),
            make_candle(datetime(2024, 1, 1, 10, 45)),
        ]
        result = filter_candles_by_timeframe(candles, "1H", time(9, 15))
        assert len(result) == 1
        assert result[0].timestamp == datetime(2024, 1, 1, 10, 45)

    def test_multiple_candles_different_intervals(self):
        """Test candles spanning multiple intervals."""
        # Candles in 10:15-11:15 and 11:15-12:15 intervals with NSE origin 09:15
        candles = [
            make_candle(datetime(2024, 1, 1, 10, 15)),
            make_candle(datetime(2024, 1, 1, 10, 45)),
            make_candle(datetime(2024, 1, 1, 11, 15)),
            make_candle(datetime(2024, 1, 1, 11, 45)),
        ]
        result = filter_candles_by_timeframe(candles, "1H", time(9, 15))
        assert len(result) == 2
        assert result[0].timestamp == datetime(2024, 1, 1, 10, 45)
        assert result[1].timestamp == datetime(2024, 1, 1, 11, 45)

    def test_15min_intervals(self):
        """Test filtering with 15-minute intervals."""
        candles = [
            make_candle(datetime(2024, 1, 1, 9, 15)),
            make_candle(datetime(2024, 1, 1, 9, 20)),
            make_candle(datetime(2024, 1, 1, 9, 30)),
            make_candle(datetime(2024, 1, 1, 9, 35)),
        ]
        result = filter_candles_by_timeframe(candles, "15M", time(9, 15))
        assert len(result) == 2
        assert result[0].timestamp == datetime(2024, 1, 1, 9, 20)
        assert result[1].timestamp == datetime(2024, 1, 1, 9, 35)

    def test_daily_intervals(self):
        """Test filtering with daily intervals."""
        candles = [
            make_candle(datetime(2024, 1, 1, 10, 0)),
            make_candle(datetime(2024, 1, 1, 14, 0)),
            make_candle(datetime(2024, 1, 2, 10, 0)),
            make_candle(datetime(2024, 1, 2, 14, 0)),
        ]
        result = filter_candles_by_timeframe(candles, "1D", time(9, 15))
        assert len(result) == 2
        assert result[0].timestamp == datetime(2024, 1, 1, 14, 0)
        assert result[1].timestamp == datetime(2024, 1, 2, 14, 0)

    def test_invalid_interval(self):
        """Test that invalid interval raises ValueError."""
        candles = [make_candle(datetime(2024, 1, 1, 10, 0))]
        with pytest.raises(ValueError, match="Invalid interval format"):
            filter_candles_by_timeframe(candles, "invalid", time(9, 15))

    def test_midnight_origin(self):
        """Test filtering with midnight origin."""
        candles = [
            make_candle(datetime(2024, 1, 1, 10, 0)),
            make_candle(datetime(2024, 1, 1, 10, 30)),
            make_candle(datetime(2024, 1, 1, 11, 0)),
        ]
        result = filter_candles_by_timeframe(candles, "1H", time(0, 0))
        assert len(result) == 2
        assert result[0].timestamp == datetime(2024, 1, 1, 10, 30)
        assert result[1].timestamp == datetime(2024, 1, 1, 11, 0)


class TestFilterCandlesByTimeframeMinutes:
    """Tests for filter_candles_by_timeframe_minutes function."""

    def test_same_as_string_version(self):
        """Test that minutes version produces same result as string version."""
        candles = [
            make_candle(datetime(2024, 1, 1, 10, 0)),
            make_candle(datetime(2024, 1, 1, 10, 30)),
            make_candle(datetime(2024, 1, 1, 11, 0)),
        ]
        result1 = filter_candles_by_timeframe(candles, "1H", time(9, 15))
        result2 = filter_candles_by_timeframe_minutes(candles, 60, time(9, 15))
        assert result1 == result2