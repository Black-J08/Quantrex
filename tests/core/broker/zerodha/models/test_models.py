"""Tests for Zerodha broker models."""

from __future__ import annotations

from quantrex.core.broker.zerodha.models.models import ZerodhaInterval


class TestZerodhaInterval:
    """Tests for ZerodhaInterval enum."""

    def test_minute_value(self) -> None:
        """Test MINUTE interval value."""
        assert ZerodhaInterval.MINUTE == "minute"

    def test_three_minute_value(self) -> None:
        """Test THREE_MINUTE interval value."""
        assert ZerodhaInterval.THREE_MINUTE == "3minute"

    def test_five_minute_value(self) -> None:
        """Test FIVE_MINUTE interval value."""
        assert ZerodhaInterval.FIVE_MINUTE == "5minute"

    def test_ten_minute_value(self) -> None:
        """Test TEN_MINUTE interval value."""
        assert ZerodhaInterval.TEN_MINUTE == "10minute"

    def test_fifteen_minute_value(self) -> None:
        """Test FIFTEEN_MINUTE interval value."""
        assert ZerodhaInterval.FIFTEEN_MINUTE == "15minute"

    def test_thirty_minute_value(self) -> None:
        """Test THIRTY_MINUTE interval value."""
        assert ZerodhaInterval.THIRTY_MINUTE == "30minute"

    def test_sixty_minute_value(self) -> None:
        """Test SIXTY_MINUTE interval value."""
        assert ZerodhaInterval.SIXTY_MINUTE == "60minute"

    def test_day_value(self) -> None:
        """Test DAY interval value."""
        assert ZerodhaInterval.DAY == "day"

    def test_all_intervals_are_strings(self) -> None:
        """Test that all interval values are strings."""
        for interval in ZerodhaInterval:
            assert isinstance(interval.value, str)



