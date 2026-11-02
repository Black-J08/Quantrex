"""Tests for ShoonyaInterval enum."""

from quantrex.core.broker.shoonya.models.models import ShoonyaInterval


class TestShoonyaInterval:
    """Tests for ShoonyaInterval enum."""

    def test_minute_1_value(self) -> None:
        """Test MINUTE_1 interval value."""
        assert ShoonyaInterval.MINUTE_1 == "1"

    def test_minute_3_value(self) -> None:
        """Test MINUTE_3 interval value."""
        assert ShoonyaInterval.MINUTE_3 == "3"

    def test_minute_5_value(self) -> None:
        """Test MINUTE_5 interval value."""
        assert ShoonyaInterval.MINUTE_5 == "5"

    def test_minute_10_value(self) -> None:
        """Test MINUTE_10 interval value."""
        assert ShoonyaInterval.MINUTE_10 == "10"

    def test_minute_15_value(self) -> None:
        """Test MINUTE_15 interval value."""
        assert ShoonyaInterval.MINUTE_15 == "15"

    def test_minute_30_value(self) -> None:
        """Test MINUTE_30 interval value."""
        assert ShoonyaInterval.MINUTE_30 == "30"

    def test_minute_60_value(self) -> None:
        """Test MINUTE_60 interval value."""
        assert ShoonyaInterval.MINUTE_60 == "60"

    def test_minute_120_value(self) -> None:
        """Test MINUTE_120 interval value."""
        assert ShoonyaInterval.MINUTE_120 == "120"

    def test_minute_240_value(self) -> None:
        """Test MINUTE_240 interval value."""
        assert ShoonyaInterval.MINUTE_240 == "240"

    def test_day_value(self) -> None:
        """Test DAY interval value."""
        assert ShoonyaInterval.DAY == "1D"

    def test_all_intervals_are_strings(self) -> None:
        """Test that all interval values are strings."""
        for interval in ShoonyaInterval:
            assert isinstance(interval.value, str)
