"""Tests for Candle model."""

from datetime import datetime
from quantrex_backtest.models.candle import Candle


class TestCandle:
    """Tests for Candle dataclass."""

    def test_candle_creation(self):
        """Test basic Candle creation with all fields."""
        candle = Candle(
            symbol="COPPER",
            timestamp=datetime(2023, 6, 20, 19, 0),
            open=737.20,
            high=737.20,
            low=737.20,
            close=737.20,
            volume=1.0,
        )

        assert candle.symbol == "COPPER"
        assert candle.timestamp == datetime(2023, 6, 20, 19, 0)
        assert candle.open == 737.20
        assert candle.high == 737.20
        assert candle.low == 737.20
        assert candle.close == 737.20
        assert candle.volume == 1.0

    def test_candle_immutability(self):
        """Test that Candle is immutable (frozen dataclass)."""
        candle = Candle(
            symbol="COPPER",
            timestamp=datetime(2023, 6, 20, 19, 0),
            open=737.20,
            high=737.20,
            low=737.20,
            close=737.20,
            volume=1.0,
        )

        # Attempting to modify should raise FrozenInstanceError
        try:
            candle.open = 100.0
            assert False, "Should have raised FrozenInstanceError"
        except Exception:
            pass  # Expected

    def test_candle_from_row_valid(self):
        """Test Candle.from_row with valid data."""
        row = {
            "datetime": "20230620 19:00",
            "open": "737.20",
            "high": "737.20",
            "low": "737.20",
            "close": "737.20",
            "volume": "1",
        }

        candle = Candle.from_row(row, symbol="COPPER")

        assert candle.symbol == "COPPER"
        assert candle.timestamp == datetime(2023, 6, 20, 19, 0)
        assert candle.open == 737.20
        assert candle.high == 737.20
        assert candle.low == 737.20
        assert candle.close == 737.20
        assert candle.volume == 1.0

    def test_candle_from_row_missing_key(self):
        """Test Candle.from_row raises ValueError for missing key."""
        row = {
            "datetime": "20230620 19:00",
            "open": "737.20",
            # missing high, low, close, volume
        }

        try:
            Candle.from_row(row, symbol="COPPER")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Missing required key" in str(e)

    def test_candle_from_row_invalid_float(self):
        """Test Candle.from_row raises ValueError for invalid float."""
        row = {
            "datetime": "20230620 19:00",
            "open": "not_a_number",
            "high": "737.20",
            "low": "737.20",
            "close": "737.20",
            "volume": "1",
        }

        try:
            Candle.from_row(row, symbol="COPPER")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Failed to parse row values" in str(e)

    def test_candle_from_row_custom_datetime_format(self):
        """Test Candle.from_row with custom datetime format."""
        row = {
            "datetime": "2023-06-20 19:00:00",
            "open": "737.20",
            "high": "737.20",
            "low": "737.20",
            "close": "737.20",
            "volume": "1",
        }

        candle = Candle.from_row(row, symbol="COPPER", datetime_format="%Y-%m-%d %H:%M:%S")

        assert candle.timestamp == datetime(2023, 6, 20, 19, 0, 0)

    def test_candle_slots(self):
        """Test that Candle uses __slots__ for memory efficiency."""
        candle = Candle(
            symbol="COPPER",
            timestamp=datetime(2023, 6, 20, 19, 0),
            open=737.20,
            high=737.20,
            low=737.20,
            close=737.20,
            volume=1.0,
        )

        # Should not have __dict__ due to slots=True
        assert not hasattr(candle, "__dict__")