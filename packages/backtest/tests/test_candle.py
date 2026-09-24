"""Tests for Candle model."""

from datetime import datetime, timedelta
from quantrex_data.providers.csv_provider import CSVDataProvider
from quantrex_data.adapters.csv_adapter import CSVDataAdapter
from quantrex_core.models import Candle
from quantrex_test_support.csv import (
    make_ohlc_series,
    csv_rows_to_string,
    create_temp_csv,
)


class TestCandle:
    """Tests for Candle dataclass."""

    def test_candle_creation(self):
        """Test basic Candle creation with all fields."""
        timestamp = datetime(2023, 6, 20, 19, 0)
        timeframe = "1M"
        close_time = timestamp + timedelta(minutes=1)
        
        candle = Candle(
            symbol="COPPER",
            timestamp=timestamp,
            close_time=close_time,
            timeframe=timeframe,
            open=737.20,
            high=737.20,
            low=737.20,
            close=737.20,
            volume=1.0,
        )

        assert candle.symbol == "COPPER"
        assert candle.timestamp == timestamp
        assert candle.close_time == close_time
        assert candle.timeframe == timeframe
        assert candle.open == 737.20
        assert candle.high == 737.20
        assert candle.low == 737.20
        assert candle.close == 737.20
        assert candle.volume == 1.0

    def test_candle_immutability(self):
        """Test that Candle is immutable (frozen dataclass)."""
        timestamp = datetime(2023, 6, 20, 19, 0)
        timeframe = "1M"
        close_time = timestamp + timedelta(minutes=1)
        
        candle = Candle(
            symbol="COPPER",
            timestamp=timestamp,
            close_time=close_time,
            timeframe=timeframe,
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

        candle = Candle.from_row(row, symbol="COPPER", timeframe="1M")

        assert candle.symbol == "COPPER"
        assert candle.timestamp == datetime(2023, 6, 20, 19, 0)
        assert candle.close_time == datetime(2023, 6, 20, 19, 1)
        assert candle.timeframe == "1M"
        assert candle.open == 737.20
        assert candle.high == 737.20
        assert candle.low == 737.20
        assert candle.close == 737.20
        assert candle.volume == 1.0

    def test_candle_from_csv_integration(self):
        """Test Candle.from_row with data from full CSV pipeline using test-support."""
        # Generate realistic OHLC data using test-support
        rows = make_ohlc_series(num_rows=3, seed=42)
        csv_content = csv_rows_to_string(rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": [0, 1],
                "open": 2,
                "high": 3,
                "low": 4,
                "close": 5,
                "volume": 6,
            })
            csv_rows = adapter.read()

            candles = [Candle.from_row(row, symbol="COPPER", timeframe="1M") for row in csv_rows]

            assert len(candles) == 3
            for candle in candles:
                assert candle.symbol == "COPPER"
                assert isinstance(candle.timestamp, datetime)
                assert candle.timeframe == "1M"
                assert candle.open > 0
                assert candle.high >= candle.open
                assert candle.low <= candle.open
                assert candle.close > 0
                assert candle.volume > 0

    def test_candle_from_csv_with_custom_datetime_format(self):
        """Test Candle.from_row with custom datetime format through CSV pipeline."""
        # Generate data with custom datetime format
        rows = make_ohlc_series(
            num_rows=2,
            start_datetime=datetime(2023, 6, 20, 19, 0),
            interval_minutes=60,
            seed=42,
        )
        # Convert to custom format: YYYY-MM-DD HH:MM:SS
        custom_rows = []
        for row in rows:
            date_str, time_str = row[0], row[1]
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y%m%d %H:%M")
            custom_datetime = dt.strftime("%Y-%m-%d %H:%M:%S")
            custom_rows.append([custom_datetime] + row[2:])

        csv_content = csv_rows_to_string(custom_rows)

        with create_temp_csv(csv_content) as temp_path:
            provider = CSVDataProvider(temp_path, has_header=False)
            adapter = CSVDataAdapter(provider, column_mapping={
                "datetime": 0,
                "open": 1,
                "high": 2,
                "low": 3,
                "close": 4,
                "volume": 5,
            }, datetime_format="%Y-%m-%d %H:%M:%S")
            csv_rows = adapter.read()

            candles = [
                Candle.from_row(row, symbol="COPPER", timeframe="1H", datetime_format="%Y-%m-%d %H:%M:%S")
                for row in csv_rows
            ]

            assert len(candles) == 2
            assert candles[0].timestamp == datetime(2023, 6, 20, 19, 0, 0)
            assert candles[0].close_time == datetime(2023, 6, 20, 20, 0, 0)
            assert candles[0].timeframe == "1H"
            assert candles[1].timestamp == datetime(2023, 6, 20, 20, 0, 0)
            assert candles[1].close_time == datetime(2023, 6, 20, 21, 0, 0)
            assert candles[1].timeframe == "1H"

    def test_candle_from_row_missing_key(self):
        """Test Candle.from_row raises ValueError for missing key."""
        row = {
            "datetime": "20230620 19:00",
            "open": "737.20",
            # missing high, low, close, volume
        }

        try:
            Candle.from_row(row, symbol="COPPER", timeframe="1M")
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
            Candle.from_row(row, symbol="COPPER", timeframe="1M")
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

        candle = Candle.from_row(row, symbol="COPPER", timeframe="1M", datetime_format="%Y-%m-%d %H:%M:%S")

        assert candle.timestamp == datetime(2023, 6, 20, 19, 0, 0)
        assert candle.close_time == datetime(2023, 6, 20, 19, 1, 0)
        assert candle.timeframe == "1M"

    def test_candle_slots(self):
        """Test that Candle uses __slots__ for memory efficiency."""
        timestamp = datetime(2023, 6, 20, 19, 0)
        timeframe = "1M"
        close_time = timestamp + timedelta(minutes=1)
        
        candle = Candle(
            symbol="COPPER",
            timestamp=timestamp,
            close_time=close_time,
            timeframe=timeframe,
            open=737.20,
            high=737.20,
            low=737.20,
            close=737.20,
            volume=1.0,
        )

        # Should not have __dict__ due to slots=True
        assert not hasattr(candle, "__dict__")